"""Leak-free churn modelling with snapshot features and time-aware validation.

Why the original approach was broken: churn was *defined* as `recency >= 120` and
`recency` was also a model feature, so the model only had to learn a threshold on its
own label (perfect but meaningless scores).

Here, for every snapshot date `t`:
  * features use only orders placed **before** `t`;
  * the label looks **forward**: churn = 1 if the customer places no order in
    [t, t + horizon).
Validation is expanding-window: to test on snapshot `T`, models are trained only on
snapshots whose label window closed on or before `T`, so no future information is
used to train.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

log = logging.getLogger(__name__)

NUMERIC_FEATURES = [
    "recency_days", "frequency", "monetary", "avg_order_value", "last_order_value",
    "tenure_days", "customer_age_days", "avg_days_between_orders",
    "avg_review_score", "last_review_score", "min_review_score",
    "avg_delivery_days", "late_delivery_rate", "last_order_late",
    "avg_installments", "avg_items_per_order", "boleto_share",
    "orders_last_90d",
]
CATEGORICAL_FEATURES = ["customer_state"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


# ---------------------------------------------------------------------------
# Features & labels
# ---------------------------------------------------------------------------
def snapshot_features(orders: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Customer features computed only from orders strictly before `cutoff`."""
    h = orders.loc[orders["purchase_ts"] < cutoff].sort_values("purchase_ts")
    if h.empty:
        return pd.DataFrame(columns=FEATURES)
    h = h.assign(
        is_boleto=(h["payment_type"] == "boleto").astype(float),
        recent=(h["purchase_ts"] >= cutoff - pd.Timedelta(days=90)).astype(int),
    )
    g = h.groupby("customer_unique_id", sort=False)
    last = g.tail(1).set_index("customer_unique_id")
    f = pd.DataFrame({
        "first": g["purchase_ts"].min(),
        "last": g["purchase_ts"].max(),
        "frequency": g.size(),
        "monetary": g["order_revenue"].sum(),
        "avg_review_score": g["review_score"].mean(),
        "min_review_score": g["review_score"].min(),
        "avg_delivery_days": g["delivery_days"].mean(),
        "late_delivery_rate": g["is_late"].mean(),
        "avg_installments": g["installments"].mean(),
        "avg_items_per_order": g["n_items"].mean(),
        "boleto_share": g["is_boleto"].mean(),
        "orders_last_90d": g["recent"].sum(),
    })
    f["last_order_value"] = last["order_revenue"]
    f["last_review_score"] = last["review_score"]
    f["last_order_late"] = last["is_late"]
    f["customer_state"] = last["customer_state"]
    day = pd.Timedelta(days=1)
    f["recency_days"] = (cutoff - f["last"]) / day
    f["tenure_days"] = (f["last"] - f["first"]) / day
    f["customer_age_days"] = (cutoff - f["first"]) / day
    f["avg_order_value"] = f["monetary"] / f["frequency"]
    f["avg_days_between_orders"] = np.where(
        f["frequency"] > 1, f["tenure_days"] / (f["frequency"] - 1), np.nan)
    f["snapshot_date"] = cutoff
    return f[FEATURES + ["snapshot_date"]]


def label_snapshot(feats: pd.DataFrame, orders: pd.DataFrame, cutoff: pd.Timestamp,
                   horizon_days: int) -> pd.DataFrame:
    """Add churn = 1 if the customer did NOT order in [cutoff, cutoff + horizon)."""
    window = orders.loc[(orders["purchase_ts"] >= cutoff)
                        & (orders["purchase_ts"] < cutoff + pd.Timedelta(days=horizon_days))]
    returned = window["customer_unique_id"].unique()
    out = feats.copy()
    out["churn"] = (~out.index.isin(returned)).astype(int)
    return out


def snapshot_dates(data_start: pd.Timestamp, data_end: pd.Timestamp, horizon_days: int,
                   step_days: int, min_history_days: int) -> list[pd.Timestamp]:
    """Snapshot dates whose full label window fits inside the data, newest last."""
    last = (data_end - pd.Timedelta(days=horizon_days)).normalize()
    first = (data_start + pd.Timedelta(days=min_history_days)).normalize()
    dates = []
    d = last
    while d >= first:
        dates.append(d)
        d -= pd.Timedelta(days=step_days)
    return sorted(dates)


def build_training_set(orders: pd.DataFrame, dates: list[pd.Timestamp], horizon_days: int) -> pd.DataFrame:
    frames = []
    for d in dates:
        frames.append(label_snapshot(snapshot_features(orders, d), orders, d, horizon_days))
    df = pd.concat(frames)
    df.index.name = "customer_unique_id"
    return df.reset_index()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
def _preprocessor(scale: bool) -> ColumnTransformer:
    num_steps = [("impute", SimpleImputer(strategy="median", add_indicator=True))]
    if scale:
        num_steps.append(("scale", StandardScaler()))
    return ColumnTransformer([
        ("num", Pipeline(num_steps), NUMERIC_FEATURES),
        ("cat", Pipeline([
            ("impute", SimpleImputer(strategy="constant", fill_value="NA")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=0.01)),
        ]), CATEGORICAL_FEATURES),
    ])


def build_models(random_state: int = 42) -> dict[str, Pipeline]:
    # No class re-weighting: the probabilities feed CLV-at-risk and retention tiers,
    # so they must stay calibrated to the real churn rate.
    return {
        "logistic_regression": Pipeline([
            ("prep", _preprocessor(scale=True)),
            ("model", LogisticRegression(max_iter=3000, C=1.0)),
        ]),
        "random_forest": Pipeline([
            ("prep", _preprocessor(scale=False)),
            ("model", RandomForestClassifier(n_estimators=200, min_samples_leaf=50, max_features="sqrt",
                                             max_samples=0.5, n_jobs=-1, random_state=random_state)),
        ]),
        "gradient_boosting": Pipeline([
            ("prep", _preprocessor(scale=False)),
            ("model", HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_leaf_nodes=31,
                                                     min_samples_leaf=100, l2_regularization=1.0,
                                                     early_stopping=False, random_state=random_state)),
        ]),
    }


def _metrics(y_churn: np.ndarray, p_churn: np.ndarray) -> dict:
    """Metrics for the churn class plus ranking metrics for the (rare) return class."""
    y_ret, p_ret = 1 - y_churn, 1 - p_churn
    pred = (p_churn >= 0.5).astype(int)
    k = max(1, int(len(y_ret) * 0.10))
    top = np.argsort(-p_ret)[:k]
    base = y_ret.mean()
    return {
        "n": int(len(y_churn)),
        "churn_rate": float(y_churn.mean()),
        "precision": float(precision_score(y_churn, pred, zero_division=0)),
        "recall": float(recall_score(y_churn, pred, zero_division=0)),
        "f1": float(f1_score(y_churn, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_churn, p_churn)) if 0 < y_churn.mean() < 1 else float("nan"),
        "pr_auc_churn": float(average_precision_score(y_churn, p_churn)),
        "pr_auc_return": float(average_precision_score(y_ret, p_ret)) if base > 0 else float("nan"),
        "return_rate": float(base),
        "return_precision_top10pct": float(y_ret[top].mean()),
        "return_lift_top10pct": float(y_ret[top].mean() / base) if base > 0 else float("nan"),
        "brier": float(np.mean((p_churn - y_churn) ** 2)),
    }


def _sample(df: pd.DataFrame, max_rows: int | None, random_state: int) -> pd.DataFrame:
    if max_rows and len(df) > max_rows:
        return df.sample(max_rows, random_state=random_state)
    return df


def time_aware_validation(train_df: pd.DataFrame, horizon_days: int, n_folds: int = 4,
                          random_state: int = 42, max_train_rows: int | None = 400_000) -> pd.DataFrame:
    """Expanding-window evaluation on the most recent `n_folds` snapshots."""
    dates = sorted(train_df["snapshot_date"].unique())
    rows = []
    test_dates = [d for d in dates if any(
        t + pd.Timedelta(days=horizon_days) <= d for t in dates)][-n_folds:]
    for fold, test_date in enumerate(test_dates, 1):
        tr = train_df[train_df["snapshot_date"] + pd.Timedelta(days=horizon_days) <= test_date]
        te = train_df[train_df["snapshot_date"] == test_date]
        tr = _sample(tr, max_train_rows, random_state)
        if tr["churn"].nunique() < 2 or te["churn"].nunique() < 2:
            continue
        for name, model in build_models(random_state).items():
            model.fit(tr[FEATURES], tr["churn"])
            p = model.predict_proba(te[FEATURES])[:, 1]
            m = _metrics(te["churn"].to_numpy(), p)
            m.update(model=name, fold=fold, test_snapshot=str(pd.Timestamp(test_date).date()),
                     train_rows=len(tr))
            rows.append(m)
            log.info("fold %d %-20s roc_auc=%.3f pr_auc_return=%.3f", fold, name, m["roc_auc"], m["pr_auc_return"])
    return pd.DataFrame(rows)


def summarise_validation(cv: pd.DataFrame) -> pd.DataFrame:
    cols = ["roc_auc", "pr_auc_churn", "pr_auc_return", "return_lift_top10pct",
            "precision", "recall", "f1", "brier"]
    agg = cv.groupby("model")[cols].agg(["mean", "std"])
    agg.columns = [f"{a}_{b}" for a, b in agg.columns]
    return agg.sort_values("roc_auc_mean", ascending=False)


def select_best(summary: pd.DataFrame) -> str:
    """Pick the best ranker (ROC-AUC); retention targeting is a ranking problem."""
    return str(summary["roc_auc_mean"].idxmax())


def fit_final(train_df: pd.DataFrame, model_name: str, random_state: int = 42,
              max_train_rows: int | None = 600_000) -> Pipeline:
    tr = _sample(train_df, max_train_rows, random_state)
    model = build_models(random_state)[model_name]
    model.fit(tr[FEATURES], tr["churn"])
    return model


def feature_importance(model: Pipeline, X: pd.DataFrame, y: pd.Series, random_state: int = 42,
                       max_rows: int = 20_000) -> pd.DataFrame:
    """Permutation importance (drop in ROC-AUC). Predictive, not causal."""
    if len(X) > max_rows:
        idx = X.sample(max_rows, random_state=random_state).index
        X, y = X.loc[idx], y.loc[idx]
    r = permutation_importance(model, X, y, scoring="roc_auc", n_repeats=5,
                               random_state=random_state, n_jobs=-1)
    return (pd.DataFrame({"feature": X.columns, "importance_mean": r.importances_mean,
                          "importance_std": r.importances_std})
            .sort_values("importance_mean", ascending=False).reset_index(drop=True))
