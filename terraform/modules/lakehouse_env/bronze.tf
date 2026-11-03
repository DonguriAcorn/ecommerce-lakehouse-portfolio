# orders のイベント単位の Raw(ADR 0010)を、そのまま読む外部テーブル(ADR 0003)
locals {
  # Raw の置き場所
  bronze_orders_events_location = "s3://${aws_s3_bucket.lake.bucket}/raw/olist/orders_events/"

  # Parquet の列と同じ名前と型(Athena の Parquet は列名で読む)
  bronze_orders_events_columns = [
    { name = "order_id", type = "string" },
    { name = "customer_id", type = "string" },
    { name = "order_purchase_timestamp", type = "timestamp" },
    { name = "order_estimated_delivery_date", type = "timestamp" },
    { name = "event_type", type = "string" },    # created / approved / shipped / delivered / final
    { name = "event_rank", type = "int" },       # 段階の順位 0〜4。Python 側で int32 にしてそろえる
    { name = "event_time", type = "timestamp" }, # 出来事の日時(時刻付き)
    { name = "order_status", type = "string" },  # その出来事の時点で到達した状態
    { name = "is_synthetic", type = "boolean" }, # 時刻を作った最終状態なら true
    { name = "_ingested_at", type = "timestamp" },
    { name = "_source_file", type = "string" },
    { name = "_batch_id", type = "string" },
  ]
}

resource "aws_glue_catalog_table" "bronze_orders_events" {
  name          = "orders_events"
  database_name = aws_glue_catalog_database.layers["bronze"].name
  table_type    = "EXTERNAL_TABLE" # データは S3 の Raw にあり、テーブルは場所と列だけを持つ
  description   = "Olist order events (one row per order event), read directly from raw Parquet"

  parameters = {
    EXTERNAL       = "TRUE"
    classification = "parquet"
    # パーティションの射影: ingest_date のフォルダを、Glue に登録せずに日付の規則で見つける
    "projection.enabled"                   = "true"
    "projection.ingest_date.type"          = "date"
    "projection.ingest_date.format"        = "yyyy-MM-dd"
    "projection.ingest_date.range"         = "2016-09-01,2018-12-31" # 遅延で数日ずれても収まる範囲
    "projection.ingest_date.interval"      = "1"
    "projection.ingest_date.interval.unit" = "DAYS"
    "storage.location.template"            = "${local.bronze_orders_events_location}ingest_date=$${ingest_date}/"
  }

  # 取り込んだ日(届いた日)。フォルダ名から決まる
  partition_keys {
    name = "ingest_date"
    type = "string"
  }

  # ファイルの読み方(Parquet)
  storage_descriptor {
    location      = local.bronze_orders_events_location
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    # 上の列の一覧から、列を1つずつ作る
    dynamic "columns" {
      for_each = local.bronze_orders_events_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
