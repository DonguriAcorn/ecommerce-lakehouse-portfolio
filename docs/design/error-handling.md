# エラーの設計(取り込み)

- 作成日: 2026-10-31
- 状態: 合意済み(実装前)

## 目的と範囲

取り込みの Python(`ingestion/`)が、問題を見つけたときに、どう止め、何を記録し、悪い行をどこに置くかを決める。

- 対象: 元の CSV を読んでから、Raw の Parquet を書き出すまで(`run_replay.py`)。
- 対象外:
  - dbt の失敗(Airflow の運用で、`run_results.json` の要点を logs/ に書く。tasks.md のフェーズ2)
  - リトライと失敗の通知(Airflow の運用で決める)
  - S3 へのアップロード(今は AWS CLI で行う。Python から S3 に直接書くようになったら、見直す)

## 用語

| 用語 | 意味 | 例 |
|---|---|---|
| 停止 | 実行全体を止める。Raw は1ファイルも書かない | 元の CSV がない |
| 隔離 | 悪い行だけを quarantine/ に移し、残りの行は通す | 購入日時が日付として読めない行 |
| batch_id | 1回の実行の識別子。Raw の監査カラム `_batch_id` と同じ値を使う | 20261031T013000Z |
| run_date | 実行した日(UTC)。リプレイ上の日付 `ingest_date` とは別 | 2026-10-31 |

## Python と dbt test の分担

| 見るもの | 担当 | 理由 |
|---|---|---|
| ファイルがあるか、必要な列があるか | Python(停止) | ないと、処理が始められない |
| order_id が空、または元データの中で重複 | Python(隔離) | リプレイが注文の単位で動くため |
| order_purchase_timestamp が空 | Python(隔離) | リプレイの最初の出来事(購入)がなく、注文が一度も出力されないため |
| 日時の列が、日時として読めない | Python(隔離) | 読めない値があると、`load_orders` が実行全体を止めてしまう |
| order_status が、既知の8つの値以外 | Python(隔離) | リプレイのルール(最終状態を合成するか)が、この値で分かれるため |
| Silver の一意性、NULL、許される値 | dbt test | テーブルに入ったあとの状態を見る |
| 日付の前後関係、delivered なのに配達日時が空 | dbt test(警告) | 業務のルール。行を止める理由にはしない |

- 既知の order_status: created、approved、invoiced、processing、shipped、delivered、canceled、unavailable(orders-data-profile.md)。
- order_status は、Python と dbt の両方で見る。ただし、見ている値が違う。Python は元データの値(リプレイの前提)、dbt はリプレイ後の Silver の値を見る。

## 停止と隔離の基準

- 停止する場合
  - 元の CSV が読めない(ない、壊れている)
  - 必要な列(8列)が1つでも欠けている
  - 隔離した行が、全体の 1% を超える(元データ側の大きな異常とみなす)
- 隔離する場合: 上の分担の表で「Python(隔離)」とした5つ。1行に複数の問題があっても、隔離は1回だけにし、理由はすべて記録する。
- 検証は、CSV を読んだ直後に全行まとめて行う。停止するときは、Raw を1ファイルも書く前に止まる。
- 終了コード: 正常(隔離が 1% 以下を含む)は 0、停止は 1。Airflow は、0 以外を失敗として扱う。

## ログ

- 場所: `logs/ingest/olist/orders/run_date=YYYY-MM-DD/batch_id=<batch_id>/events.jsonl`
- 形式: JSON Lines(1行 = 1つの出来事)。Athena で集計できるように、項目に分けて持ち、`message` は項目から組み立てる。
- ローカルでは `data/logs/` の下に同じ形で書き、Raw と一緒に S3 にアップロードする。画面(標準出力)にも `message` を出す。

| 項目 | 必須 | 意味 | 例 |
|---|---|---|---|
| `ts` | ○ | 出来事の日時(UTC) | 2026-10-31T01:30:02Z |
| `level` | ○ | INFO / WARNING / ERROR | ERROR |
| `batch_id` | ○ | 実行の識別子 | 20261031T013000Z |
| `table` | ○ | 対象のテーブル | orders |
| `stage` | ○ | 処理の段階 | ORDERS_VALIDATE |
| `code` | ○ | 出来事の種類(決まった名前) | UNPARSABLE_TIMESTAMP |
| `ingest_date` | | リプレイ上の日付(日ごとの処理のとき) | 2017-10-04 |
| `column` | | 関係する列 | order_approved_at |
| `count` | | 件数 | 3 |
| `samples` | | 値の例(最大3件) | ["2017-13-01 10:00:00"] |
| `message` | ○ | 人が読む文 | 下を参照 |

- `message` の形: `[段階] 何が / どの列で / 何件 (例: …)`。列や件数がない出来事では、その部分を省く。
  - 例: `[ORDERS_VALIDATE] 日時として読めない値があります / order_approved_at / 3件 (例: 2017-13-01 10:00:00)`
  - 例: `[ORDERS_LOAD] 元の CSV がありません / data/olist/olist_orders_dataset.csv`
- 実行の始めと終わりにも、INFO を1行ずつ書く。終わりの行に、読んだ行数、隔離した行数、書き出した日数と行数、結果(成功 / 停止)を入れる。
- `samples` には、ID と日時と状態の値だけを入れる。住所などの個人情報の列は入れない(どの列が PII かは、フェーズ3の meta / tags で決める)。

### stage と code の一覧(orders)

| stage | code | level | 対応 |
|---|---|---|---|
| ORDERS_LOAD | SOURCE_NOT_FOUND | ERROR | 停止 |
| ORDERS_LOAD | MISSING_COLUMN | ERROR | 停止 |
| ORDERS_VALIDATE | EMPTY_REQUIRED | WARNING | 隔離(order_id か order_purchase_timestamp が空) |
| ORDERS_VALIDATE | DUPLICATE_KEY | WARNING | 隔離(重複したすべての行) |
| ORDERS_VALIDATE | UNPARSABLE_TIMESTAMP | WARNING | 隔離 |
| ORDERS_VALIDATE | UNKNOWN_STATUS | WARNING | 隔離 |
| ORDERS_VALIDATE | QUARANTINE_OVER_LIMIT | ERROR | 停止 |
| ORDERS_WRITE | WRITE_FAILED | ERROR | 停止(それまでに書いた日は残る。同じ期間を再実行すればよい) |

## 隔離

- 場所: `quarantine/olist/orders/run_date=YYYY-MM-DD/batch_id=<batch_id>/orders.parquet`
- 中身: 元の CSV の行を、文字列のまま(型を変えずに)入れ、次の列を足す。
  - `_error_codes`(例: `UNPARSABLE_TIMESTAMP,UNKNOWN_STATUS`)、`_error_columns`、`_batch_id`、`_quarantined_at`
- 隔離した行の直し方: 元データを直して、同じ期間を再実行する。隔離した行は Silver に入っていないので、MERGE で追加される。
- 隔離が0件の実行では、ファイルを作らない。

## 保存期間

| 場所 | 期間 | 理由 |
|---|---|---|
| logs/ | 90日 | 再実行の確認や、傾向の調査に使う |
| quarantine/ | 30日 | 中身は元データの写しなので、調べて直したら不要 |

- 実際の削除は、S3 のライフサイクル(フェーズ1の別のタスク)で行う。

## 確かめ方

- Olist の orders には、隔離に当たる行がない(2026-10-31 確認: 99,441 件で、order_id の空と重複が0、購入日時の空が0、読めない日時が0、order_status は既知の8つだけ)。そのため、本番のデータで隔離を起こすことはしない(障害注入は対象外)。
- 隔離と停止の動きは、pytest で、小さな表(悪い行を数行混ぜたもの)を使って確かめる(フェーズ2の pytest のタスク)。
- 実データでは、隔離0件のときに、ログの終わりの行が正しく出ることを確かめる。

## 今は決めないこと

- 他のテーブル(order_items など)の検証項目: リプレイを全テーブルに広げるときに、この表に行を足す
- 通知(どの level で、誰に知らせるか): Airflow の運用で決める
