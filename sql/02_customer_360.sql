-- =============================================================================
-- 02_customer_360.sql — one row per real customer (customer_unique_id)
-- Olist issues a new customer_id per order; customer_unique_id is the person.
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE OR REPLACE TABLE analytics.customer_360 AS
WITH snapshot AS (
    -- Analysis date: the day after the last order in the data.
    SELECT CAST(MAX(purchase_ts) AS DATE) + 1 AS snapshot_date FROM staging.orders
),
cat AS (
    SELECT o.customer_unique_id,
           MODE(i.category) AS top_category,
           COUNT(DISTINCT i.category) AS distinct_categories
    FROM staging.order_items i
    JOIN staging.orders o USING (order_id)
    GROUP BY 1
),
agg AS (
    SELECT
        customer_unique_id,
        ARG_MAX(customer_state, purchase_ts)   AS customer_state,
        ARG_MAX(customer_city,  purchase_ts)   AS customer_city,
        MIN(purchase_ts)                       AS first_purchase,
        MAX(purchase_ts)                       AS last_purchase,
        COUNT(*)                               AS order_count,
        SUM(order_revenue)                     AS total_revenue,
        AVG(order_revenue)                     AS avg_order_value,
        SUM(n_items)                           AS total_items,
        AVG(review_score)                      AS avg_review_score,
        MIN(review_score)                      AS min_review_score,
        AVG(delivery_days)                     AS avg_delivery_days,
        AVG(is_late)                           AS late_delivery_rate,
        AVG(installments)                      AS avg_installments,
        MODE(payment_type)                     AS preferred_payment_type
    FROM staging.orders
    GROUP BY customer_unique_id
)
SELECT
    a.*,
    c.top_category,
    c.distinct_categories,
    DATE_DIFF('day', a.first_purchase, a.last_purchase)              AS tenure_days,
    DATE_DIFF('day', CAST(a.last_purchase AS DATE), s.snapshot_date) AS recency,
    DATE_DIFF('day', CAST(a.first_purchase AS DATE), s.snapshot_date) AS customer_age_days,
    a.order_count  AS frequency,
    a.total_revenue AS monetary,
    (a.order_count > 1)::INTEGER AS is_repeat_customer,
    s.snapshot_date
FROM agg a
LEFT JOIN cat c USING (customer_unique_id)
CROSS JOIN snapshot s;
