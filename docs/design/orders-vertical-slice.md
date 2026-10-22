# orders の縦通し設計(最小スライス)

- 作成日: 2026-10-22
- 状態: 合意済み(実装前)

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
- キャンセルなどの日付は元データにない。最後に分かっている日付の翌日に、その状態になったことにする(合成であることを記録に残す)。

## Raw の置き方(S3)

- 場所: `s3://ecom-lakehouse-dev-<アカウント ID>/raw/olist/orders/ingest_date=YYYY-MM-DD/orders_YYYYMMDD.parquet`
- 形式は Parquet で、1日1ファイル。
- `ingest_date` は、リプレイ上の日付(実際に実行した日ではない)。
- 監査カラム `_ingested_at`、`_source_file`、`_batch_id` をファイルに入れる。

## Silver のテーブル

| 項目 | 内容 |
|---|---|
| 名前 | `ecom_dev_silver.orders`(Iceberg) |
| 主キー | `order_id` |
| 列 | 上の8列 + `_ingested_at`、`_batch_id` |
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
- Bronze の Glue テーブル定義(Raw を読むための外部テーブルは、実装のステップで作る)
