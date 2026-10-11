-- =============================================================================
-- Business questions (DuckDB SQL, run after `retailpulse run`)
--   duckdb artifacts/warehouse.duckdb < sql/analytics/01_business_questions.sql
-- =============================================================================

-- Q1. Which customer segment contributes the most revenue?
SELECT customer_segment,
       COUNT(*)                                             AS customers,
       ROUND(SUM(total_revenue), 2)                         AS revenue,
       ROUND(100 * SUM(total_revenue) / SUM(SUM(total_revenue)) OVER (), 1) AS revenue_pct,
       ROUND(AVG(avg_order_value), 2)                       AS avg_order_value
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY revenue DESC;

-- Q2. What share of customers is At Risk, Can't Lose Them or Hibernating / Lost?
SELECT ROUND(100 * AVG(CASE WHEN customer_segment IN ('At Risk', 'Can''t Lose Them', 'Hibernating / Lost')
                            THEN 1 ELSE 0 END), 1) AS lapsed_customer_pct
FROM analytics.customer_360_clv;

-- Q3. How much historical revenue and future value sits with high-value, at-risk customers?
SELECT retention_priority,
       COUNT(*)                              AS customers,
       ROUND(SUM(total_revenue), 2)          AS historical_revenue,
       ROUND(SUM(predicted_12m_clv), 2)      AS predicted_12m_clv,
       ROUND(SUM(clv_at_risk), 2)            AS clv_at_risk
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY 1;

-- Q4. Do Champions have materially higher AOV than other segments?
SELECT customer_segment = 'Champions'        AS is_champion,
       COUNT(*)                              AS customers,
       ROUND(AVG(avg_order_value), 2)        AS avg_order_value,
       ROUND(MEDIAN(avg_order_value), 2)     AS median_order_value
FROM analytics.customer_360_clv
GROUP BY 1;

-- Q5. Which states hold the most high-value customers?
SELECT customer_state,
       COUNT(*) FILTER (WHERE value_tier = 'High') AS high_value_customers,
       COUNT(*)                                    AS customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE value_tier = 'High') / COUNT(*), 1) AS high_value_pct
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
       ROUND(100 * AVG(is_repeat_customer), 2)   AS repeat_rate_pct,
       ROUND(AVG(churn_probability), 4)          AS avg_churn_probability
FROM analytics.customer_360_clv
GROUP BY 1
ORDER BY 1;
