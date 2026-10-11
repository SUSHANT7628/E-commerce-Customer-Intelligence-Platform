"""End-to-end pipeline: raw CSVs -> warehouse -> models -> scored customers -> exports."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from . import churn, clv, priority, report, warehouse
from .config import Settings

log = logging.getLogger(__name__)

EXPORT_TABLES = {
    "customer_360_clv": "SELECT * FROM analytics.customer_360_clv",
    "monthly_kpis": "SELECT * FROM analytics.monthly_kpis",
    "category_performance": "SELECT * FROM analytics.category_performance",
    "product_performance": "SELECT * FROM analytics.product_performance LIMIT 2000",
    "seller_performance": "SELECT * FROM analytics.seller_performance",
    "state_performance": "SELECT * FROM analytics.state_performance",
}


def load_orders(con) -> pd.DataFrame:
    return warehouse.query(con, """
        SELECT order_id, customer_unique_id, customer_state, purchase_ts, order_revenue,
               n_items, installments, payment_type, review_score, delivery_days, is_late
        FROM staging.orders""")


def run(settings: Settings, n_folds: int = 4) -> dict:
    t_start = time.time()
    settings.ensure_dirs()
    con = warehouse.connect(settings.warehouse_path)
    try:
        raw_counts = warehouse.load_raw(con, settings.data_dir)
        warehouse.build(con)

        orders = load_orders(con)
        data_start = orders["purchase_ts"].min()
        data_end = (orders["purchase_ts"].max() + pd.Timedelta(days=1)).normalize()
        log.info("orders: %d  window: %s -> %s", len(orders), data_start.date(), data_end.date())

        # ---------------- Churn -----------------------------------------
        dates = churn.snapshot_dates(data_start, data_end, settings.churn_horizon_days,
                                     settings.snapshot_step_days, settings.min_history_days)
        if len(dates) < 3:
            raise ValueError("Not enough history for time-aware churn validation "
                             f"({len(dates)} snapshots). Use a longer dataset or smaller horizon.")
        train_df = churn.build_training_set(orders, dates, settings.churn_horizon_days)
        log.info("churn training set: %d rows over %d snapshots", len(train_df), len(dates))

        cv = churn.time_aware_validation(train_df, settings.churn_horizon_days, n_folds,
                                         settings.random_state)
        cv_summary = churn.summarise_validation(cv)
        best = churn.select_best(cv_summary)
        log.info("best churn model: %s", best)

        # Importance: train on data available before the last test snapshot, score on it.
        last_test = pd.Timestamp(cv["test_snapshot"].max())
        pre = train_df[train_df["snapshot_date"] + pd.Timedelta(days=settings.churn_horizon_days) <= last_test]
        te = train_df[train_df["snapshot_date"] == last_test]
        imp_model = churn.fit_final(pre, best, settings.random_state)
        importance = churn.feature_importance(imp_model, te[churn.FEATURES], te["churn"], settings.random_state)

        model = churn.fit_final(train_df, best, settings.random_state)
        current = churn.snapshot_features(orders, data_end)
        current["churn_probability"] = model.predict_proba(current[churn.FEATURES])[:, 1]

        # ---------------- CLV -------------------------------------------
        clv_backtest = clv.backtest_clv(orders, data_end, settings.clv_holdout_days)
        summary = clv.rfm_summary(orders, data_end)
        bg, gg = clv.fit_probabilistic(summary)
        clv_pred = clv.predict_clv(summary, bg, gg, settings.clv_horizon_days)
        clv_pred = clv_pred.rename(columns={
            "expected_orders": "expected_orders_12m",
            "predicted_clv": "predicted_12m_clv",
            "heuristic_clv": "heuristic_12m_clv",
        })

        # ---------------- Combine + priority -----------------------------
        rfm = warehouse.query(con, "SELECT * FROM analytics.customer_rfm").set_index("customer_unique_id")
        scores = rfm.join(clv_pred).join(current[["churn_probability"]])
        scores["churn_probability"] = scores["churn_probability"].fillna(scores["churn_probability"].median())
        scores["clv_at_risk"] = scores["predicted_12m_clv"] * scores["churn_probability"]

        # Risk tiers are relative to the score distribution: on a marketplace where
        # most buyers never return, fixed 0.7/0.4 cut-offs would flag nearly everyone.
        high_risk = float(scores["churn_probability"].quantile(settings.risk_high_quantile))
        medium_risk = float(scores["churn_probability"].quantile(settings.risk_medium_quantile))
        scores = priority.assign_priority(scores, "predicted_12m_clv", settings.high_value_quantile,
                                          high_risk, medium_risk)
        high_value_threshold = scores.attrs["high_value_threshold"]
        scores = scores.reset_index().rename(columns={"index": "customer_unique_id"})
        warehouse.write_table(con, scores, "analytics.customer_360_clv")

        # ---------------- Persist -----------------------------------------
        joblib.dump({
            "model": model, "model_name": best, "features": churn.FEATURES,
            "horizon_days": settings.churn_horizon_days,
            "risk_thresholds": {"high": high_risk, "medium": medium_risk},
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "data_end": str(data_end.date()),
            "clv_params": {"bgnbd": vars(bg), "gamma_gamma": vars(gg)},
        }, settings.model_path)

        for name, sql in EXPORT_TABLES.items():
            warehouse.query(con, sql).to_csv(settings.exports_dir / f"{name}.csv", index=False)
        cv.to_csv(settings.artifacts_dir / "churn_cv_folds.csv", index=False)
        importance.to_csv(settings.artifacts_dir / "feature_importance.csv", index=False)

        metrics = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "data": {
                "raw_rows": raw_counts,
                "window_start": str(data_start.date()),
                "window_end": str(data_end.date()),
                **_dataset_stats(con),
            },
            "segments": _segment_stats(scores),
            "churn": {
                "definition": f"no order in the {settings.churn_horizon_days} days after the snapshot",
                "horizon_days": settings.churn_horizon_days,
                "validation_churn_rate": float(cv["churn_rate"].mean()),
                "snapshots": [str(d.date()) for d in dates],
                "training_rows": int(len(train_df)),
                "best_model": best,
                "cv_summary": _records(cv_summary.reset_index()),
                "feature_importance": _records(importance.head(12)),
                "risk_thresholds": {"high": high_risk, "medium": medium_risk},
            },
            "clv": {
                "horizon_days": settings.clv_horizon_days,
                "params": {"bgnbd": vars(bg), "gamma_gamma": vars(gg)},
                "backtest": clv_backtest,
                "total_predicted_12m_clv": float(scores["predicted_12m_clv"].sum()),
            },
            "priority": _priority_stats(scores),
            "priority_config": {"high_value_quantile": settings.high_value_quantile,
                                "high_value_threshold": high_value_threshold},
            "runtime_seconds": round(time.time() - t_start, 1),
        }
        settings.metrics_path.write_text(json.dumps(_clean(metrics), indent=2))
        report.write_reports(_clean(metrics), settings)
        log.info("done in %.0fs -> %s", metrics["runtime_seconds"], settings.artifacts_dir)
        return metrics
    finally:
        con.close()


# ---------------------------------------------------------------------------
def _dataset_stats(con) -> dict:
    row = warehouse.query(con, """
        SELECT COUNT(*) AS orders, COUNT(DISTINCT customer_unique_id) AS customers,
               SUM(order_revenue) AS revenue, AVG(order_revenue) AS avg_order_value
        FROM staging.orders""").iloc[0]
    repeat = warehouse.query(con, "SELECT AVG(is_repeat_customer) AS r FROM analytics.customer_360").iloc[0, 0]
    return {"orders": int(row.orders), "customers": int(row.customers), "revenue": float(row.revenue),
            "avg_order_value": float(row.avg_order_value), "repeat_customer_rate": float(repeat)}


def _segment_stats(scores: pd.DataFrame) -> list[dict]:
    g = scores.groupby("customer_segment").agg(
        customers=("customer_unique_id", "count"), revenue=("total_revenue", "sum"),
        avg_order_value=("avg_order_value", "mean"), avg_predicted_clv=("predicted_12m_clv", "mean"),
        avg_churn_probability=("churn_probability", "mean"))
    g["customer_share"] = g["customers"] / g["customers"].sum()
    g["revenue_share"] = g["revenue"] / g["revenue"].sum()
    return _records(g.sort_values("revenue", ascending=False).reset_index())


def _priority_stats(scores: pd.DataFrame) -> list[dict]:
    g = scores.groupby("retention_priority").agg(
        customers=("customer_unique_id", "count"), historical_revenue=("total_revenue", "sum"),
        predicted_12m_clv=("predicted_12m_clv", "sum"), clv_at_risk=("clv_at_risk", "sum"),
        avg_churn_probability=("churn_probability", "mean"))
    g = g.reindex([p for p in priority.PRIORITY_ORDER if p in g.index])
    return _records(g.reset_index())


def _records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records"))


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if not np.isfinite(obj) else float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return obj
