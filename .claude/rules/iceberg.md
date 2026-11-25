---
paths:
  - "dbt/models/silver/**"
  - "dbt/models/gold/**"
  - "dbt/macros/silver_latest.sql"
  - "ingestion/iceberg_maintenance.py"
  - "airflow/dags/iceberg_maintenance.py"
  - "docs/design/iceberg-maintenance.md"
  - "docs/adr/**"
---

# Iceberg の設定の説明

Iceberg はこのポートフォリオの中心の技術なので、ユーザーは設定を細かく理解したい(2026-10-26 の依頼)。

- Iceberg の設定(`table_type`、`location`、パーティションの変換、テーブルのプロパティ、`incremental` と `merge`、スナップショット、`OPTIMIZE` と `VACUUM`)を示すときは、項目ごとに次の3つを書く。
  - 何をするか
  - なぜその値か
  - 別の値にした場合、何が変わるか
- たとえ(例: 図書館の「棚」と「目録」)と、実データの例も使う。
- Iceberg のスナップショット(テーブルの履歴)と、S3 のバージョニング(ファイルの履歴)は、役割が違うことを区別して説明する。
