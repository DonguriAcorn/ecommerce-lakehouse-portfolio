# ADR 0010: orders の Raw を、注文の出来事を1行ずつ並べたイベント単位にする

- 日付: 2026-11-03
- 状態: 採用(Silver は実装中)。Raw の形式、型を付ける場所、監査カラムは ADR 0004
- レビュー: plan-critic による3回のレビュー済み(2026-11-03)

## 状況

Olist の元データは、最終状態の CSV 1回分である。日次の取り込みと更新(MERGE)を練習するには、日々データが届く形を再現する必要がある。実務では、アプリが出すイベントのログや CDC の変更ログなど、「出来事を1件ずつ」届けて積む形が多い。Raw を実務に近い形にし、Silver で「いまの状態」を作る流れ(積む → 畳む)を学ぶ。

## 決めたこと

- **1行 = 注文の1つの出来事。** 列は `order_id`、`customer_id`、`order_purchase_timestamp`、`order_estimated_delivery_date`、`event_type`(created / approved / shipped / delivered / final)、`event_rank`(0〜4。既存の段階の順位)、`event_time`(時刻付き)、`order_status`(その出来事の時点で到達した状態)、`is_synthetic`、監査カラム3つ。`customer_id`、購入日時、配達予定日は注文の変わらない属性で、どの行にも入れる(窓に created がない注文でも、NULL にならないようにするため)。
- **`event_date`(日付)と `event_time`(時刻付き)を分ける。** `ingest_date` は「届いた日」で、通常は出来事が起きた日(`event_time` の日付)と同じ。遅れて届くイベントだけ、`ingest_date` が後ろにずれる。`event_time` は変えない。
- **合成の印:** `is_synthetic` は、日時の列がない最終状態(canceled など)の `final` の `event_time` を、作って入れたときだけ true。
- **置き場所:** `raw/olist/orders_events/ingest_date=YYYY-MM-DD/`。
- **Silver の畳み方:** 窓に現れた注文について、その注文の全イベント(`ingest_date <= end_date`。開始日の制限なし)を読む。`row_number() over (partition by order_id order by event_rank desc, event_time desc)` で最新を選び、`order_status` を決める。承認日時などは、`event_type` ごとの `event_time` を取り出して1行にする。時刻と順位が食い違っても、順位を優先する(Olist には、引き渡しが承認より前の注文が 1,359 件、配達が引き渡しより前の注文が 23 件あるため。orders-data-profile.md)。
- **古いデータで上書きしない:** 畳んだ結果の `_last_ingest_date`(その注文のイベントの `ingest_date` の最大)が、Silver の値より新しいときだけ MERGE に通す。同じ日の再実行は変化 0。同じ日の Raw を直して流し直した訂正は、Silver を作り直して対応する。
- **Silver の作り直しを窓の誤りで起こさない:** モデルに `full_refresh=false` を入れる。作り直すときは、全期間の窓を渡す手順で行う。
- **ソースと取り込みを分ける:** コードのフォルダも分ける。`simulator/` は業務システムの代わりで、パイプラインではない。`simulator/make_source_events.py` が CSV から全期間の出来事を1回だけ作り、`data/source/orders_events/arrival_date=YYYY-MM-DD/*.jsonl`(JSON Lines、日時は文字列)に置く。出来事のない日も空のファイルを置く。`ingestion/` はパイプラインで、`ingestion/run_ingest.py` が、その日に届いたファイルを読み、検証・隔離・型の付与・監査カラムをして Raw に書くだけで、出来事を作らない。ファイルがない日は止める。`ingest_date` = `arrival_date`。届くファイルの列と書式は、受け取り側の `ingestion/schema.py` で決め、`simulator/` はそれに合わせる。
- **全期間:** 2016-09-04〜2018-10-18(775 日)。最後の購入日(2018-10-17)にキャンセルされた注文の最終状態が、翌日の 2018-10-18 に届くため。
- **遅延の再現:** ソースを作るときに `--late-share` と `--late-days` を渡し、一部の出来事だけ後の `arrival_date` のフォルダに入れる(`event_time` は変えない)。取り込み側は遅延を知らない。対象は `hashlib` の sha256 と固定の seed で決め(Python の `hash()` は実行ごとに変わるので使わない)、何度作っても同じになる。遅延ありのソースは、別のフォルダ(`--out`)に作る。前のファイルが残っていると止まる(同じ出来事が2つの日に入るのを防ぐ)。
- **答え合わせ:** AWS 上の比較用コピー `ecom_dev_silver.orders_baseline_20261103` と、元の CSV の `order_status` で行う。日ごとに畳んだ状態が正しいかは、pytest(`tests/test_orders_events.py`)で、期待する状態を直接書いて確かめる。

## 理由

- 積んで畳む流れは、実務の CDC やイベントログと同じで、Silver の設計(順位で選ぶ、ガード、冪等)を学べる。
- 全行に属性を持たせると、Silver が窓の外の created を探さなくて済み、再実行しても結果が実行時の Bronze の内容で変わらない。
- 遅延を決定的にすると、再実行しても同じ結果になり、検証できる。

## あきらめたこと(弱い点)

- 属性を全行に持たせるので、行は冗長になる(非正規化)。元が CSV の1行なので、食い違いは通常起きない。pytest で確かめる。
- 厳密な「新しい日のときだけ更新」のガードのため、同じ `ingest_date` の訂正は Silver に入らない。作り直しで対応する。
- リプレイの共通化(全9テーブル)は、「スナップショット型」と「イベント型」の2つの形を扱う設計になる。order_items など他のテーブルをどちらにするかは、共通化のときに決める。
- 全期間を1日ずつ流すと、MERGE が約770回になる。週か月の窓で流す。Iceberg のスナップショットと小さなファイルが増えるので、expire / vacuum の運用は、Airflow の運用のタスクで扱う。
- Silver の切り替えは、Athena の Iceberg で名前の入れ替えができるか未確認のため、新しい名前に切り替える形にする。
