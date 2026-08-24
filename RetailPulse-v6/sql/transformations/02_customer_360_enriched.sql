DROP TABLE IF EXISTS analytics.customer_360_enriched;

CREATE TABLE analytics.customer_360_enriched AS
WITH base AS (
    SELECT
        *,
        EXTRACT(
            DAY FROM (MAX(last_purchase) OVER () - last_purchase)
        )::int AS recency,
        order_count AS frequency,
        total_revenue AS monetary
    FROM analytics.customer_360
)
SELECT
    *,
    NTILE(5) OVER (ORDER BY recency DESC) AS recency_bucket,
    NTILE(5) OVER (ORDER BY frequency) AS frequency_bucket,
    NTILE(5) OVER (ORDER BY monetary) AS monetary_bucket
FROM base;
