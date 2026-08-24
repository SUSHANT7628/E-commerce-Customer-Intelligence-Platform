-- CLV distribution
SELECT
    customer_segment,
    COUNT(*) AS customers,
    ROUND(AVG(predicted_12m_clv)::numeric, 2) AS avg_predicted_clv,
    ROUND(SUM(predicted_12m_clv)::numeric, 2) AS total_predicted_clv
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY total_predicted_clv DESC;

-- Highest-value customers
SELECT
    customer_unique_id,
    customer_segment,
    total_revenue,
    predicted_12m_clv,
    recency
FROM analytics.customer_360_clv
ORDER BY predicted_12m_clv DESC
LIMIT 100;

-- High CLV but poor recency: retention priority candidates
SELECT
    customer_unique_id,
    customer_segment,
    predicted_12m_clv,
    recency,
    frequency
FROM analytics.customer_360_clv
WHERE predicted_12m_clv >= (
    SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY predicted_12m_clv)
    FROM analytics.customer_360_clv
)
AND recency >= (
    SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY recency)
    FROM analytics.customer_360_clv
)
ORDER BY predicted_12m_clv DESC;
