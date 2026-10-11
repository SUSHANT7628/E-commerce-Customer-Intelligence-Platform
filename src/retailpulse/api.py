"""REST API over the scored warehouse and the trained churn model.

Run with `retailpulse serve` (docs at http://127.0.0.1:8000/docs).
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import __version__, warehouse
from .churn import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from .config import Settings

app = FastAPI(
    title="RetailPulse API",
    version=__version__,
    description="Customer 360, RFM segments, CLV, churn risk and retention priority.",
)

SORTABLE = Literal["clv_at_risk", "predicted_12m_clv", "churn_probability", "total_revenue", "recency"]


@lru_cache
def settings() -> Settings:
    return Settings()


def _query(sql: str, params: list | None = None) -> pd.DataFrame:
    path = settings().warehouse_path
    if not path.exists():
        raise HTTPException(503, "Warehouse not built yet. Run `retailpulse run` first.")
    con = warehouse.connect(path, read_only=True)
    try:
        return warehouse.query(con, sql, params)
    finally:
        con.close()


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


@lru_cache
def _bundle() -> dict:
    path = settings().model_path
    if not path.exists():
        raise HTTPException(503, "Model not trained yet. Run `retailpulse run` first.")
    return joblib.load(path)


@app.get("/health")
def health() -> dict:
    s = settings()
    return {"status": "ok", "version": __version__,
            "warehouse": s.warehouse_path.exists(), "model": s.model_path.exists()}


@app.get("/kpis")
def kpis() -> dict:
    row = _query("""
        SELECT COUNT(*) AS customers, SUM(total_revenue) AS revenue, SUM(order_count) AS orders,
               SUM(total_revenue) / SUM(order_count) AS avg_order_value,
               AVG(is_repeat_customer) AS repeat_rate,
               AVG(predicted_12m_clv) AS avg_predicted_12m_clv,
               SUM(clv_at_risk) AS total_clv_at_risk,
               AVG(churn_probability) AS avg_churn_probability,
               SUM(CASE WHEN retention_priority LIKE 'P1%' THEN 1 ELSE 0 END) AS p1_customers
        FROM analytics.customer_360_clv""")
    return _records(row)[0]


@app.get("/segments")
def segments() -> list[dict]:
    return _records(_query("""
        SELECT customer_segment, COUNT(*) AS customers, SUM(total_revenue) AS revenue,
               AVG(avg_order_value) AS avg_order_value, AVG(predicted_12m_clv) AS avg_predicted_12m_clv,
               AVG(churn_probability) AS avg_churn_probability
        FROM analytics.customer_360_clv GROUP BY 1 ORDER BY revenue DESC"""))


@app.get("/retention/priorities")
def priorities() -> list[dict]:
    return _records(_query("""
        SELECT retention_priority, ANY_VALUE(recommended_action) AS recommended_action,
               COUNT(*) AS customers, SUM(predicted_12m_clv) AS predicted_12m_clv,
               SUM(clv_at_risk) AS clv_at_risk, AVG(churn_probability) AS avg_churn_probability
        FROM analytics.customer_360_clv GROUP BY 1 ORDER BY 1"""))


@app.get("/customers")
def customers(
    segment: str | None = None,
    priority: str | None = Query(None, description="e.g. 'P1' or the full label"),
    state: str | None = None,
    sort_by: SORTABLE = "clv_at_risk",
    limit: int = Query(50, ge=1, le=1000),
) -> list[dict]:
    where, params = [], []
    if segment:
        where.append("customer_segment = ?"); params.append(segment)
    if priority:
        where.append("retention_priority LIKE ?"); params.append(priority + "%")
    if state:
        where.append("customer_state = ?"); params.append(state.upper())
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return _records(_query(f"""
        SELECT customer_unique_id, customer_state, customer_segment, order_count, total_revenue,
               recency, predicted_12m_clv, churn_probability, clv_at_risk, retention_priority,
               recommended_action
        FROM analytics.customer_360_clv {clause}
        ORDER BY {sort_by} DESC LIMIT {int(limit)}""", params))


@app.get("/customers/{customer_unique_id}")
def customer(customer_unique_id: str) -> dict:
    df = _query("SELECT * FROM analytics.customer_360_clv WHERE customer_unique_id = ?", [customer_unique_id])
    if df.empty:
        raise HTTPException(404, "customer not found")
    return _records(df)[0]


class CustomerFeatures(BaseModel):
    """Behavioural history as of the scoring date (see churn.snapshot_features)."""
    recency_days: float = Field(..., ge=0)
    frequency: int = Field(..., ge=1)
    monetary: float = Field(..., ge=0)
    avg_order_value: float | None = None
    last_order_value: float | None = None
    tenure_days: float = 0
    customer_age_days: float | None = None
    avg_days_between_orders: float | None = None
    avg_review_score: float | None = Field(None, ge=1, le=5)
    last_review_score: float | None = Field(None, ge=1, le=5)
    min_review_score: float | None = Field(None, ge=1, le=5)
    avg_delivery_days: float | None = None
    late_delivery_rate: float | None = Field(None, ge=0, le=1)
    last_order_late: float | None = Field(None, ge=0, le=1)
    avg_installments: float | None = None
    avg_items_per_order: float | None = None
    boleto_share: float | None = Field(None, ge=0, le=1)
    orders_last_90d: int = 0
    customer_state: str | None = None


@app.post("/predict/churn")
def predict_churn(items: list[CustomerFeatures]) -> list[dict]:
    b = _bundle()
    rows = []
    for it in items:
        d = it.model_dump()
        d["avg_order_value"] = d["avg_order_value"] or d["monetary"] / d["frequency"]
        d["last_order_value"] = d["last_order_value"] or d["avg_order_value"]
        d["customer_age_days"] = d["customer_age_days"] or d["recency_days"] + d["tenure_days"]
        rows.append(d)
    X = pd.DataFrame(rows)[FEATURES]
    X[NUMERIC_FEATURES] = X[NUMERIC_FEATURES].astype(float)
    X[CATEGORICAL_FEATURES] = X[CATEGORICAL_FEATURES].astype(object)
    p = b["model"].predict_proba(X)[:, 1]
    th = b["risk_thresholds"]
    return [{"churn_probability": float(v),
             "risk_tier": "High" if v >= th["high"] else "Medium" if v >= th["medium"] else "Low"} for v in p]


@app.get("/model")
def model_info() -> dict:
    b = _bundle()
    out = {k: b[k] for k in ("model_name", "features", "horizon_days", "risk_thresholds", "trained_at", "data_end")}
    mp = settings().metrics_path
    if mp.exists():
        m = json.loads(mp.read_text())
        out["validation"] = m["churn"]["cv_summary"]
        out["clv_backtest"] = m["clv"]["backtest"]
    return out
