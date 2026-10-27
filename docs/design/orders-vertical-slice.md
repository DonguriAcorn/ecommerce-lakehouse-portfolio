# orders の縦通し設計(最小スライス)

- 作成日: 2026-10-22
- 状態: 合意済み(実装中。Silver のテーブル作成まで済み)

## 目的

Olist の `orders` 1テーブルを、取り込みから Iceberg の Silver まで縦に通し、冪等な再実行ができることを確認する。実装で見つかった課題は、権限設計と IAM に反映する。

## 対象データ

`olist_orders_dataset.csv`(約10万行、8列)。列名と型は、ダウンロード後にヘッダーで確認する。

| 列 | 意味 | Silver での型 |
|---|---|---|
| `order_id` | 注文の ID(主キー) | string |
| `customer_id` | 顧客の ID | string |
| `order_status` | 注文の状態 | string |
| `order_purchase_timestamp` | 購入日時 | timestamp |
| `order_approved_at` | 承認日時 | timestamp |
| `order_delivered_carrier_date` | 配送業者への引き渡し日時 | timestamp |
| `order_delivered_customer_date` | 顧客への配達日時 | timestamp |
| `order_estimated_delivery_date` | 配達予定日 | timestamp |

## リプレイの方針

- 元データは最終的な状態の1回分なので、日付ごとに、その日までに分かっている状態を出力して、日次の更新を再現する。
- 日付 D ごとに、D に何かの出来事(購入、承認、引き渡し、配達)があった注文を、D 時点で分かっている情報だけで出力する。
- 同じ注文が、日をまたいで何度も出力される。これが MERGE(更新)が必要になる理由である。
- キャンセルなどの日付は元データにない。最後に分かっている日付の翌日に、その状態になったことにする。合成であることは、列では持たない(下の「決めたこと」を参照)。

## Raw の置き方(S3)

- 場所: `s3://ecom-lakehouse-dev-<アカウント ID>/raw/olist/orders/ingest_date=YYYY-MM-DD/orders_YYYYMMDD.parquet`
- 形式は Parquet で、1日1ファイル。
- `ingest_date` は、リプレイ上の日付(実際に実行した日ではない)。
- 監査カラムを、ファイルに入れる。

| 列 | 中身 | 例 |
|---|---|---|
| `_ingested_at` | ファイルを書き出した日時(UTC。タイムゾーンの印は付けない) | 2026-10-25 02:47:04.373974 |
| `_source_file` | Raw のファイル名 | orders_20171004.parquet |
| `_batch_id` | 実行の識別子。呼び出す側が決める(run_replay.py では、実行時刻の UTC)。1回の実行で何日分を書いても、同じ値になる | 20261025T065417Z |

- ローカルでは、`data/raw/` の下に S3 と同じ形で書き出してから、アップロードする。

## Silver のテーブル

| 項目 | 内容 |
|---|---|
| 名前 | `ecom_dev_silver.orders`(Iceberg) |
| 主キー | `order_id` |
| 列 | 上の8列 + `_ingested_at`、`_batch_id`、`_ingest_date` |
| パーティション | 購入月(`order_purchase_timestamp` の月) |
| 更新の方法 | `MERGE`(同じ `order_id` なら更新、なければ追加) |

## 冪等性の考え方

- Raw から取り出すとき、同じ `order_id` が複数あれば、`ingest_date` が最も新しいものだけを使う。
- 同じ日付を2回実行しても、同じ結果になる(MERGE の条件で、古い情報で新しい情報を上書きしない)。

## 完了の基準

- 3日分をリプレイして Silver に反映すると、件数と状態が期待どおりになる。
- 同じ日付を再実行しても、Silver の内容が変わらない。

## 今回は決めないこと

- 遅延到着(日付が前後する)のデータの扱い
- Airflow での自動化(縦に通したあとの、次の段階で行う)

## 決めたこと(2026-10-25)

- **合成の印の列は持たない**: Silver の列は、8列 + 監査カラムのままにする。どの注文の状態が合成なのかは、build_events のルールで、必ず同じ結果に再現できる。印が必要になったら、フェーズ3で dbt を使ってルールから作る。
- **`_batch_id` は、関数の外で決める**: 手で実行するときは、run_replay.py が実行時刻の UTC(例: `20261025T065417Z`)を使う。Airflow を使うようになったら、Airflow の実行 ID を渡す。
- **`_ingested_at` は、書き出した時刻にする**: ファイルの中の値は、書き出すときにしか決められない。S3 に置いた時刻が必要なときは、S3 側の更新時刻を見る。
- **タイムゾーンの印を付けない理由**: Athena の `timestamp` 型(タイムゾーンなし)に合わせる。値は UTC にそろえる。

## 決めたこと(2026-10-26)

- **Bronze は外部テーブルにする**: `ecom_dev_bronze.orders` は、Raw の Parquet をそのまま読む外部テーブル。Iceberg にしない理由は、次の3つ。
  - Raw のファイルは Python が置くだけで、Iceberg のメタデータを更新しない。
  - Bronze は追加だけで、MERGE や DELETE を使わない。
  - Iceberg にすると、Raw と同じデータを2回持つことになる。
- **パーティションは射影で扱う**: `ingest_date`(string、`yyyy-MM-dd`)を、範囲 2016-09-01〜2018-12-31 の1日刻みで射影する。日付が増えても、パーティションの登録(`MSCK REPAIR TABLE`)はいらない。
- **定義は Terraform で管理する**: `terraform/envs/dev/bronze.tf`(`aws_glue_catalog_table`)。バケット名は参照で入るので、アカウント ID をファイルに書かない。コンソールでは変更しない。
- **列が増えたとき(将来の手順)**:
  - Bronze: 列の一覧の最後に足す(`update in-place`)。古いファイルの値は NULL として読めるので、Raw は書き換えない。
  - Silver: `ALTER TABLE … ADD COLUMNS` で列を足す。Iceberg は、データのファイルを書き直さない。過去の値が必要なら、backfill する。
  - backfill の注意: MERGE は古い `ingest_date` で上書きしないので、古い日付を再実行しても値は入らない。backfill は、Bronze から Silver を作り直す(full refresh)か、専用の更新で行う。
- **Silver の定義は、SQL ファイルで管理する**: `sql/silver/create_orders.sql`(`CREATE TABLE IF NOT EXISTS`)を、transform ロールで、AWS CLI(`aws athena start-query-execution`)から実行する。Terraform にしない理由は、次の3つ。
  - Iceberg は、更新(MERGE)のたびに、Glue の `metadata_location` が書き換わる。Terraform で管理すると、設計図とのずれになり、`apply` で古い状態に戻す恐れがある。
  - 列の追加は `ALTER TABLE … ADD COLUMNS` で行い、テーブルを作り直さない。
  - silver と gold は、テーブルが増えていく。フェーズ3で dbt に移すので、dbt と同じ SQL の形にしておく。
  - 役割の分け方: 中身が動かないもの(バケット、データベース、workgroup、IAM、Bronze)は Terraform。Iceberg のテーブルは SQL(のちに dbt)。
- **Silver の設定**: 場所は `iceberg/silver/orders/`。パーティションは `month(order_purchase_timestamp)`(購入日時は値が変わらないので、更新で行が移動しない)。形式は Parquet、圧縮は zstd。`vacuum_*` と `optimize_*` は既定値のままにし、運用の段階(Airflow)で決める。
- **アカウント ID の扱い**: SQL ファイルでは、バケット名を `__LAKE_BUCKET__` という目印にし、実行するときに `sed` で置き換える。同時に、`--` のコメント行を取り除く(Athena の DDL は、先頭のコメントでエラーになることがあるため)。
- **Silver に `_ingest_date`(date)を持つ**: MERGE で「古い情報で上書きしない」を判定するための、リプレイ上の日付。`_ingested_at` は書き出した時刻なので、古い日付を書き出し直すと新しく見えてしまい、判定に使えない。dev では `ALTER TABLE … ADD COLUMNS` で足し、`create_orders.sql` にも同じ列を最後に足した。
- **MERGE の条件**: `sql/silver/merge_orders.sql`。材料は、指定した `ingest_date` の範囲から、`row_number()` で注文ごとに最新の1行だけにする。更新は `s._ingest_date > t._ingest_date` のときだけ(`>=` にしない)。同じ日付の再実行では何も変わらない。同じ日付の訂正版を反映するときは、full refresh で行う。材料にない Silver の行は消さない(毎日の材料は、出来事のあった注文だけのため)。

## 検証の結果(2026-10-27)

縦通しの完了の基準を、`sql/silver/check_orders_rerun.sql` で確認した(Athena のクエリエディタ、workgroup `ecom-dev`)。

- **再実行の内容**: 最初の MERGE(10-04〜06)のあとに、10-04 だけを1回、10-04〜06 を3回、再実行した(すべて SUCCEEDED)。
- **スナップショットの数は 1**(最初の MERGE、2026-10-26 08:08 UTC): 再実行では、更新も挿入も0行だった。Athena は、変わる行がない MERGE ではスナップショットを作らない。
- **基準との差分**(EXCEPT の両方向): 0 行。
- **件数**: 1,308 行で、order_id の種類の数も 1,308(重複なし)。
- **protected_orders**: 175。10-04 にも出てくる注文のうち、10-05 以降の情報を持つ注文。10-04 だけを再実行しても、古い状態に戻らなかった。
- **leaked_rows**: 0。承認日、引き渡し日、配達日が、取り込み日より後の行はない。
- **結論**: 「完了の基準」の2項目を満たしたので、orders の縦通しを完了とする。
