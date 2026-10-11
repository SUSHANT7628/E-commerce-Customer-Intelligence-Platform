-- =============================================================================
-- 01_staging.sql — clean, typed, order-level tables built from raw.* (DuckDB)
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS staging;

-- Items with English category names. Revenue = item price + freight (GMV),
-- which excludes card-installment interest included in payment_value.
CREATE OR REPLACE TABLE staging.order_items AS
SELECT
    i.order_id,
    i.order_item_id,
    i.product_id,
    i.seller_id,
    CAST(i.price AS DOUBLE)                                   AS price,
    CAST(i.freight_value AS DOUBLE)                           AS freight_value,
    CAST(i.price AS DOUBLE) + CAST(i.freight_value AS DOUBLE) AS item_revenue,
    COALESCE(t.product_category_name_english,
             p.product_category_name, 'unknown')              AS category
FROM raw.order_items i
LEFT JOIN raw.products p USING (product_id)
LEFT JOIN raw.category_translation t USING (product_category_name);

-- One row per order. Canceled / unavailable orders never generated revenue and
-- are excluded from every downstream metric.
CREATE OR REPLACE TABLE staging.orders AS
WITH items AS (
    SELECT order_id,
           SUM(item_revenue)   AS order_revenue,
           SUM(price)          AS product_revenue,
           SUM(freight_value)  AS freight_revenue,
           COUNT(*)            AS n_items,
           COUNT(DISTINCT category) AS n_categories
    FROM staging.order_items
    GROUP BY order_id
),
pay AS (
    SELECT order_id,
           MAX(CAST(payment_installments AS INTEGER))           AS installments,
           ARG_MAX(payment_type, CAST(payment_value AS DOUBLE)) AS payment_type
    FROM raw.order_payments
    GROUP BY order_id
),
rev AS (
    SELECT order_id, AVG(CAST(review_score AS DOUBLE)) AS review_score
    FROM raw.order_reviews
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_state,
    c.customer_city,
    o.order_status,
    CAST(o.order_purchase_timestamp AS TIMESTAMP)               AS purchase_ts,
    CAST(o.order_purchase_timestamp AS DATE)                    AS purchase_date,
    DATE_TRUNC('month', CAST(o.order_purchase_timestamp AS TIMESTAMP)) AS purchase_month,
    CAST(o.order_delivered_customer_date AS TIMESTAMP)          AS delivered_ts,
    CAST(o.order_estimated_delivery_date AS TIMESTAMP)          AS estimated_delivery_ts,
    DATE_DIFF('hour', CAST(o.order_purchase_timestamp AS TIMESTAMP),
              CAST(o.order_delivered_customer_date AS TIMESTAMP)) / 24.0 AS delivery_days,
    CASE WHEN o.order_delivered_customer_date IS NULL THEN NULL
         WHEN CAST(o.order_delivered_customer_date AS TIMESTAMP)
              > CAST(o.order_estimated_delivery_date AS TIMESTAMP) + INTERVAL 1 DAY
         THEN 1 ELSE 0 END                                       AS is_late,
    i.order_revenue,
    i.product_revenue,
    i.freight_revenue,
    i.n_items,
    i.n_categories,
    p.installments,
    p.payment_type,
    r.review_score
FROM raw.orders o
JOIN raw.customers c USING (customer_id)
JOIN items i USING (order_id)            -- orders without items have no revenue
LEFT JOIN pay p USING (order_id)
LEFT JOIN rev r USING (order_id)
WHERE o.order_status NOT IN ('canceled', 'unavailable');
