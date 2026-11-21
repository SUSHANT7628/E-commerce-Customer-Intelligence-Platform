# Power BI executive dashboard (4 pages)

The Power BI report reads the **PostgreSQL warehouse** built by `retailpulse postgres-build`
(or by `docker compose up`, which starts PostgreSQL on `localhost:5432`). The Streamlit app
(`retailpulse dashboard`) shows the same four pages with zero setup.

Save the finished report as `dashboard/RetailPulse.pbix` and its page screenshots as
`dashboard/screenshots/page1.png` … `page4.png`.

## 1. Connect to PostgreSQL

Power BI Desktop → **Get data → PostgreSQL database**

| Field | Value (docker compose defaults) |
|---|---|
| Server | `localhost:5432` |
| Database | `retailpulse` |
| Data connectivity mode | Import |
| User / password | `retailpulse` / `retailpulse` |

Load these tables from the `analytics` schema:

| Table | Grain | Built by |
|---|---|---|
| `customer_360_clv` | one row per customer: RFM scores, segment, 12-month CLV, P(alive), churn probability, priority, action | models (`retailpulse run`), loaded into PostgreSQL |
| `monthly_kpis` | one row per month | `sql/postgres/04_business_marts.sql` |
| `category_performance` | one row per product category | `sql/postgres/04_business_marts.sql` |
| `product_performance` | one row per product | `sql/postgres/04_business_marts.sql` |
| `seller_performance` | one row per seller | `sql/postgres/04_business_marts.sql` |
| `state_performance` | one row per customer state | `sql/postgres/04_business_marts.sql` |

Set `monthly_kpis[month]` to type **Date**. The tables are pre-aggregated, so no relationships are
required. Create the measures in [`measures.dax`](measures.dax) (Modeling → New measure, one per
block).

No PostgreSQL? Run `retailpulse run` and load the same tables from `artifacts/exports/*.csv`
with **Get data → Text/CSV**.

## 2. Pages

Every visual answers a business question. Avoid decorative charts.

**Page 1: Executive Overview.** Where does revenue come from?
- Cards: Total Revenue, Total Orders, Customers, Average Order Value, Revenue Growth MoM
- Line chart: `monthly_kpis[revenue]` by `month`
- Bar chart: Category Revenue by `category` (top 15)
- Filled map (or bar): `state_performance[revenue]` by `customer_state`

**Page 2: Customer Intelligence.** Who are our customers and what are they worth?
- Cards: Active Customers (180d), Repeat Customer Rate, Average CLV, Total Predicted CLV
- Clustered bar chart: Customers and Total Revenue by `customer_segment` (7 RFM segments)
- Matrix: `r_score` rows × `m_score` columns, values = Customers
- Histogram (binned column chart): `predicted_12m_clv`
- Slicer: `customer_segment`

**Page 3: Churn & Retention.** Who should the retention team call first?
- Cards: Average Churn Probability, High Risk Customers, High Value High Risk, P1 CLV At Risk
- Scatter chart: x = `churn_probability`, y = `predicted_12m_clv`, legend = `retention_priority`
- Bar chart: Customers by `retention_priority`
- Table: P1 customers sorted by `clv_at_risk` with `recommended_action`, filtered to `retention_priority` starting with "P1"

**Page 4: Product & Seller.** Which products and sellers drive revenue and experience?
- Bar charts: top 15 categories and top 15 products by revenue
- Scatter chart: `seller_performance` `avg_review_score` vs `revenue`, size = `orders`, colour = `late_delivery_rate`
- Card: Top 10% Seller Revenue Share

## 3. Theme

Use one accent colour for revenue and a red for risk, consistently on every page. Put page titles
in a header band, and keep cards in a single row at the top of each page.
