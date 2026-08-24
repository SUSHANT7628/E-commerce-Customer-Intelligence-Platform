# RetailPulse — Phase 3: CLV Framework

## Why CLV?
RFM tells us what customers have done. CLV estimates the economic value of retaining them.

## Core project metric
Predicted 12-month CLV is a transparent proxy:

`monthly revenue run-rate × 12 × recency factor`

The recency factor discounts customers who have become inactive.

## Important limitation
This is a portfolio analytics model, not a production-grade probabilistic CLV model. In a later iteration we can compare it with BG/NBD + Gamma-Gamma or another probabilistic framework.

## Business decision
Combine:
- predicted CLV
- recency
- customer segment

to create retention priority:
1. High CLV + high recency risk → urgent retention
2. High CLV + low recency risk → protect/upsell
3. Low CLV + high recency risk → low-cost automated win-back
4. Low CLV + low recency risk → standard lifecycle marketing
