-- Silver re-run checks for ecom_dev_silver.orders. Paste each query into the Athena query editor (workgroup ecom-dev).
-- Replace <SNAPSHOT_ID> with the snapshot_id of the first MERGE (committed_at 2026-10-26 08:08 UTC).

-- 1. Snapshots (the baseline is the first row)
SELECT committed_at, snapshot_id, operation
FROM "ecom_dev_silver"."orders$snapshots"
ORDER BY committed_at;

-- 2. Orders that a 10-04-only re-run must not roll back (expected: 1 or more)
SELECT count(*) AS protected_orders
FROM ecom_dev_silver.orders
WHERE _ingest_date > DATE '2017-10-04'
  AND order_id IN (
    SELECT order_id
    FROM ecom_dev_bronze.orders
    WHERE ingest_date = '2017-10-04'
  );

-- 3. Rows that differ from the baseline snapshot, both directions (expected: 0)
SELECT count(*) AS diff_rows
FROM (
  (SELECT * FROM ecom_dev_silver.orders
   EXCEPT
   SELECT * FROM ecom_dev_silver.orders FOR VERSION AS OF <SNAPSHOT_ID>)
  UNION ALL
  (SELECT * FROM ecom_dev_silver.orders FOR VERSION AS OF <SNAPSHOT_ID>
   EXCEPT
   SELECT * FROM ecom_dev_silver.orders)
);

-- 4. Row count and distinct orders; EXCEPT cannot see exact duplicates (expected: 1308 | 1308)
SELECT count(*) AS silver_rows, count(DISTINCT order_id) AS silver_orders
FROM ecom_dev_silver.orders;

-- 5. Event dates later than the row's ingest date; the estimated date is excluded on purpose (expected: 0)
SELECT count(*) AS leaked_rows
FROM ecom_dev_silver.orders
WHERE date(order_approved_at)             > _ingest_date
   OR date(order_delivered_carrier_date)  > _ingest_date
   OR date(order_delivered_customer_date) > _ingest_date;
