-- Once churn_probability is written back to analytics.customer_360_clv,
-- combine model risk with economic value.

SELECT
    customer_unique_id,
    customer_segment,
    predicted_12m_clv,
    churn_probability,
    CASE
        WHEN predicted_12m_clv >=
             (SELECT percentile_cont(0.75) WITHIN GROUP
              (ORDER BY predicted_12m_clv)
              FROM analytics.customer_360_clv)
         AND churn_probability >= 0.70
            THEN 'P1 - High Value / High Churn Risk'
        WHEN predicted_12m_clv >=
             (SELECT percentile_cont(0.75) WITHIN GROUP
              (ORDER BY predicted_12m_clv)
              FROM analytics.customer_360_clv)
         AND churn_probability >= 0.40
            THEN 'P2 - High Value / Medium Risk'
        WHEN churn_probability >= 0.70
            THEN 'P3 - High Churn Risk'
        ELSE 'Standard Lifecycle'
    END AS retention_priority
FROM analytics.customer_360_clv
ORDER BY predicted_12m_clv DESC;
