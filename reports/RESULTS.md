# RetailPulse — Results

_Generated automatically by `retailpulse run` on 2026-10-10T16:54:46+00:00. Every number below comes from that run; re-running regenerates this file._

## Dataset
| Metric | Value |
|---|---|
| Order window | 2016-09-04 → 2018-09-04 |
| Orders (excl. canceled/unavailable) | 98,199 |
| Customers (customer_unique_id) | 94,983 |
| Revenue (items + freight) | R$ 15,740,217 |
| Average order value | R$ 160.29 |
| Repeat-customer rate | 3.04% |

## Key insights
1. **Retention, not acquisition, is the gap.** Only 3.0% of 94,983 customers ever placed a second order, and in a typical 120-day window only 0.82% of existing customers return.
2. **New / Promising** is the largest revenue segment (38.5% of revenue, 38.7% of customers); 40.0% of customers sit in lapsed segments (Hibernating/Lost, At Risk, Can't Lose Them).
3. **Return is hard to predict but rankable.** The best model (Logistic Regression) reaches ROC-AUC 0.607 ± 0.011; targeting its top-10% list finds returning customers at 2.1x the base rate.
4. **What predicts return:** `avg_review_score`, `avg_order_value`, `avg_installments` are the strongest signals; customer-experience features (`avg_review_score`, `min_review_score`) rank in the top 5, a lever operations controls (predictive association, not proven causation).
5. **The original CLV proxy is unusable.** In a 180-day holdout it forecast 347x the revenue customers actually spent; BG/NBD + Gamma-Gamma landed within 11.5% of actual revenue.
6. **P1 cohort:** 4,420 high-value / high-risk customers hold R$ 36,261 of 12-month CLV at risk.

## RFM segments
| Segment | Customers | % customers | Revenue | % revenue | AOV | Avg 12m CLV | Avg churn p |
|---|---|---|---|---|---|---|---|
| New / Promising | 36,757 | 38.7% | R$ 6,053,917 | 38.5% | R$ 165 | R$ 3.35 | 0.991 |
| Hibernating / Lost | 36,965 | 38.9% | R$ 6,000,589 | 38.1% | R$ 162 | R$ 1.54 | 0.995 |
| Needs Attention | 18,374 | 19.3% | R$ 2,794,728 | 17.8% | R$ 152 | R$ 2.03 | 0.994 |
| Loyal Customers | 1,112 | 1.2% | R$ 328,411 | 2.1% | R$ 148 | R$ 10.67 | 0.961 |
| At Risk | 968 | 1.0% | R$ 273,045 | 1.7% | R$ 141 | R$ 2.83 | 0.985 |
| Potential Loyalists | 623 | 0.7% | R$ 191,482 | 1.2% | R$ 147 | R$ 5.69 | 0.975 |
| Champions | 123 | 0.1% | R$ 69,215 | 0.4% | R$ 161 | R$ 58.81 | 0.845 |
| Can't Lose Them | 61 | 0.1% | R$ 28,829 | 0.2% | R$ 153 | R$ 7.73 | 0.964 |

## Churn model — time-aware validation
Churn = no order in the 120 days after the snapshot. 15 monthly snapshots (2017-03-13 → 2018-05-07), 478,272 customer-snapshot rows. Each fold trains only on snapshots whose label window closed before the test snapshot.

| Model | ROC-AUC | PR-AUC (return) | Top-10% lift | Precision | Recall | F1 | Brier |
|---|---|---|---|---|---|---|---|
| Logistic Regression ✅ | 0.607 ± 0.011 | 0.021 ± 0.002 | 2.08x | 0.992 | 1.000 | 0.996 | 0.0082 |
| Random Forest | 0.570 ± 0.009 | 0.020 ± 0.003 | 1.86x | 0.992 | 1.000 | 0.996 | 0.0081 |
| Gradient Boosting (HistGB) | 0.569 ± 0.006 | 0.014 ± 0.002 | 1.67x | 0.992 | 1.000 | 0.996 | 0.0082 |

Base churn rate ≈ 99.2%: precision / recall / F1 for the churn class are near 1 for *any* model and should not be quoted as model quality. ROC-AUC, PR-AUC for the rare *return* class and top-decile lift are the honest measures.

### Feature importance (permutation, Δ ROC-AUC on the last test snapshot)
| Feature | Importance | Std |
|---|---|---|
| `avg_review_score` | 0.0196 | 0.0078 |
| `avg_order_value` | 0.0138 | 0.0079 |
| `avg_installments` | 0.0092 | 0.0098 |
| `last_order_value` | 0.0091 | 0.0062 |
| `min_review_score` | 0.0068 | 0.0038 |
| `orders_last_90d` | 0.0059 | 0.0063 |
| `monetary` | 0.0057 | 0.0036 |
| `customer_state` | 0.0053 | 0.0043 |
| `last_order_late` | 0.0039 | 0.0026 |
| `frequency` | 0.0033 | 0.0023 |
| `recency_days` | 0.0025 | 0.0081 |
| `avg_items_per_order` | 0.0025 | 0.0008 |

## CLV — holdout backtest
Calibrated on orders before 2018-03-08, scored on the next 180 days (58,323 customers, 661 returned).

| Model | Predicted revenue | Actual revenue | Total error | MAE / customer | Top-10% revenue capture |
|---|---|---|---|---|---|
| BG/NBD + Gamma-Gamma | R$ 119,308 | R$ 106,993 | 11.5% | R$ 3.80 | 22.2% |
| Heuristic proxy (original) | R$ 37,095,442 | R$ 106,993 | 34570.9% | R$ 634.58 | 14.7% |

Total predicted 12-month CLV of the current base: R$ 243,173.

## Retention priority
High value = top 25% of predicted 12-month CLV. Risk tiers are churn-probability quantiles (High ≥ 0.995, Medium ≥ 0.993).

| Priority | Customers | Historical revenue | Predicted 12m CLV | CLV at risk | Avg churn p |
|---|---|---|---|---|---|
| P1 - High Value / High Risk | 4,420 | R$ 3,156,413 | R$ 36,377 | R$ 36,261 | 0.996 |
| P2 - High Value / Medium Risk | 3,789 | R$ 1,471,047 | R$ 20,477 | R$ 20,359 | 0.994 |
| P3 - Low Value / High Risk | 19,326 | R$ 2,162,199 | R$ 21,359 | R$ 21,272 | 0.996 |
| P4 - Protect & Grow | 15,537 | R$ 4,217,200 | R$ 92,610 | R$ 89,171 | 0.986 |
| Standard Lifecycle | 51,911 | R$ 4,733,358 | R$ 72,349 | R$ 71,751 | 0.992 |

## Limitations
- Observational data: associations, not causal effects of interventions.
- The churn horizon is a business assumption (`--churn-horizon`); test sensitivity.
- BG/NBD gives every one-time buyer P(alive) = 1 by construction; churn probability from the classifier is the better risk signal, CLV the better value signal.
- Revenue is GMV (item price + freight), not margin.
