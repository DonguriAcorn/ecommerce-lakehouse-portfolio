# Iceberg の整理(OPTIMIZE / VACUUM)

判断の理由は ADR 0013。ここでは、何が起きるかと、流し方をまとめる。

## なぜ要るか

Iceberg は、ファイルを書き換えず、新しいファイルを作る。古いファイルは、過去の版(スナップショット)から使われるうちは消さない。dbt の MERGE を窓ごとに何度も流すと、小さなファイルと古い版が増える。

- OPTIMIZE: 小さなファイルを、大きなファイルにまとめる(新しいファイルを作る。まとめる前のファイルは残る)。
- VACUUM: 期限を過ぎた版と、どの版からも使われなくなったファイルを、S3 から消す。消した版には戻れない。

順番は、OPTIMIZE → VACUUM。

## 設定

| 項目 | 値 | 意味 |
|---|---|---|
| `vacuum_max_snapshot_age_seconds` | 604800(7日) | これより古いスナップショットを、VACUUM が消す |
| `vacuum_min_snapshots_to_keep` | 1(既定) | 期限を過ぎても、最新から数えて最低 1 つは残す |
| OPTIMIZE の方式 | `BIN_PACK` | 小さいファイルを詰める(Athena で使える方式) |

`vacuum_max_snapshot_age_seconds` は、整理のスクリプトが、毎回 `ALTER TABLE ... SET TBLPROPERTIES` で入れ直す(同じ値を何度入れても同じ)。

## 流し方

対象は Silver の7表(`ingestion/iceberg_maintenance.py` の `TABLES`)。1表ずつ、前を測る → ALTER → OPTIMIZE → VACUUM → 後を測る、の順で流す。

1. 流すタイミング: 全期間のバックフィルなど、MERGE をたくさん流したあと。`olist_daily` が動いていないときに流す(MERGE と重ねると、書き込みが衝突することがある)。
2. 一時キーを発行し直す: `bash airflow/refresh_credentials.sh`(期限は 1 時間)。
3. Airflow を起動する: `docker compose -f airflow/docker-compose.yaml up -d`。
4. 新しい DAG のときだけ: 既定で一時停止なので、`airflow dags unpause iceberg_maintenance`。読み込みが遅いときは `airflow dags reserialize`。
5. 実行する: `airflow dags trigger iceberg_maintenance`。ログに、表ごとの「前: ファイル N 個 / バイト / スナップショット N 個」と「後: …」が出る。
6. 1表だけ試すとき: `uv run python -m ingestion.iceberg_maintenance --table orders_from_events`(ロールは `AWS_PROFILE=ecom-dev-transform`)。

## 確かめ方

整理の前後で、`orders_from_events` の行数と、業務の8列をつないだ全行の `checksum` が同じことを確かめる。

```
select count(*), to_hex(checksum(concat_ws('|', order_id, customer_id, order_status,
  cast(order_purchase_timestamp as varchar), cast(order_approved_at as varchar),
  cast(order_delivered_carrier_date as varchar), cast(order_delivered_customer_date as varchar),
  cast(order_estimated_delivery_date as varchar)))) from ecom_dev_silver.orders_from_events
```

2026-11-14 の値は、99,441 行、`2DDE47A22018FB6F`。以前の記録(`D021FB02FF4384F1`)とは式が違うので、比べられない。前後の比較には、同じ式を使う。

## 2026-11-14 の結果

`orders_from_events`(購入月ごとのパーティション。月は 25 個):

| | 前 | OPTIMIZE のあと | VACUUM のあと |
|---|---|---|---|
| 現在の版のデータファイル | 61 | 25 | 25 |
| S3 の Parquet の総数 | 109 | 134 | 25 |
| スナップショット | 9 | 10 | 1 |
| 行数・指紋 | 99,441 / `2DDE…` | 同じ | 同じ |

- OPTIMIZE のあと、ファイルが 25 個になったのは、パーティション(月)ごとに詰めるため。
- OPTIMIZE のあとに S3 の Parquet が増えるのは、新しいファイルを作り、まとめる前のものは VACUUM まで残るため。
- 7表を DAG で流した結果: `order_items` は 2 → 1 ファイル。ほかの 5 表は変化なし。`order_items` と `reviews` の古いスナップショット(2026-11-07 の 07:25〜07:26 UTC)は、実行時点で 7 日に届いていないので、残った。
- 7表すべてに、`vacuum_max_snapshot_age_seconds = 604800` が入った。

## 注意

- S3 のバージョニングで、消えたファイルは非現行の版として 14 日残る。S3 の量が減るのは、約 14 日後。Iceberg のスナップショット(テーブルの履歴)と、バージョニング(ファイルの履歴)は、別の仕組み。
- テーブルの置き場は、`iceberg/<DB>/<表>/<UUID>/`(dbt-athena が付ける)。`data/` と `metadata/` がこの下にある。作り直すと、新しい UUID のフォルダができるので、古いフォルダが残っていないかを確かめる。
- Iceberg にとって、フォルダの名前に意味はない。どのファイルがどの版に入るかは、`metadata/` の台帳が持つ。
- 新しい DAG は、既定で一時停止の状態で作られる。解除しないと、手動で呼んでも待ち(queued)のまま動かない。
