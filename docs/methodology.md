# Methodology

## 1. Data
Brazilian E-Commerce Public Dataset by Olist (~100k orders, Sep 2016 – Sep 2018,
CC BY-NC-SA 4.0). `retailpulse download` fetches the CSVs from Olist's public GitHub
mirror; they are never committed.

Cleaning rules (`sql/01_staging.sql`):
- Orders with status `canceled` or `unavailable`, or with no items, are excluded.
- **Revenue = item price + freight** (GMV). `payment_value` is not used because it
  includes card-installment interest.
- An order is **late** if delivered more than one day after the estimated date.
- Duplicate reviews per order are averaged; the main payment type is the one with the
  largest value.

**Customer identity.** Olist issues a new `customer_id` for every order; the person is
`customer_unique_id`. Using `customer_id` (a common mistake) makes every customer look
like a one-time buyer.

## 2. Customer 360 and RFM (`sql/02`, `sql/03`)
One row per `customer_unique_id` with value, behaviour and experience features.

RFM: Recency and Monetary are quintiles (`NTILE(5)`, deterministic tie-break).
Frequency uses fixed bins (1 → 1, 2 → 3, 3 → 4, 4+ → 5) because ~97% of customers have
exactly one order — a frequency quintile would split identical customers at random.

| Segment | Rule |
|---|---|
| Champions | R ≥ 4, F ≥ 4, M ≥ 4 |
| Loyal Customers | R ≥ 4, F ≥ 3 |
| New / Promising | R ≥ 4, single order |
| Can't Lose Them | R ≤ 2, F ≥ 4, M ≥ 4 |
| At Risk | R ≤ 2, F ≥ 3 |
| Hibernating / Lost | R ≤ 2, single order |
| Potential Loyalists | R = 3, F ≥ 3 |
| Needs Attention | R = 3, single order |

## 3. Churn prediction (`src/retailpulse/churn.py`)

**The original design leaked its label.** Churn was defined as `recency ≥ 120` and
`recency` was also a feature, so any model could score perfectly by learning one
threshold. This version separates past from future:

- **Snapshots** every 30 days. At snapshot *t*, features use only orders before *t*.
- **Label:** churn = 1 if the customer places no order in [*t*, *t* + 120 days).
- **Validation:** expanding window. To test on snapshot *T*, models train only on
  snapshots whose label window closed on or before *T*. No future information reaches
  training.
- **Models:** Logistic Regression (baseline), Random Forest, HistGradientBoosting.
  No class re-weighting, so probabilities stay calibrated (Brier score reported).
- **Metrics:** with ~99% of customers churning in any 120-day window, precision / recall
  / F1 for the churn class are ~1 for any model and say nothing. The honest measures are
  ROC-AUC, PR-AUC for the rare *return* class, and lift in the top 10% of scores.
- **Selection:** highest mean ROC-AUC across folds (retention targeting is a ranking task).
- **Importance:** permutation importance (drop in ROC-AUC) on the last test snapshot,
  using a model trained only on earlier data. Predictive, not causal.

## 4. Customer Lifetime Value (`src/retailpulse/clv.py`)

**BG/NBD + Gamma-Gamma** (Fader, Hardie & Lee 2005; Fader & Hardie 2013), implemented
directly with numpy/scipy:
- Purchases are counted per day; time is in weeks.
- BG/NBD estimates expected purchases over the next 52 weeks and P(alive).
- Gamma-Gamma estimates spend per purchase, shrunk toward the population mean.
- Predicted 12-month CLV = expected purchases × expected spend.

**Backtest.** Both this model and the original heuristic (monthly run-rate × 12 ×
exp(−recency/365)) are fitted on data up to *end − 180 days* and scored on the final 180
days. The heuristic treats every one-time buyer as a monthly buyer and overstates
revenue by hundreds of times; see `reports/RESULTS.md` for the run's figures.

## 5. Retention priority (`src/retailpulse/priority.py`)
- **High value:** top 25% of predicted 12-month CLV.
- **Risk tiers:** quantiles of churn probability (top 25% = High, next 25% = Medium).
  Fixed cut-offs like 0.7 / 0.4 would flag nearly every Olist customer.
- **CLV at risk** = predicted CLV × churn probability.

| Priority | Rule | Action |
|---|---|---|
| P1 | High value, High risk | Personal outreach, service recovery, strong incentive |
| P2 | High value, Medium risk | Proactive nurture and loyalty perks |
| P3 | Standard value, High risk | Low-cost automated win-back |
| P4 | High value, Low risk | Protect & upsell, no discounting |
| Standard | everything else | Standard lifecycle marketing |

## 6. Known limitations
- Observational data: model associations are not intervention effects. For example,
  customers whose *worst* review was 1–2 stars have a higher repeat rate, because
  customers with more orders have more chances to leave a bad review.
- BG/NBD assigns P(alive) = 1 to every one-time buyer by construction; use the
  classifier's churn probability for risk and CLV for value.
- The 120-day horizon is an assumption (`retailpulse run --churn-horizon N`).
- Revenue is GMV, not margin.
