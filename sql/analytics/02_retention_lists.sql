-- =============================================================================
-- Retention call lists for the CRM team
-- =============================================================================

-- P1: high value / high risk, ordered by value at risk.
SELECT customer_unique_id, customer_state, customer_segment, order_count,
       ROUND(total_revenue, 2)       AS total_revenue,
       recency                       AS days_since_last_order,
       avg_review_score,
       ROUND(predicted_12m_clv, 2)   AS predicted_12m_clv,
       ROUND(churn_probability, 4)   AS churn_probability,
       ROUND(clv_at_risk, 2)         AS clv_at_risk,
       recommended_action
FROM analytics.customer_360_clv
WHERE retention_priority LIKE 'P1%'
ORDER BY clv_at_risk DESC
LIMIT 500;

-- Service-recovery list: valuable customers whose worst experience was 1-2 stars.
SELECT customer_unique_id, customer_state, order_count, ROUND(total_revenue, 2) AS total_revenue,
       min_review_score, ROUND(late_delivery_rate, 2) AS late_delivery_rate,
       ROUND(predicted_12m_clv, 2) AS predicted_12m_clv
FROM analytics.customer_360_clv
WHERE min_review_score <= 2 AND value_tier = 'High'
ORDER BY predicted_12m_clv DESC
LIMIT 500;

-- Highest predicted CLV customers overall (protect & grow).
SELECT customer_unique_id, customer_segment, order_count, ROUND(total_revenue, 2) AS total_revenue,
       ROUND(expected_orders_12m, 3) AS expected_orders_12m,
       ROUND(predicted_12m_clv, 2) AS predicted_12m_clv, retention_priority
FROM analytics.customer_360_clv
ORDER BY predicted_12m_clv DESC
LIMIT 100;
