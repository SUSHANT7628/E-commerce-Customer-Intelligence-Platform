-- Customer segment summary after analytics.customer_360 has been created.
SELECT
    customer_segment,
    COUNT(*) AS customers,
    ROUND(SUM(total_revenue)::numeric, 2) AS revenue,
    ROUND(AVG(avg_order_value)::numeric, 2) AS avg_order_value
FROM analytics.customer_360_enriched
GROUP BY 1
ORDER BY revenue DESC;

-- High-value customers with recent inactivity.
SELECT
    customer_unique_id,
    total_revenue,
    order_count,
    last_purchase
FROM analytics.customer_360_enriched
WHERE customer_segment = 'At Risk'
ORDER BY total_revenue DESC
LIMIT 100;
