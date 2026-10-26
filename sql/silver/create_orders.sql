-- Silver: Olist orders (Iceberg). Current state of each order, updated by MERGE from bronze.
-- __LAKE_BUCKET__ is replaced at run time (the account ID must not be written in files).
CREATE TABLE IF NOT EXISTS ecom_dev_silver.orders (
  order_id                      string,
  customer_id                   string,
  order_status                  string,
  order_purchase_timestamp      timestamp,
  order_approved_at             timestamp,
  order_delivered_carrier_date  timestamp,
  order_delivered_customer_date timestamp,
  order_estimated_delivery_date timestamp,
  _ingested_at                  timestamp,
  _batch_id                     string
)
PARTITIONED BY (month(order_purchase_timestamp))
LOCATION 's3://__LAKE_BUCKET__/iceberg/silver/orders/'
TBLPROPERTIES (
  'table_type'        = 'ICEBERG',
  'format'            = 'parquet',
  'write_compression' = 'zstd'
)
