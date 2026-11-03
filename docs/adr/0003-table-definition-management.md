# ADR 0003: Bronze は Terraform の外部テーブル、Silver と Gold は dbt で定義する

- 日付: 2026-11-03(詳細は docs/design/orders-vertical-slice.md)
- 状態: 採用(Silver の dbt のモデルは作成中)

## 状況

Glue のテーブルの定義を、どの道具で持つかを決める必要がある。Terraform は設計図とのずれを直す道具で、dbt と SQL はデータを作る道具である。

## 決めたこと

- 中身が動かないもの(バケット、データベース、workgroup、IAM、Bronze)は、**Terraform** で管理する。
- Iceberg のテーブル(Silver、Gold)は、**dbt**(`dbt/models/`)で作る。
- Bronze は Iceberg にせず、Raw の Parquet をそのまま読む**外部テーブル**にする(`terraform/modules/lakehouse_env/bronze.tf`)。パーティションは `ingest_date` の射影で扱い、`MSCK REPAIR TABLE` を不要にする。

## 理由

- Bronze を外部テーブルにする。
  - Raw のファイルは Python が置くだけで、Iceberg のメタデータを更新しない。
  - Bronze は追加だけで、MERGE も DELETE も使わない。
  - Iceberg にすると、Raw と同じデータを2回持つことになる。
- Silver を Iceberg にする。Silver は、同じ `order_id` の注文の出来事が日をまたいで何度も届くので、最新の状態に書き換える(MERGE)必要がある。Parquet のファイルは1行だけを直せないが、Iceberg は台帳でファイルを管理するので、MERGE ができる。
  - 列の追加は、ファイルを書き直さずに行える(`ALTER TABLE … ADD COLUMNS`)。
  - 変わる行がない MERGE では、Iceberg のスナップショットが増えない。同じ日付を再実行しても結果が変わらない(冪等)。
  - 購入月でパーティションを切り、読む量を減らせる。
- Silver を Terraform にしない。
  - Iceberg は、MERGE のたびに Glue の `metadata_location` が書き換わる。Terraform で管理すると設計図とずれ、`apply` が古い状態に戻す恐れがある。
  - 列の追加は `ALTER TABLE … ADD COLUMNS` で行い、テーブルを作り直さない。
  - Silver と Gold はテーブルが増えていく。dbt なら、テーブル同士の依存、テスト、説明(dbt docs)を1か所で持てる。

## あきらめたこと(弱い点)

- テーブルの定義が、Terraform と dbt の2か所に分かれる。どこに何があるかを、設計書で説明する必要がある。
- Silver の定義は、`apply` のような「設計図との差分の確認」が働かない。dbt の仕組み(テスト、`dbt docs`)で補う。
- Terraform の `apply` でデータベースを消すと、中の Silver のテーブルの登録も一緒に消える(データは S3 に残る)。2026-11-03 のモジュール化では、`moved` で移して、これを避けた(ADR 0001)。
