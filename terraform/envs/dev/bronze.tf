locals {
  bronze_orders_location = "s3://${aws_s3_bucket.lake.bucket}/raw/olist/orders/"

  bronze_orders_columns = [
    { name = "order_id", type = "string" },
    { name = "customer_id", type = "string" },
    { name = "order_status", type = "string" },
    { name = "order_purchase_timestamp", type = "timestamp" },
    { name = "order_approved_at", type = "timestamp" },
    { name = "order_delivered_carrier_date", type = "timestamp" },
    { name = "order_delivered_customer_date", type = "timestamp" },
    { name = "order_estimated_delivery_date", type = "timestamp" },
    { name = "_ingested_at", type = "timestamp" },
    { name = "_source_file", type = "string" },
    { name = "_batch_id", type = "string" },
  ]
}

resource "aws_glue_catalog_table" "bronze_orders" {
  name          = "orders"
  database_name = aws_glue_catalog_database.layers["bronze"].name
  table_type    = "EXTERNAL_TABLE"
  description   = "Olist orders daily snapshots, read directly from raw Parquet"

  parameters = {
    EXTERNAL                               = "TRUE"
    classification                         = "parquet"
    "projection.enabled"                   = "true"
    "projection.ingest_date.type"          = "date"
    "projection.ingest_date.format"        = "yyyy-MM-dd"
    "projection.ingest_date.range"         = "2016-09-01,2018-12-31"
    "projection.ingest_date.interval"      = "1"
    "projection.ingest_date.interval.unit" = "DAYS"
    "storage.location.template"            = "${local.bronze_orders_location}ingest_date=$${ingest_date}/"
  }

  partition_keys {
    name = "ingest_date"
    type = "string"
  }

  storage_descriptor {
    location      = local.bronze_orders_location
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    dynamic "columns" {
      for_each = local.bronze_orders_columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
