"""Render the run's metrics into a Markdown results report (numbers come only from the run)."""
from __future__ import annotations

from .config import Settings

MODEL_LABELS = {
    "logistic_regression": "Logistic Regression",
    "random_forest": "Random Forest",
    "gradient_boosting": "Gradient Boosting (HistGB)",
}


def _money(v: float) -> str:
    return f"R$ {v:,.0f}" if v is not None else "n/a"


def _pct(v: float, d: int = 1) -> str:
    return f"{v * 100:.{d}f}%" if v is not None else "n/a"


def _f(v: float, d: int = 3) -> str:
    return f"{v:.{d}f}" if v is not None else "n/a"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def render(m: dict) -> str:
    d, ch, cl = m["data"], m["churn"], m["clv"]
    bt = cl["backtest"]
    best = ch["best_model"]
    cv = {r["model"]: r for r in ch["cv_summary"]}
    b = cv[best]
    segs = m["segments"]
    pri = {r["retention_priority"]: r for r in m["priority"]}
    seg_by = {s["customer_segment"]: s for s in segs}
    top_seg = segs[0]
    lapsed = sum(seg_by.get(k, {}).get("customer_share", 0) for k in ("Hibernating / Lost", "At Risk", "Can't Lose Them"))
    p1 = pri.get("P1 - High Value / High Risk", {})
    imp = ch["feature_importance"]

    insights = [
        f"**Retention, not acquisition, is the gap.** Only {_pct(d['repeat_customer_rate'])} of "
        f"{d['customers']:,} customers ever placed a second order, and in a typical "
        f"{ch['horizon_days']}-day window only {_pct(1 - _churn_rate(m), 2)} of existing customers return.",
        f"**{top_seg['customer_segment']}** is the largest revenue segment "
        f"({_pct(top_seg['revenue_share'])} of revenue, {_pct(top_seg['customer_share'])} of customers); "
        f"{_pct(lapsed)} of customers sit in lapsed segments (Hibernating/Lost, At Risk, Can't Lose Them).",
        f"**Return is hard to predict but rankable.** The best model ({MODEL_LABELS[best]}) reaches "
        f"ROC-AUC {_f(b['roc_auc_mean'])} ± {_f(b['roc_auc_std'])}; targeting its top-10% list finds "
        f"returning customers at {_f(b['return_lift_top10pct_mean'], 1)}x the base rate.",
        _importance_insight(imp),
        f"**The original CLV proxy is unusable.** In a {bt['holdout_days']}-day holdout it forecast "
        f"{bt['heuristic_proxy']['predicted_total'] / bt['heuristic_proxy']['actual_total']:,.0f}x the revenue "
        f"customers actually spent; BG/NBD + Gamma-Gamma landed within "
        f"{_pct(abs(bt['bgnbd_gamma_gamma']['total_error_pct']))} of actual revenue.",
        f"**P1 cohort:** {p1.get('customers', 0):,} high-value / high-risk customers hold "
        f"{_money(p1.get('clv_at_risk', 0))} of 12-month CLV at risk.",
    ]

    lines = [
        "# RetailPulse — Results",
        "",
        f"_Generated automatically by `retailpulse run` on {m['generated_at']}. "
        "Every number below comes from that run; re-running regenerates this file._",
        "",
        "## Dataset",
        _table(["Metric", "Value"], [
            ["Order window", f"{d['window_start']} → {d['window_end']}"],
            ["Orders (excl. canceled/unavailable)", f"{d['orders']:,}"],
            ["Customers (customer_unique_id)", f"{d['customers']:,}"],
            ["Revenue (items + freight)", _money(d["revenue"])],
            ["Average order value", f"R$ {d['avg_order_value']:,.2f}"],
            ["Repeat-customer rate", _pct(d["repeat_customer_rate"], 2)],
        ]),
        "",
        "## Key insights",
        *[f"{i}. {t}" for i, t in enumerate(insights, 1)],
        "",
        "## RFM segments",
        _table(["Segment", "Customers", "% customers", "Revenue", "% revenue", "AOV", "Avg 12m CLV", "Avg churn p"], [
            [s["customer_segment"], f"{s['customers']:,}", _pct(s["customer_share"]), _money(s["revenue"]),
             _pct(s["revenue_share"]), f"R$ {s['avg_order_value']:,.0f}", f"R$ {s['avg_predicted_clv']:,.2f}",
             _f(s["avg_churn_probability"])] for s in segs
        ]),
        "",
        "## Churn model — time-aware validation",
        f"Churn = {ch['definition']}. {len(ch['snapshots'])} monthly snapshots "
        f"({ch['snapshots'][0]} → {ch['snapshots'][-1]}), {ch['training_rows']:,} customer-snapshot rows. "
        "Each fold trains only on snapshots whose label window closed before the test snapshot.",
        "",
        _table(["Model", "ROC-AUC", "PR-AUC (return)", "Top-10% lift", "Precision", "Recall", "F1", "Brier"], [
            [MODEL_LABELS[r["model"]] + (" ✅" if r["model"] == best else ""),
             f"{_f(r['roc_auc_mean'])} ± {_f(r['roc_auc_std'])}",
             f"{_f(r['pr_auc_return_mean'])} ± {_f(r['pr_auc_return_std'])}",
             f"{_f(r['return_lift_top10pct_mean'], 2)}x",
             _f(r["precision_mean"]), _f(r["recall_mean"]), _f(r["f1_mean"]), _f(r["brier_mean"], 4)]
            for r in ch["cv_summary"]
        ]),
        "",
        f"Base churn rate ≈ {_pct(_churn_rate(m))}: precision / recall / F1 for the churn class are "
        "near 1 for *any* model and should not be quoted as model quality. ROC-AUC, PR-AUC for the "
        "rare *return* class and top-decile lift are the honest measures.",
        "",
        "### Feature importance (permutation, Δ ROC-AUC on the last test snapshot)",
        _table(["Feature", "Importance", "Std"], [
            [f"`{r['feature']}`", _f(r["importance_mean"], 4), _f(r["importance_std"], 4)] for r in imp
        ]),
        "",
        "## CLV — holdout backtest",
        f"Calibrated on orders before {bt['calibration_end']}, scored on the next {bt['holdout_days']} days "
        f"({bt['customers']:,} customers, {bt['customers_returning_in_holdout']:,} returned).",
        "",
        _table(["Model", "Predicted revenue", "Actual revenue", "Total error", "MAE / customer",
                "Top-10% revenue capture"], [
            [name, _money(r["predicted_total"]), _money(r["actual_total"]), _pct(r["total_error_pct"]),
             f"R$ {r['mae']:,.2f}", _pct(r["top_decile_revenue_capture"])]
            for name, r in (("BG/NBD + Gamma-Gamma", bt["bgnbd_gamma_gamma"]),
                            ("Heuristic proxy (original)", bt["heuristic_proxy"]))
        ]),
        "",
        f"Total predicted 12-month CLV of the current base: {_money(cl['total_predicted_12m_clv'])}.",
        "",
        "## Retention priority",
        f"High value = top {_pct(1 - m['priority_config']['high_value_quantile'], 0)} of predicted 12-month CLV. Risk tiers are churn-probability "
        f"quantiles (High ≥ {_f(ch['risk_thresholds']['high'])}, Medium ≥ {_f(ch['risk_thresholds']['medium'])}).",
        "",
        _table(["Priority", "Customers", "Historical revenue", "Predicted 12m CLV", "CLV at risk", "Avg churn p"], [
            [r["retention_priority"], f"{r['customers']:,}", _money(r["historical_revenue"]),
             _money(r["predicted_12m_clv"]), _money(r["clv_at_risk"]), _f(r["avg_churn_probability"])]
            for r in m["priority"]
        ]),
        "",
        "## Limitations",
        "- Observational data: associations, not causal effects of interventions.",
        "- The churn horizon is a business assumption (`--churn-horizon`); test sensitivity.",
        "- BG/NBD gives every one-time buyer P(alive) = 1 by construction; churn probability "
        "from the classifier is the better risk signal, CLV the better value signal.",
        "- Revenue is GMV (item price + freight), not margin.",
        "",
    ]
    return "\n".join(lines)


EXPERIENCE_FEATURES = {"avg_review_score", "last_review_score", "min_review_score", "late_delivery_rate",
                       "last_order_late", "avg_delivery_days"}


def _importance_insight(imp: list[dict]) -> str:
    top = [r["feature"] for r in imp[:3]]
    text = f"**What predicts return:** {', '.join('`' + f + '`' for f in top)} are the strongest signals"
    exp = [r["feature"] for r in imp[:5] if r["feature"] in EXPERIENCE_FEATURES]
    if exp:
        text += (f"; customer-experience features ({', '.join('`' + f + '`' for f in exp)}) rank in the top 5, "
                 "a lever operations controls")
    return text + " (predictive association, not proven causation)."


def _churn_rate(m: dict) -> float:
    # Mean churn rate across the validation folds.
    return m["churn"].get("validation_churn_rate", 0.0)


def write_reports(metrics: dict, settings: Settings) -> None:
    (settings.artifacts_dir / "RESULTS.md").write_text(render(metrics))
