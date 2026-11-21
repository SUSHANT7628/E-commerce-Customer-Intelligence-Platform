-- =============================================================================
-- 02_customer_360.sql (PostgreSQL) — one row per real customer (customer_unique_id)
-- Olist issues a new customer_id per order; customer_unique_id is the person.
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS analytics;

DROP TABLE IF EXISTS analytics.customer_360 CASCADE;
CREATE TABLE analytics.customer_360 AS
WITH snapshot AS (
    -- Analysis date: the day after the last order in the data.
    SELECT CAST(MAX(purchase_ts) AS DATE) + 1 AS snapshot_date FROM staging.orders
),
cat AS (
    SELECT o.customer_unique_id,
           MODE() WITHIN GROUP (ORDER BY i.category) AS top_category,
           COUNT(DISTINCT i.category)                AS distinct_categories
    FROM staging.order_items i
    JOIN staging.orders o USING (order_id)
    GROUP BY 1
),
latest AS (
    -- state and city of each customer's most recent order (DuckDB: ARG_MAX)
    SELECT DISTINCT ON (customer_unique_id)
           customer_unique_id, customer_state, customer_city
    FROM staging.orders
    ORDER BY customer_unique_id, purchase_ts DESC, order_id
),
agg AS (
    SELECT
        customer_unique_id,
        MIN(purchase_ts)                          AS first_purchase,
        MAX(purchase_ts)                          AS last_purchase,
        COUNT(*)                                  AS order_count,
        SUM(order_revenue)                        AS total_revenue,
        AVG(order_revenue)                        AS avg_order_value,
        SUM(n_items)                              AS total_items,
        AVG(review_score)                         AS avg_review_score,
        MIN(review_score)                         AS min_review_score,
        AVG(delivery_days)                        AS avg_delivery_days,
        AVG(is_late)                              AS late_delivery_rate,
        AVG(installments)                         AS avg_installments,
        MODE() WITHIN GROUP (ORDER BY payment_type) AS preferred_payment_type
    FROM staging.orders
    GROUP BY customer_unique_id
)
SELECT
    a.customer_unique_id,
    l.customer_state,
    l.customer_city,
    a.first_purchase, a.last_purchase, a.order_count, a.total_revenue, a.avg_order_value,
    a.total_items, a.avg_review_score, a.min_review_score, a.avg_delivery_days,
    a.late_delivery_rate, a.avg_installments, a.preferred_payment_type,
    c.top_category,
    c.distinct_categories,
    CAST(a.last_purchase AS DATE) - CAST(a.first_purchase AS DATE) AS tenure_days,
    s.snapshot_date - CAST(a.last_purchase AS DATE)                AS recency,
    s.snapshot_date - CAST(a.first_purchase AS DATE)               AS customer_age_days,
    a.order_count   AS frequency,
    a.total_revenue AS monetary,
    (a.order_count > 1)::INTEGER AS is_repeat_customer,
    s.snapshot_date
FROM agg a
JOIN latest l USING (customer_unique_id)
LEFT JOIN cat c USING (customer_unique_id)
CROSS JOIN snapshot s;

CREATE UNIQUE INDEX ON analytics.customer_360 (customer_unique_id);
