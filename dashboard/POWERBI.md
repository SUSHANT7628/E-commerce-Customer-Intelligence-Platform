# Power BI report

The Streamlit app (`retailpulse dashboard`) is the zero-setup dashboard. If you prefer
Power BI, the same four pages can be built from the CSV exports.

## 1. Load data
Run `retailpulse run`, then in Power BI Desktop → **Get data → Text/CSV** and load every
file in `artifacts/exports/`:

| Table | Grain |
|---|---|
| `customer_360_clv` | one row per customer: RFM, segment, CLV, churn probability, priority |
| `monthly_kpis` | one row per month |
| `category_performance` | one row per product category |
| `product_performance` | top 2,000 products |
| `seller_performance` | one row per seller |
| `state_performance` | one row per customer state |

Set `monthly_kpis[month]` to type **Date**. The tables are pre-aggregated, so no
relationships are required. Paste the measures from `measures.dax`.

## 2. Pages
Every visual answers a business question — avoid decorative charts.

**Executive Overview** — cards: Total Revenue, Total Orders, Customers, Average Order Value,
Revenue Growth MoM · line: `monthly_kpis` revenue by month · bar: Category Revenue by
category (top 15) · map/bar: `state_performance` revenue by state.

**Customer Intelligence** — cards: Active Customers (180d), Repeat Customer Rate, Average
CLV · bars: Customers and Total Revenue by `customer_segment` · matrix: `r_score` × `m_score`
count · histogram: `predicted_12m_clv`.

**Churn & Retention** — cards: Average Churn Probability, High Risk Customers, High Value
High Risk, P1 CLV At Risk · scatter: `churn_probability` vs `predicted_12m_clv` coloured by
`retention_priority` · bar: Customers by `retention_priority` · table: P1 customers sorted
by `clv_at_risk` with `recommended_action`.

**Product & Seller** — bars: top categories and top products by revenue · scatter:
`seller_performance` avg_review_score vs revenue (size = orders, colour =
late_delivery_rate) · card: Top 10% Seller Revenue Share.
