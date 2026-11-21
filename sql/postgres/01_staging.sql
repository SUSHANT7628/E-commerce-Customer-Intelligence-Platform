-- =============================================================================
-- 01_staging.sql (PostgreSQL) — clean, typed, order-level tables built from raw.*
-- Same logic as sql/01_staging.sql (DuckDB); raw.* columns are loaded as TEXT.
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS staging;

-- Items with English category names. Revenue = item price + freight (GMV),
-- which excludes card-installment interest included in payment_value.
DROP TABLE IF EXISTS staging.order_items CASCADE;
CREATE TABLE staging.order_items AS
SELECT
    i.order_id,
    CAST(i.order_item_id AS INTEGER)                                            AS order_item_id,
    i.product_id,
    i.seller_id,
    CAST(i.price AS DOUBLE PRECISION)                                           AS price,
    CAST(i.freight_value AS DOUBLE PRECISION)                                   AS freight_value,
    CAST(i.price AS DOUBLE PRECISION) + CAST(i.freight_value AS DOUBLE PRECISION) AS item_revenue,
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS category
FROM raw.order_items i
LEFT JOIN raw.products p USING (product_id)
LEFT JOIN raw.category_translation t USING (product_category_name);

-- One row per order. Canceled / unavailable orders never generated revenue and
-- are excluded from every downstream metric.
DROP TABLE IF EXISTS staging.orders CASCADE;
CREATE TABLE staging.orders AS
WITH items AS (
    SELECT order_id,
           SUM(item_revenue)        AS order_revenue,
           SUM(price)               AS product_revenue,
           SUM(freight_value)       AS freight_revenue,
           COUNT(*)                 AS n_items,
           COUNT(DISTINCT category) AS n_categories
    FROM staging.order_items
    GROUP BY order_id
),
pay AS (
    -- payment type of the largest payment: window function instead of DuckDB's ARG_MAX
    SELECT order_id, installments, payment_type
    FROM (
        SELECT order_id,
               MAX(CAST(payment_installments AS INTEGER)) OVER (PARTITION BY order_id) AS installments,
               payment_type,
               ROW_NUMBER() OVER (PARTITION BY order_id
                                  ORDER BY CAST(payment_value AS DOUBLE PRECISION) DESC,
                                           payment_sequential) AS rn
        FROM raw.order_payments
    ) ranked
    WHERE rn = 1
),
rev AS (
    SELECT order_id, AVG(CAST(review_score AS DOUBLE PRECISION)) AS review_score
    FROM raw.order_reviews
    GROUP BY order_id
),
typed AS (
    SELECT o.*,
           CAST(o.order_purchase_timestamp AS TIMESTAMP)      AS p_ts,
           CAST(o.order_delivered_customer_date AS TIMESTAMP) AS d_ts,
           CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS e_ts
    FROM raw.orders o
)
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_state,
    c.customer_city,
    o.order_status,
    o.p_ts                                                    AS purchase_ts,
    CAST(o.p_ts AS DATE)                                      AS purchase_date,
    DATE_TRUNC('month', o.p_ts)                               AS purchase_month,
    o.d_ts                                                    AS delivered_ts,
    o.e_ts                                                    AS estimated_delivery_ts,
    -- whole hours between purchase and delivery, as DuckDB DATE_DIFF('hour', ...) counts them
    EXTRACT(EPOCH FROM DATE_TRUNC('hour', o.d_ts) - DATE_TRUNC('hour', o.p_ts)) / 3600.0 / 24.0 AS delivery_days,
    CASE WHEN o.d_ts IS NULL THEN NULL
         WHEN o.d_ts > o.e_ts + INTERVAL '1 day' THEN 1 ELSE 0 END AS is_late,
    i.order_revenue,
    i.product_revenue,
    i.freight_revenue,
    i.n_items,
    i.n_categories,
    p.installments,
    p.payment_type,
    r.review_score
FROM typed o
JOIN raw.customers c USING (customer_id)
JOIN items i USING (order_id)            -- orders without items have no revenue
LEFT JOIN pay p USING (order_id)
LEFT JOIN rev r USING (order_id)
WHERE o.order_status NOT IN ('canceled', 'unavailable');

CREATE INDEX ON staging.orders (customer_unique_id);
CREATE INDEX ON staging.order_items (order_id);
