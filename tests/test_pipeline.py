import json

import pytest
from fastapi.testclient import TestClient

from retailpulse import warehouse
from retailpulse.config import OLIST_FILES


def test_synthetic_data_has_olist_schema(synthetic_dir):
    for stem in OLIST_FILES:
        assert (synthetic_dir / f"{stem}.csv").exists()


def test_warehouse_integrity(run_result):
    s, _ = run_result
    con = warehouse.connect(s.warehouse_path, read_only=True)
    try:
        one = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
        # one row per real customer
        assert one("SELECT COUNT(*) - COUNT(DISTINCT customer_unique_id) FROM analytics.customer_360") == 0
        # canceled orders excluded
        assert one("SELECT COUNT(*) FROM staging.orders WHERE order_status IN ('canceled','unavailable')") == 0
        # revenue reconciles across layers
        rev_orders = one("SELECT SUM(order_revenue) FROM staging.orders")
        rev_c360 = one("SELECT SUM(total_revenue) FROM analytics.customer_360")
        assert rev_orders == pytest.approx(rev_c360)
        # every customer scored exactly once
        assert one("SELECT COUNT(*) FROM analytics.customer_360_clv") == one("SELECT COUNT(*) FROM analytics.customer_360")
        assert one("SELECT COUNT(*) FROM analytics.customer_360_clv WHERE churn_probability IS NULL "
                   "OR predicted_12m_clv IS NULL OR retention_priority IS NULL") == 0
        assert one("SELECT MIN(churn_probability) >= 0 AND MAX(churn_probability) <= 1 "
                   "FROM analytics.customer_360_clv")
        scores = one("SELECT COUNT(*) FROM analytics.customer_rfm WHERE r_score NOT BETWEEN 1 AND 5 "
                     "OR m_score NOT BETWEEN 1 AND 5")
        assert scores == 0
    finally:
        con.close()


def test_pipeline_outputs(run_result):
    s, m = run_result
    assert s.model_path.exists()
    assert (s.artifacts_dir / "RESULTS.md").read_text().startswith("# RetailPulse — Results")
    for name in ("customer_360_clv", "monthly_kpis", "seller_performance"):
        assert (s.exports_dir / f"{name}.csv").exists()
    saved = json.loads(s.metrics_path.read_text())
    assert saved["churn"]["best_model"] in {"logistic_regression", "random_forest", "gradient_boosting"}
    # Synthetic data has real signal: the model must beat random ranking.
    best = next(r for r in m["churn"]["cv_summary"] if r["model"] == m["churn"]["best_model"])
    assert best["roc_auc_mean"] > 0.6


def test_api(run_result, monkeypatch):
    s, _ = run_result
    monkeypatch.setenv("RETAILPULSE_ARTIFACTS_DIR", str(s.artifacts_dir))
    from retailpulse import api
    api.settings.cache_clear()
    api._bundle.cache_clear()
    c = TestClient(api.app)

    assert c.get("/health").json()["model"] is True
    assert c.get("/kpis").json()["customers"] > 0
    assert len(c.get("/segments").json()) > 0
    top = c.get("/customers", params={"priority": "P1", "limit": 5}).json()
    assert len(top) <= 5
    cid = c.get("/customers", params={"limit": 1}).json()[0]["customer_unique_id"]
    assert c.get(f"/customers/{cid}").json()["customer_unique_id"] == cid
    assert c.get("/customers/does-not-exist").status_code == 404

    pred = c.post("/predict/churn", json=[
        {"recency_days": 10, "frequency": 3, "monetary": 450, "tenure_days": 200,
         "avg_review_score": 5, "customer_state": "SP"},
        {"recency_days": 400, "frequency": 1, "monetary": 60, "avg_review_score": 1, "late_delivery_rate": 1},
    ]).json()
    assert all(0 <= p["churn_probability"] <= 1 for p in pred)
    assert pred[0]["churn_probability"] < pred[1]["churn_probability"]
    assert "validation" in c.get("/model").json()
