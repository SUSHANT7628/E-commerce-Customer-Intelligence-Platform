-- =============================================================================
-- 03_rfm_segments.sql — RFM scores and interpretable segments
--
-- R and M use quintiles (NTILE, ties broken by id so results are deterministic).
-- F uses fixed business bins: on Olist ~97% of customers order exactly once, so a
-- frequency quintile would split identical customers at random.
--   1 order -> 1 | 2 orders -> 3 | 3 orders -> 4 | 4+ orders -> 5
-- =============================================================================
CREATE OR REPLACE TABLE analytics.customer_rfm AS
WITH scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY recency DESC, customer_unique_id)    AS r_score, -- 5 = most recent
        CASE WHEN frequency >= 4 THEN 5
             WHEN frequency = 3  THEN 4
             WHEN frequency = 2  THEN 3
             ELSE 1 END                                               AS f_score,
        NTILE(5) OVER (ORDER BY monetary, customer_unique_id)        AS m_score
    FROM analytics.customer_360
)
SELECT
    *,
    r_score + f_score + m_score                         AS rfm_score,
    CAST(r_score AS VARCHAR) || CAST(f_score AS VARCHAR) || CAST(m_score AS VARCHAR) AS rfm_cell,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 4 AND f_score >= 3                  THEN 'Loyal Customers'
        WHEN r_score >= 4                                   THEN 'New / Promising'
        WHEN r_score <= 2 AND f_score >= 4 AND m_score >= 4 THEN 'Can''t Lose Them'
        WHEN r_score <= 2 AND f_score >= 3                  THEN 'At Risk'
        WHEN r_score <= 2                                   THEN 'Hibernating / Lost'
        WHEN f_score >= 3                                   THEN 'Potential Loyalists'
        ELSE 'Needs Attention'
    END AS customer_segment
FROM scored;
