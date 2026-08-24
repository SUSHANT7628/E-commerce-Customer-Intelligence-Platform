DROP TABLE IF EXISTS analytics.customer_360_clv;

CREATE TABLE analytics.customer_360_clv AS
SELECT
    e.*,
    GREATEST(
        (total_revenue / GREATEST(EXTRACT(DAY FROM (last_purchase - first_purchase)) / 30.44, 1))
        * 12
        * EXP(-recency / 365.0),
        0
    ) AS predicted_12m_clv
FROM analytics.customer_360_enriched e;
