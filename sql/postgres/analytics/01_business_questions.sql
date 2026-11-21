-- =============================================================================
-- Business questions (PostgreSQL, run after `retailpulse postgres-build`)
--   psql "$PG_URL" -f sql/postgres/analytics/01_business_questions.sql
-- =============================================================================

-- Q1. Which customer segment contributes the most revenue?
SELECT customer_segment,
       COUNT(*)                                             AS customers,
       ROUND(CAST(SUM(total_revenue) AS NUMERIC), 2)                         AS revenue,
       ROUND(CAST(100 * SUM(total_revenue) / SUM(SUM(total_revenue)) OVER () AS NUMERIC), 1) AS revenue_pct,
       ROUND(CAST(AVG(avg_order_value) AS NUMERIC), 2)                       AS avg_order_value
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY revenue DESC;

-- Q2. What share of customers is At Risk or Hibernating / Lost?
SELECT ROUND(CAST(100 * AVG(CASE WHEN customer_segment IN ('At Risk', 'Hibernating / Lost')
                            THEN 1 ELSE 0 END) AS NUMERIC), 1) AS lapsed_customer_pct
FROM analytics.customer_360_clv;

-- Q3. How much historical revenue and future value sits with high-value, at-risk customers?
SELECT retention_priority,
       COUNT(*)                              AS customers,
       ROUND(CAST(SUM(total_revenue) AS NUMERIC), 2)          AS historical_revenue,
       ROUND(CAST(SUM(predicted_12m_clv) AS NUMERIC), 2)      AS predicted_12m_clv,
       ROUND(CAST(SUM(clv_at_risk) AS NUMERIC), 2)            AS clv_at_risk
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY 1;

-- Q4. Do Champions have materially higher AOV than other segments?
SELECT customer_segment = 'Champions'        AS is_champion,
       COUNT(*)                              AS customers,
       ROUND(CAST(AVG(avg_order_value) AS NUMERIC), 2)        AS avg_order_value,
       ROUND(CAST(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY avg_order_value) AS NUMERIC), 2)     AS median_order_value
FROM analytics.customer_360_clv
GROUP BY 1;

-- Q5. Which states hold the most high-value customers?
SELECT customer_state,
       COUNT(*) FILTER (WHERE value_tier = 'High') AS high_value_customers,
       COUNT(*)                                    AS customers,
       ROUND(CAST(100.0 * COUNT(*) FILTER (WHERE value_tier = 'High') / COUNT(*) AS NUMERIC), 1) AS high_value_pct
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY high_value_customers DESC
LIMIT 10;

-- Q6. Do bad experiences coincide with lower return? (association, not causation)
SELECT CASE WHEN min_review_score <= 2 THEN '1-2 stars'
            WHEN min_review_score = 3  THEN '3 stars'
            WHEN min_review_score >= 4 THEN '4-5 stars'
            ELSE 'no review' END                 AS worst_review,
       COUNT(*)                                  AS customers,
       ROUND(CAST(100 * AVG(is_repeat_customer) AS NUMERIC), 2)   AS repeat_rate_pct,
       ROUND(CAST(AVG(churn_probability) AS NUMERIC), 4)          AS avg_churn_probability
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY 1;
