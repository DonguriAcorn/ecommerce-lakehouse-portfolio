-- Silver: upsert orders from bronze for ingest dates __START_DATE__ .. __END_DATE__.
-- Uses only the latest ingest_date per order_id, and never overwrites newer data with older data.
MERGE INTO ecom_dev_silver.orders AS t
USING (
  SELECT
    order_id,
    customer_id,
    order_status,
    order_purchase_timestamp,
    order_approved_at,
    order_delivered_carrier_date,
    order_delivered_customer_date,
    order_estimated_delivery_date,
    _ingested_at,
    _batch_id,
    CAST(ingest_date AS date) AS _ingest_date
  FROM (
    SELECT
      b.*,
      row_number() OVER (PARTITION BY order_id ORDER BY ingest_date DESC) AS rn
    FROM ecom_dev_bronze.orders AS b
    WHERE ingest_date BETWEEN '__START_DATE__' AND '__END_DATE__'
  ) AS ranked
  WHERE rn = 1
) AS s
ON t.order_id = s.order_id
WHEN MATCHED AND s._ingest_date > t._ingest_date THEN UPDATE SET
  customer_id                   = s.customer_id,
  order_status                  = s.order_status,
  order_purchase_timestamp      = s.order_purchase_timestamp,
  order_approved_at             = s.order_approved_at,
  order_delivered_carrier_date  = s.order_delivered_carrier_date,
  order_delivered_customer_date = s.order_delivered_customer_date,
  order_estimated_delivery_date = s.order_estimated_delivery_date,
  _ingested_at                  = s._ingested_at,
  _batch_id                     = s._batch_id,
  _ingest_date                  = s._ingest_date
WHEN NOT MATCHED THEN INSERT (
  order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at,
  order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date,
  _ingested_at, _batch_id, _ingest_date
) VALUES (
  s.order_id, s.customer_id, s.order_status, s.order_purchase_timestamp, s.order_approved_at,
  s.order_delivered_carrier_date, s.order_delivered_customer_date, s.order_estimated_delivery_date,
  s._ingested_at, s._batch_id, s._ingest_date
)
