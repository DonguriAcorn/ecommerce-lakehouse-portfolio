# エラーの設計(取り込み)

- 更新日: 2026-11-03
- 状態: 実装済み(`ingestion/ingest_events.py`、`ingestion/quarantine.py`、`ingestion/run_log.py`)

## 目的と範囲

取り込みの Python(`ingestion/`)が、問題を見つけたときに、どう止め、何を記録し、悪い行をどこに置くかを決める。

- 対象: 届いたファイル(`data/source/orders_events/`)を読んでから、Raw の Parquet を書き出すまで(`ingestion/run_ingest.py`)。
- 対象外:
  - 届くファイルを作る側(`simulator/`)。業務システムの代わりなので、パイプラインのエラーとしては扱わない
  - dbt の失敗(Airflow の運用で、`run_results.json` の要点を logs/ に書く。tasks.md のフェーズ2)
  - リトライと失敗の通知(Airflow の運用で決める)
  - S3 へのアップロード(今は AWS CLI で行う。Python から S3 に直接書くようになったら、見直す)

## 用語

| 用語 | 意味 | 例 |
|---|---|---|
| 停止 | 実行全体を止める。止めた日より前の日の Raw は残る | その日のファイルが届いていない |
| 隔離 | 悪い行だけを quarantine/ に移し、残りの行は通す | event_time が日時として読めない行 |
| batch_id | 1回の実行の識別子。Raw の監査カラム `_batch_id` と同じ値を使う | 20261103T064012Z |
| run_date | 実行した日(UTC)。取り込んだ日 `ingest_date` とは別 | 2026-11-03 |

## Python と dbt test の分担

| 見るもの | 担当 | 理由 |
|---|---|---|
| その日のファイルがあるか、読めるか、必要な列(9列)があるか | Python(停止) | ないと、処理が始められない。業務システムは毎日ファイルを届ける想定(出来事のない日は空のファイル) |
| order_id、customer_id、order_purchase_timestamp、event_type、event_rank、event_time、order_status、is_synthetic が空(配達予定日だけは空でも通す) | Python(隔離) | Silver で注文を畳めない、または型を付けられない |
| 同じファイルの中で (order_id, event_type) が重複 | Python(隔離) | 出来事のキーが一意でなくなる |
| 日時の列(購入日時、配達予定日、event_time)が、日時として読めない | Python(隔離) | 型を付ける段階で、実行全体が止まってしまう |
| event_type が、既知の5つ以外 | Python(隔離) | Silver の畳み方が、この値で決まる |
| event_type と event_rank が食い違う(例: shipped なのに順位 0) | Python(隔離) | 順位は Silver で最新の出来事を選ぶ要。食い違うと状態を取り違える |
| is_synthetic が true / false ではない(文字の "false" など) | Python(隔離) | 文字のまま bool に変えると、"false" が true に化ける |
| 日をまたいだ (order_id, event_type) の重複、Silver の一意性、NULL、許される値 | dbt test | 1日分のファイルだけでは分からない。テーブルに入ったあとの状態を見る |
| 日付の前後関係、delivered なのに配達日時が空 | dbt test(警告) | 業務のルール。行を止める理由にはしない |

- 既知の event_type と順位の組(`EVENT_TYPE_RANKS`)と、届くファイルの列は、`ingestion/schema.py` で決める。

## 停止と隔離の基準

- 停止する場合
  - その日のファイルがない、または JSON として読めない(`SOURCE_NOT_FOUND`)
  - 必要な列(9列)が1つでも欠けている(`MISSING_COLUMN`)
  - その日の隔離した行が、その日の全体の 1% を超える(`QUARANTINE_OVER_LIMIT`。元データ側の大きな異常とみなす)
- 隔離する場合: 上の分担の表で「Python(隔離)」とした6つ。1行に複数の問題があっても、隔離は1回だけにし、理由はすべて記録する。
- 検証は、1日分のファイルを読んだ直後に、その日の全行まとめて行う。止まった日の Raw は書かない。それより前の日の Raw は残るので、同じ期間を再実行すればよい(同じ日は上書きされる)。
- 終了コード: 正常(隔離が 1% 以下を含む)は 0、停止は 1。Airflow は、0 以外を失敗として扱う。

## ログ

- 場所: `logs/ingest/olist/orders_events/run_date=YYYY-MM-DD/batch_id=<batch_id>/events.jsonl`
- 形式: JSON Lines(1行 = 1つの出来事)。Athena で集計できるように、項目に分けて持ち、`message` は項目から組み立てる。
- ローカルでは `data/logs/` の下に同じ形で書く。画面(標準出力)にも `message` を出す。

| 項目 | 必須 | 意味 | 例 |
|---|---|---|---|
| `ts` | ○ | 出来事の日時(UTC) | 2026-11-03T06:40:12Z |
| `level` | ○ | INFO / WARNING / ERROR | ERROR |
| `batch_id` | ○ | 実行の識別子 | 20261103T064012Z |
| `table` | ○ | 対象のテーブル | orders_events |
| `stage` | ○ | 処理の段階 | EVENTS_VALIDATE |
| `code` | ○ | 出来事の種類(決まった名前) | UNPARSABLE_TIMESTAMP |
| `ingest_date` | | 取り込んだ日(日ごとの処理のとき) | 2017-10-04 |
| `column` | | 関係する列 | event_time |
| `count` | | 件数 | 3 |
| `samples` | | 値の例(最大3件) | ["2017-13-45 99:00:00"] |
| `message` | ○ | 人が読む文 | 下を参照 |

- `message` の形: `[段階] 何が / どの列で / 何件 (例: …)`。列や件数がない出来事では、その部分を省く。
  - 例: `[EVENTS_VALIDATE] 日時として読めない値があります / event_time / 3件 (例: 2017-13-45 99:00:00)`
  - 例: `[EVENTS_LOAD] 届いたファイルがありません / data/source/orders_events/arrival_date=2017-10-04/orders_events_20171004.jsonl`
- 実行の始めと終わりにも、INFO を1行ずつ書く。終わりの行に、書き出した日数と行数、隔離した行数、結果(成功 / 停止)を入れる。
- `samples` には、ID と日時と種類の値だけを入れる。空の値と、2列の組(キーの重複)には例を付けない。住所などの個人情報の列は入れない(どの列が PII かは、フェーズ3の meta / tags で決める)。

### stage と code の一覧(orders_events)

| stage | code | level | 対応 |
|---|---|---|---|
| EVENTS_RUN | RUN_START | INFO | 実行の始め |
| EVENTS_RUN | RUN_END | INFO | 実行の終わり(結果、書き出した日数と行数、隔離行数) |
| EVENTS_LOAD | SOURCE_NOT_FOUND | ERROR | 停止(ファイルがない、または読めない) |
| EVENTS_LOAD | MISSING_COLUMN | ERROR | 停止 |
| EVENTS_VALIDATE | EMPTY_REQUIRED | WARNING | 隔離 |
| EVENTS_VALIDATE | DUPLICATE_KEY | WARNING | 隔離(重複したすべての行) |
| EVENTS_VALIDATE | UNPARSABLE_TIMESTAMP | WARNING | 隔離 |
| EVENTS_VALIDATE | UNKNOWN_EVENT_TYPE | WARNING | 隔離 |
| EVENTS_VALIDATE | INVALID_EVENT_RANK | WARNING | 隔離 |
| EVENTS_VALIDATE | INVALID_FLAG | WARNING | 隔離 |
| EVENTS_VALIDATE | QUARANTINE_OVER_LIMIT | ERROR | 停止 |
| EVENTS_WRITE | WRITE_FAILED | ERROR | 停止(それまでに書いた日は残る。同じ期間を再実行すればよい) |

## 隔離

- 場所: `quarantine/olist/orders_events/run_date=YYYY-MM-DD/batch_id=<batch_id>/orders_events.parquet`
- 中身: 届いた行を、すべて文字列にそろえて入れ(型の混ざった値でも書けるように)、次の列を足す。
  - `_error_codes`(例: `UNPARSABLE_TIMESTAMP,UNKNOWN_EVENT_TYPE`)、`_error_columns`、`_batch_id`、`_quarantined_at`
- 隔離した行の直し方: 届いたファイルを直して(実務では、送る側に直してもらって)、同じ期間を再実行する。
- 隔離が0件の日は、ファイルを作らない。

## 保存期間

| 場所 | 期間 | 理由 |
|---|---|---|
| logs/ | 90日 | 再実行の確認や、傾向の調査に使う |
| quarantine/ | 30日 | 中身は届いたファイルの写しなので、調べて直したら不要 |
| athena-results/ | 7日 | クエリ結果の一時ファイルで、再実行すれば作り直せる |

- 実際の削除は、S3 のライフサイクル(terraform/modules/lakehouse_env/s3.tf)で行う。

## 確かめ方

- 実データ(全期間 775 日、394,713 件)では、隔離に当たる行がない(2026-11-03 確認)。そのため、本番のデータで隔離を起こすことはしない(障害注入は対象外)。
- 隔離と停止の動きは、pytest(`tests/test_source_events.py`)で、小さな表(悪い行を数行混ぜたもの)を使って確かめる。ファイルがない日、空のファイル、知らない種類、読めない日時、キーの重複、種類と順位の食い違い、文字の印、空の順位、型の混ざった隔離の書き出し、上限を超えたときの停止。

## 今は決めないこと

- 他のテーブル(order_items など)の検証項目: リプレイを全テーブルに広げるときに、この表に行を足す
- 通知(どの level で、誰に知らせるか): Airflow の運用で決める
