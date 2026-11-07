# Olist の Raw(Parquet)を、そのまま読む外部テーブル(ADR 0003)。7表を1つの一覧から作る
# 列の名前と型は、ingestion/schema.py(registry)と、raw_writer.py が書く Parquet の型に合わせる
# (Athena の Parquet は列名で読むので、名前が1文字でも違うと、その列は全行 NULL になる)
locals {
  # Raw の置き場所の共通部分。表ごとに <表の名前>/ が続く
  bronze_raw_prefix = "s3://${aws_s3_bucket.lake.bucket}/raw/olist"

  # 全表の最後に付く監査カラム(raw_writer.py が足す)
  bronze_audit_columns = [
    { name = "_ingested_at", type = "timestamp" }, # Raw に書いた日時
    { name = "_source_file", type = "string" },    # 元のファイル名
    { name = "_batch_id", type = "string" },       # 取り込みの実行の ID
  ]

  # 表の名前 → 説明と、業務の列(監査カラムは下で足す)
  bronze_tables = {
    # 出来事型(ADR 0010)。説明を日本語に変えたので、plan に「変更」が1件出る(その場での書き換え)
    orders_events = {
      description = "Olist の注文の出来事(1行 = 1つの出来事)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "order_id", type = "string" },
        { name = "customer_id", type = "string" },
        { name = "order_purchase_timestamp", type = "timestamp" },
        { name = "order_estimated_delivery_date", type = "timestamp" },
        { name = "event_type", type = "string" },    # created / approved / shipped / delivered / final
        { name = "event_rank", type = "int" },       # 段階の順位 0〜4。Python 側で int32 にしてそろえる
        { name = "event_time", type = "timestamp" }, # 出来事の日時(時刻付き)
        { name = "order_status", type = "string" },  # その出来事の時点で到達した状態
        { name = "is_synthetic", type = "boolean" }, # 時刻を作った最終状態なら true
      ]
    }
    # 追記型。親の注文の購入日に届く
    order_items = {
      description = "Olist の注文の明細(1行 = 注文の1明細)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "order_id", type = "string" },
        { name = "order_item_id", type = "int" }, # 注文の中の明細の番号(1, 2, ...)
        { name = "product_id", type = "string" },
        { name = "seller_id", type = "string" },
        { name = "shipping_limit_date", type = "timestamp" }, # 出品者が発送すべき期限
        { name = "price", type = "decimal(10,2)" },           # 金額は小数の誤差が出ない decimal
        { name = "freight_value", type = "decimal(10,2)" },
      ]
    }
    # 追記型。客が答えた日に届く(期間は 2018-10-29 まで)
    reviews = {
      description = "Olist のレビュー(1行 = 1件の回答)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "review_id", type = "string" },
        { name = "order_id", type = "string" },
        { name = "review_score", type = "int" }, # 星の数(1〜5)
        { name = "review_comment_title", type = "string" },
        { name = "review_comment_message", type = "string" },
        { name = "review_creation_date", type = "timestamp" },    # アンケートを送った日
        { name = "review_answer_timestamp", type = "timestamp" }, # 客が答えた日時
      ]
    }
    # 一括型(マスタ)。2016-09-04 に全件1回
    customers = {
      description = "Olist の顧客マスタ(全件を1回だけ届ける)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "customer_id", type = "string" },
        { name = "customer_unique_id", type = "string" },
        { name = "customer_zip_code_prefix", type = "string" }, # 先頭の 0 を保つため文字列
        { name = "customer_city", type = "string" },
        { name = "customer_state", type = "string" },
      ]
    }
    sellers = {
      description = "Olist の出品者マスタ(全件を1回だけ届ける)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "seller_id", type = "string" },
        { name = "seller_zip_code_prefix", type = "string" }, # 先頭の 0 を保つため文字列
        { name = "seller_city", type = "string" },
        { name = "seller_state", type = "string" },
      ]
    }
    # 列名の綴りの誤り _lenght は、元データ(Parquet の列名)のまま
    products = {
      description = "Olist の商品マスタ(全件を1回だけ届ける)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "product_id", type = "string" },
        { name = "product_category_name", type = "string" },
        { name = "product_name_lenght", type = "int" },
        { name = "product_description_lenght", type = "int" },
        { name = "product_photos_qty", type = "int" },
        { name = "product_weight_g", type = "int" },
        { name = "product_length_cm", type = "int" },
        { name = "product_height_cm", type = "int" },
        { name = "product_width_cm", type = "int" },
      ]
    }
    product_category_name_translation = {
      description = "Olist のカテゴリ名の英訳(全件を1回だけ届ける)。Raw の Parquet をそのまま読む"
      columns = [
        { name = "product_category_name", type = "string" },
        { name = "product_category_name_english", type = "string" },
      ]
    }
  }
}

# 前の住所(orders_events 専用の resource)から、一覧の1件へ引っ越す。作り直しを防ぐ
moved {
  from = aws_glue_catalog_table.bronze_orders_events
  to   = aws_glue_catalog_table.bronze["orders_events"]
}

resource "aws_glue_catalog_table" "bronze" {
  # 一覧の1件ごとに、表を1つ作る。each.key は表の名前、each.value は説明と列
  for_each = local.bronze_tables

  name          = each.key
  database_name = aws_glue_catalog_database.layers["bronze"].name
  table_type    = "EXTERNAL_TABLE" # データは S3 の Raw にあり、テーブルは場所と列だけを持つ
  description   = each.value.description

  parameters = {
    EXTERNAL       = "TRUE"
    classification = "parquet"
    # パーティションの射影: ingest_date のフォルダを、Glue に登録せずに日付の規則で見つける
    # 全表で同じ範囲にする(reviews の最後 2018-10-29 も、マスタの 2016-09-04 も収まる)
    "projection.enabled"                   = "true"
    "projection.ingest_date.type"          = "date"
    "projection.ingest_date.format"        = "yyyy-MM-dd"
    "projection.ingest_date.range"         = "2016-09-01,2018-12-31"
    "projection.ingest_date.interval"      = "1"
    "projection.ingest_date.interval.unit" = "DAYS"
    "storage.location.template"            = "${local.bronze_raw_prefix}/${each.key}/ingest_date=$${ingest_date}/"
  }

  # 取り込んだ日(届いた日)。フォルダ名から決まる
  partition_keys {
    name = "ingest_date"
    type = "string"
  }

  # ファイルの読み方(Parquet)
  storage_descriptor {
    location      = "${local.bronze_raw_prefix}/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    # 業務の列のあとに監査カラムをつなげ、列を1つずつ作る
    dynamic "columns" {
      for_each = concat(each.value.columns, local.bronze_audit_columns)
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
