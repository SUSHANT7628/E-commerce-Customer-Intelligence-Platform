-- =============================================================================
-- 04_business_marts.sql (PostgreSQL) — aggregates behind the Executive and
-- Product & Seller dashboard pages
-- =============================================================================

DROP TABLE IF EXISTS analytics.monthly_kpis CASCADE;
CREATE TABLE analytics.monthly_kpis AS
WITH first_orders AS (
    SELECT customer_unique_id, MIN(purchase_month) AS cohort_month
    FROM staging.orders GROUP BY 1
),
m AS (
    SELECT
        o.purchase_month                                     AS month,
        SUM(o.order_revenue)                                 AS revenue,
        COUNT(*)                                             AS orders,
        COUNT(DISTINCT o.customer_unique_id)                 AS customers,
        COUNT(DISTINCT CASE WHEN f.cohort_month = o.purchase_month
                            THEN o.customer_unique_id END)   AS new_customers,
        AVG(o.review_score)                                  AS avg_review_score,
        AVG(o.is_late)                                       AS late_delivery_rate
    FROM staging.orders o
    JOIN first_orders f USING (customer_unique_id)
    GROUP BY 1
)
SELECT
    *,
    revenue / orders                                               AS avg_order_value,
    revenue / LAG(revenue) OVER (ORDER BY month) - 1               AS revenue_growth_mom
FROM m
ORDER BY month;

DROP TABLE IF EXISTS analytics.category_performance CASCADE;
CREATE TABLE analytics.category_performance AS
SELECT
    i.category,
    SUM(i.item_revenue)                  AS revenue,
    COUNT(DISTINCT i.order_id)           AS orders,
    COUNT(*)                             AS items_sold,
    AVG(i.price)                         AS avg_item_price,
    AVG(o.review_score)                  AS avg_review_score,
    AVG(o.is_late)                       AS late_delivery_rate
FROM staging.order_items i
JOIN staging.orders o USING (order_id)
GROUP BY 1
ORDER BY revenue DESC;

DROP TABLE IF EXISTS analytics.product_performance CASCADE;
CREATE TABLE analytics.product_performance AS
SELECT
    i.product_id,
    MIN(i.category)                      AS category,   -- one category per product
    SUM(i.item_revenue)                  AS revenue,
    COUNT(*)                             AS items_sold,
    AVG(o.review_score)                  AS avg_review_score
FROM staging.order_items i
JOIN staging.orders o USING (order_id)
GROUP BY 1
ORDER BY revenue DESC;

DROP TABLE IF EXISTS analytics.seller_performance CASCADE;
CREATE TABLE analytics.seller_performance AS
SELECT
    i.seller_id,
    MIN(s.seller_state)                  AS seller_state,
    SUM(i.item_revenue)                  AS revenue,
    COUNT(DISTINCT i.order_id)           AS orders,
    COUNT(DISTINCT i.category)           AS categories,
    AVG(o.review_score)                  AS avg_review_score,
    AVG(o.is_late)                       AS late_delivery_rate,
    AVG(o.delivery_days)                 AS avg_delivery_days
FROM staging.order_items i
JOIN staging.orders o USING (order_id)
LEFT JOIN raw.sellers s USING (seller_id)
GROUP BY 1
ORDER BY revenue DESC;

DROP TABLE IF EXISTS analytics.state_performance CASCADE;
CREATE TABLE analytics.state_performance AS
SELECT
    customer_state,
    SUM(order_revenue)                   AS revenue,
    COUNT(*)                             AS orders,
    COUNT(DISTINCT customer_unique_id)   AS customers,
    AVG(order_revenue)                   AS avg_order_value,
    AVG(review_score)                    AS avg_review_score,
    AVG(delivery_days)                   AS avg_delivery_days
FROM staging.orders
GROUP BY 1
ORDER BY revenue DESC;
