"""RetailPulse dashboard — 4 pages, each visual answers a business question.

Run: `retailpulse dashboard` (or `streamlit run dashboard/app.py`).
"""
from __future__ import annotations

import json

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from retailpulse.config import Settings

st.set_page_config(page_title="RetailPulse", page_icon="📊", layout="wide")
S = Settings()
ACCENT = "#2563eb"
PRIORITY_COLORS = {
    "P1 - High Value / High Risk": "#dc2626",
    "P2 - High Value / Medium Risk": "#f59e0b",
    "P3 - Low Value / High Risk": "#a855f7",
    "P4 - Protect & Grow": "#16a34a",
    "Standard Lifecycle": "#94a3b8",
}


@st.cache_data(show_spinner=False)
def q(sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(S.warehouse_path), read_only=True)
    try:
        return con.execute(sql).df()
    finally:
        con.close()


@st.cache_data(show_spinner=False)
def metrics() -> dict:
    return json.loads(S.metrics_path.read_text()) if S.metrics_path.exists() else {}


def brl(v: float) -> str:
    if abs(v) >= 1e6:
        return f"R$ {v / 1e6:,.2f}M"
    if abs(v) >= 1e3:
        return f"R$ {v / 1e3:,.1f}K"
    return f"R$ {v:,.2f}"


def chart(fig, height: int = 360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")


if not S.warehouse_path.exists():
    st.error("No warehouse found. Run `retailpulse download` then `retailpulse run` "
             "(or `retailpulse run --synthetic`) first.")
    st.stop()

M = metrics()
st.sidebar.title("📊 RetailPulse")
page = st.sidebar.radio("Page", ["Executive Overview", "Customer Intelligence", "Churn & Retention",
                                 "Product & Seller"])
states = q("SELECT DISTINCT customer_state FROM analytics.customer_360_clv ORDER BY 1")["customer_state"].tolist()
state = st.sidebar.selectbox("Customer state", ["All"] + states)
where = "" if state == "All" else f"WHERE customer_state = '{state}'"
if M:
    st.sidebar.caption(f"Data: {M['data']['window_start']} → {M['data']['window_end']}  \n"
                       f"Model run: {M['generated_at'][:16].replace('T', ' ')} UTC")

# ---------------------------------------------------------------------------
if page == "Executive Overview":
    st.title("Executive Overview")
    monthly = q("SELECT * FROM analytics.monthly_kpis ORDER BY month")
    # Drop the trailing partial month so growth isn't distorted.
    full = monthly[monthly["orders"] >= monthly["orders"].median() * 0.3]
    tot = q(f"""SELECT SUM(total_revenue) rev, SUM(order_count) orders, COUNT(*) customers
                FROM analytics.customer_360_clv {where}""").iloc[0]
    last, prev = full.iloc[-1], full.iloc[-2]
    c = st.columns(5)
    c[0].metric("Revenue", brl(tot.rev))
    c[1].metric("Orders", f"{int(tot.orders):,}")
    c[2].metric("Customers", f"{int(tot.customers):,}")
    c[3].metric("Avg order value", brl(tot.rev / tot.orders))
    c[4].metric(f"Revenue growth ({pd.Timestamp(last.month):%b %Y})",
                f"{last.revenue / prev.revenue - 1:+.1%}", help="Month over month, last complete month")

    st.subheader("Is revenue growing?")
    chart(px.area(full, x="month", y="revenue", labels={"revenue": "Revenue (R$)", "month": ""},
                  color_discrete_sequence=[ACCENT]))
    left, right = st.columns(2)
    with left:
        st.subheader("Which categories drive revenue?")
        cat = q("SELECT category, revenue FROM analytics.category_performance ORDER BY revenue DESC LIMIT 15")
        chart(px.bar(cat.iloc[::-1], x="revenue", y="category", orientation="h",
                     labels={"revenue": "Revenue (R$)", "category": ""}, color_discrete_sequence=[ACCENT]), 480)
    with right:
        st.subheader("Where are our customers?")
        st_df = q("SELECT customer_state, revenue, customers FROM analytics.state_performance ORDER BY revenue DESC")
        chart(px.bar(st_df, x="customer_state", y="revenue", hover_data=["customers"],
                     labels={"revenue": "Revenue (R$)", "customer_state": "State"},
                     color_discrete_sequence=[ACCENT]), 480)

# ---------------------------------------------------------------------------
elif page == "Customer Intelligence":
    st.title("Customer Intelligence")
    k = q(f"""SELECT COUNT(*) FILTER (WHERE recency <= 180) active, AVG(is_repeat_customer) repeat_rate,
                     AVG(predicted_12m_clv) avg_clv, SUM(predicted_12m_clv) total_clv
              FROM analytics.customer_360_clv {where}""").iloc[0]
    c = st.columns(4)
    c[0].metric("Active customers (≤180 days)", f"{int(k.active):,}")
    c[1].metric("Repeat-customer rate", f"{k.repeat_rate:.2%}")
    c[2].metric("Avg predicted 12-month CLV", brl(k.avg_clv))
    c[3].metric("Total predicted 12-month CLV", brl(k.total_clv))

    seg = q(f"""SELECT customer_segment, COUNT(*) customers, SUM(total_revenue) revenue,
                       AVG(avg_order_value) aov, AVG(predicted_12m_clv) avg_clv
                FROM analytics.customer_360_clv {where} GROUP BY 1 ORDER BY revenue DESC""")
    left, right = st.columns(2)
    with left:
        st.subheader("How are customers distributed across segments?")
        chart(px.bar(seg, x="customer_segment", y="customers", labels={"customer_segment": ""},
                     color_discrete_sequence=[ACCENT]))
    with right:
        st.subheader("Which segments generate revenue?")
        chart(px.bar(seg, x="customer_segment", y="revenue", hover_data=["aov", "avg_clv"],
                     labels={"customer_segment": "", "revenue": "Revenue (R$)"}, color_discrete_sequence=[ACCENT]))
    left, right = st.columns(2)
    with left:
        st.subheader("RFM: recency × monetary (customers)")
        rfm = q(f"""SELECT r_score, m_score, COUNT(*) n FROM analytics.customer_360_clv {where}
                    GROUP BY 1, 2""").pivot(index="r_score", columns="m_score", values="n").sort_index(ascending=False)
        chart(px.imshow(rfm, text_auto=True, color_continuous_scale="Blues", aspect="auto",
                        labels=dict(x="Monetary score", y="Recency score (5 = most recent)", color="Customers")))
    with right:
        st.subheader("How is predicted CLV distributed?")
        clv = q(f"SELECT predicted_12m_clv FROM analytics.customer_360_clv {where}")
        chart(px.histogram(clv, x="predicted_12m_clv", nbins=80, log_y=True,
                           labels={"predicted_12m_clv": "Predicted 12-month CLV (R$)"},
                           color_discrete_sequence=[ACCENT]))
    st.caption("CLV: BG/NBD (purchase frequency & survival) × Gamma-Gamma (spend), 12-month horizon.")

# ---------------------------------------------------------------------------
elif page == "Churn & Retention":
    st.title("Churn & Retention")
    ch = M.get("churn", {})
    k = q(f"""SELECT COUNT(*) FILTER (WHERE risk_tier = 'High') high_risk,
                     COUNT(*) FILTER (WHERE retention_priority LIKE 'P1%') p1,
                     SUM(clv_at_risk) FILTER (WHERE retention_priority LIKE 'P1%') p1_clv
              FROM analytics.customer_360_clv {where}""").iloc[0]
    c = st.columns(4)
    if ch:
        c[0].metric(f"{ch['horizon_days']}-day churn rate", f"{ch['validation_churn_rate']:.1%}",
                    help="Share of existing customers with no order in the following window (validation folds)")
    c[1].metric("High-risk customers", f"{int(k.high_risk):,}")
    c[2].metric("High-value & high-risk (P1)", f"{int(k.p1):,}")
    c[3].metric("P1 CLV at risk", brl(k.p1_clv or 0))

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Where do value and risk collide?")
        pts = q(f"""SELECT customer_unique_id, predicted_12m_clv, churn_probability, retention_priority
                    FROM analytics.customer_360_clv {where} USING SAMPLE 6000 ROWS""")
        chart(px.scatter(pts, x="churn_probability", y="predicted_12m_clv", color="retention_priority",
                         color_discrete_map=PRIORITY_COLORS, log_y=True, opacity=0.6,
                         labels={"churn_probability": "Churn probability", "predicted_12m_clv": "Predicted 12m CLV (R$)"}),
              440)
    with right:
        st.subheader("How big is each retention cohort?")
        pr = q(f"""SELECT retention_priority, COUNT(*) customers, SUM(clv_at_risk) clv_at_risk
                   FROM analytics.customer_360_clv {where} GROUP BY 1 ORDER BY 1""")
        chart(px.bar(pr, x="customers", y="retention_priority", orientation="h", color="retention_priority",
                     color_discrete_map=PRIORITY_COLORS, hover_data=["clv_at_risk"],
                     labels={"retention_priority": ""}).update_layout(showlegend=False), 440)

    st.subheader("Who should the retention team call first?")
    top = q(f"""SELECT customer_unique_id, customer_state, customer_segment, order_count, total_revenue,
                       recency, avg_review_score, ROUND(predicted_12m_clv, 2) predicted_12m_clv,
                       ROUND(churn_probability, 4) churn_probability, ROUND(clv_at_risk, 2) clv_at_risk,
                       recommended_action
                FROM analytics.customer_360_clv
                {where + ' AND' if where else 'WHERE'} retention_priority LIKE 'P1%'
                ORDER BY clv_at_risk DESC LIMIT 100""")
    st.dataframe(top, width="stretch", hide_index=True)
    st.download_button("Download P1 list (CSV)", top.to_csv(index=False), "p1_customers.csv", "text/csv")

    if ch:
        st.subheader("How good is the churn model? (time-aware validation)")
        cv = pd.DataFrame(ch["cv_summary"])[["model", "roc_auc_mean", "roc_auc_std", "pr_auc_return_mean",
                                             "return_lift_top10pct_mean", "brier_mean"]]
        st.dataframe(cv.round(4), width="stretch", hide_index=True)
        imp = pd.DataFrame(ch["feature_importance"])
        chart(px.bar(imp.iloc[::-1], x="importance_mean", y="feature", orientation="h", error_x="importance_std",
                     labels={"importance_mean": "Permutation importance (Δ ROC-AUC)", "feature": ""},
                     color_discrete_sequence=[ACCENT], title="What predicts churn?"), 420)

# ---------------------------------------------------------------------------
else:
    st.title("Product & Seller")
    left, right = st.columns(2)
    with left:
        st.subheader("Top categories by revenue")
        cat = q("SELECT * FROM analytics.category_performance ORDER BY revenue DESC LIMIT 15")
        chart(px.bar(cat.iloc[::-1], x="revenue", y="category", orientation="h", hover_data=["orders", "avg_review_score"],
                     labels={"revenue": "Revenue (R$)", "category": ""}, color_discrete_sequence=[ACCENT]), 480)
    with right:
        st.subheader("Top products by revenue")
        prod = q("SELECT LEFT(product_id, 10) || '…' AS product, category, revenue, items_sold "
                 "FROM analytics.product_performance ORDER BY revenue DESC LIMIT 15")
        chart(px.bar(prod.iloc[::-1], x="revenue", y="product", orientation="h", color="category",
                     labels={"revenue": "Revenue (R$)", "product": ""}), 480)
    left, right = st.columns(2)
    with left:
        st.subheader("How concentrated is seller revenue?")
        sel = q("SELECT revenue FROM analytics.seller_performance ORDER BY revenue DESC")
        sel["seller_rank_pct"] = (sel.index + 1) / len(sel)
        sel["cum_revenue_share"] = sel["revenue"].cumsum() / sel["revenue"].sum()
        chart(px.line(sel, x="seller_rank_pct", y="cum_revenue_share",
                      labels={"seller_rank_pct": "Share of sellers (ranked)", "cum_revenue_share": "Share of revenue"},
                      color_discrete_sequence=[ACCENT]).update_layout(xaxis_tickformat=".0%", yaxis_tickformat=".0%"))
    with right:
        st.subheader("Do better-reviewed sellers sell more?")
        s2 = q("SELECT * FROM analytics.seller_performance WHERE orders >= 20")
        chart(px.scatter(s2, x="avg_review_score", y="revenue", size="orders", color="late_delivery_rate",
                         color_continuous_scale="RdYlGn_r", log_y=True, hover_data=["seller_id", "seller_state"],
                         labels={"avg_review_score": "Avg review score", "revenue": "Revenue (R$)",
                                 "late_delivery_rate": "Late rate"}))
    st.caption("Sellers with ≥ 20 orders. Colour = share of orders delivered late.")
