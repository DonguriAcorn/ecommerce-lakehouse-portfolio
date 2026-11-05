# orders のパイプライン設計

- 更新日: 2026-11-03
- 状態: ソース、Raw、Bronze は実装済み。Silver は dbt に移す途中(docs/tasks.md のフェーズ2「orders の Raw をイベント単位にする」の 2c)
- 判断の理由: ADR 0003(テーブル定義の管理)、ADR 0004(Raw で型を付ける)、ADR 0010(イベント単位の Raw)

## 流れ

```
元の CSV ─(simulator/make_source_events.py、1回だけ)→ data/source/orders_events/arrival_date=…/*.jsonl
         ─(ingestion/run_ingest.py、1日ずつ)→ data/raw/olist/orders_events/ingest_date=…/*.parquet
         ─(aws s3 sync、ingest ロール)→ s3://…/raw/olist/orders_events/
         ─(外部テーブル、Terraform)→ ecom_dev_bronze.orders_events
         ─(dbt、transform ロール)→ ecom_dev_silver.orders_from_events(Iceberg)
```

- `simulator/` は業務システムの代わりで、パイプラインではない。パイプラインは `ingestion/` と dbt。
- 出来事の作り方と件数は、orders-data-profile.md を参照。

## 届くファイル(ソース)

- 場所: `data/source/orders_events/arrival_date=YYYY-MM-DD/orders_events_YYYYMMDD.jsonl`(Git の管理外)
- 形式: JSON Lines(1行 = 1つの出来事)。日時は文字列(`YYYY-MM-DD HH:MM:SS`)。
- 列と書式は、受け取り側の `ingestion/schema.py` で決める。simulator はそれに合わせる。
- `arrival_date` は届いた日。ふつうは出来事が起きた日と同じで、遅れて届く出来事だけ後ろの日になる(`event_time` は変えない)。
- 期間: 2016-09-04 〜 2018-10-18 の 775 日。出来事のない日(79 日)も、空のファイルを置く。最後の購入日(2018-10-17)にキャンセルされた注文の final が、翌日に届くため、最後の日は 2018-10-18。
- 遅延の再現: `--late-share` と `--late-days` で、一部の出来事だけ後ろの日に入れる。対象は sha256 と固定の seed で決める(何度作っても同じ)。遅延ありのソースは、別のフォルダ(`--out`)に作る。
- 作り直すとき: 前のファイルが残っていると止まる(同じ出来事が2つの日に入るのを防ぐ)。中身を確かめてから消す。

## Raw の置き方(S3)

- 場所: `s3://ecom-lakehouse-dev-<アカウント ID>/raw/olist/orders_events/ingest_date=YYYY-MM-DD/orders_events_YYYYMMDD.parquet`
- 形式は Parquet で、1日1ファイル。`ingest_date` は取り込んだ日で、届いた日(`arrival_date`)と同じ。
- ローカルの `data/raw/` に S3 と同じ形で書き、`aws s3 sync` で上げる(ingest ロール。Raw の読み書きだけができる)。
- 列は、届くファイルの9列(型を付ける)+ 監査カラム3つ。型は `ingestion/schema.py` の registry(`ORDERS_EVENTS`)に書き、`ingestion/raw_writer.py` の `raw_schema` が Parquet の型にして明示する(出来事のない日の 0 行のファイルも、ほかの日と同じ型になる)。受付の流れは全表で共通(replay-tables.md)。

| 列 | 型 | 中身 |
|---|---|---|
| `order_id`、`customer_id` | string | 注文と顧客の ID |
| `order_purchase_timestamp`、`order_estimated_delivery_date` | timestamp | 購入日時と配達予定日(注文の属性。どの行にも入る) |
| `event_type` | string | created / approved / shipped / delivered / final |
| `event_rank` | int(int32) | 段階の順位 0〜4 |
| `event_time` | timestamp | 出来事の日時(時刻付き) |
| `order_status` | string | その出来事の時点で到達した状態 |
| `is_synthetic` | boolean | 時刻を作った final なら true |

監査カラム:

| 列 | 中身 | 例 |
|---|---|---|
| `_ingested_at` | ファイルを書き出した日時(UTC。タイムゾーンの印は付けない) | 2026-11-03 06:40:12.123456 |
| `_source_file` | Raw のファイル名 | orders_events_20171004.parquet |
| `_batch_id` | 実行の識別子。手で実行するときは run_ingest.py が実行時刻の UTC を使う。Airflow を使うようになったら、Airflow の実行 ID を渡す | 20261103T064012Z |

- タイムゾーンの印を付けない理由: Athena の `timestamp` 型(タイムゾーンなし)に合わせる。値は UTC にそろえる。
- `_ingested_at` は書き出した時刻。S3 に置いた時刻が必要なときは、S3 側の更新時刻を見る。

## Bronze

- `ecom_dev_bronze.orders_events` は、Raw の Parquet をそのまま読む外部テーブル。Iceberg にしない理由は、次の3つ。
  - Raw のファイルは Python が置くだけで、Iceberg のメタデータを更新しない。
  - Bronze は追加だけで、MERGE や DELETE を使わない。
  - Iceberg にすると、Raw と同じデータを2回持つことになる。
- パーティションは射影で扱う: `ingest_date`(string、`yyyy-MM-dd`)を、範囲 2016-09-01〜2018-12-31 の1日刻みで射影する。日付が増えても、パーティションの登録(`MSCK REPAIR TABLE`)はいらない。
- 定義は Terraform で管理する: `terraform/modules/lakehouse_env/bronze.tf`。バケット名は参照で入るので、アカウント ID をファイルに書かない。コンソールでは変更しない。
- 列が増えたとき: 列の一覧の最後に足す(`update in-place`)。古いファイルの値は NULL として読めるので、Raw は書き換えない。

## Silver(dbt、これから作る)

| 項目 | 内容 |
|---|---|
| 名前 | `ecom_dev_silver.orders_from_events`(Iceberg。2c で決定。「イベントから作った」ことが名前で分かる) |
| 主キー | `order_id`(1行 = 1つの注文の、いまの状態) |
| 列 | 元の CSV と同じ8列 + 監査カラム(`_last_ingest_date` など) |
| パーティション | 購入月(`month(order_purchase_timestamp)`)。購入日時は値が変わらないので、更新で行が移動しない |
| 形式 | Parquet、zstd。置き場所は `iceberg/` の下(`athena-results/` はライフサイクルで消えるため) |
| 更新の方法 | dbt の incremental + merge(`unique_key='order_id'`) |

- 畳み方: 窓(`start_date` 〜 `end_date`)に現れた注文について、その注文の全イベント(`ingest_date <= end_date`。開始日の制限なし)を読む。状態は `event_rank` の大きい順(同じなら `event_time` の新しい順)で最新の出来事から取る。承認日時などは、`event_type` ごとの `event_time` を取り出して1行にする。
- 古い情報で上書きしない: その注文のイベントの `ingest_date` の最大を `_last_ingest_date` として持ち、Silver の値より新しいときだけ MERGE に通す。同じ日の再実行は変化 0。
- 同じ日の訂正: 上のガードで入らないので、Silver を全期間の窓で作り直して対応する。
- 作り直しの事故を防ぐ: モデルに `full_refresh=false` を入れる(狭い窓で作り直すと、その窓の分だけになるため)。
- 定義を Terraform にしない理由: Iceberg は更新のたびに Glue の `metadata_location` が書き換わり、Terraform で管理すると設計図とのずれになるため。中身が動かないもの(バケット、DB、workgroup、IAM、Bronze)は Terraform、Iceberg のテーブルは dbt。
- 接続: `dbt/profiles.yml`。バケット名は環境変数 `LAKE_BUCKET` から読み、アカウント ID をファイルに書かない。

## 答え合わせ用のコピー(2026-11-03 に差分 0 を確認し、DROP 済み)

- `ecom_dev_silver.orders_baseline_20261103`(Iceberg、1,308 行、置き場所 `iceberg/silver/orders_baseline_20261103/`): 10-04〜06 の 3 日分の、注文ごとの状態の正解。dbt の Silver と、業務の列だけで EXCEPT して差分 0 を確かめるのに使う。
- 差分 0 を確かめた直後に消す(Athena で `DROP TABLE`。Iceberg の DROP はデータも消し、戻せない)。

## 消したファイルを戻すとき(S3)

lake バケットはバージョニングが有効なので、`aws s3 rm` で消したファイルは、14 日以内なら戻せる(消すと「削除マーカー」が付くだけで、前の版は非現行として残る)。戻すには、削除マーカーを消す。

```bash
# 1. 削除マーカーの一覧(Key と VersionId を見る)
aws s3api list-object-versions --bucket <bucket> --prefix <消したプレフィックス> --query 'DeleteMarkers[].[Key,VersionId]' --output text
# 2. 削除マーカーを1つずつ消す(前の版が、現在の版に戻る)
aws s3api delete-object --bucket <bucket> --key <Key> --version-id <VersionId>
```

- Iceberg のテーブルの DROP と、ローカルの `data/` の削除は戻せない。

## まだ決めていないこと

- (決定 2026-11-04)全期間を流すときの窓の幅: orders は Raw が 36 MB なので、全期間 1 回で足りる。Airflow のバックフィルでは、日次・月次など、運用の形で決める
- (決定 2026-11-04)遅延ありのソースの置き場所と読み方: 本番の Raw と Silver は上書きしない。Raw は `raw/olist_late/orders_events/`、Bronze は別テーブル `orders_events_late`(Terraform)、Silver は別テーブル `orders_from_events_late`(dbt の変数で読む元を切り替える)。確認が終わったら消す。
- Iceberg の expire / vacuum / optimize の設定(Airflow の運用のタスクで決める)
