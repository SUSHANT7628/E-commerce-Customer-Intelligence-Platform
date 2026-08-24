import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    average_precision_score
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer

FEATURES = ["frequency", "monetary", "avg_order_value", "recency", "observed_months"]

def build_models():
    prep = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler())
    ])
    return {
        "Logistic Regression": Pipeline([
            ("prep", prep),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced"))
        ]),
        "Random Forest": Pipeline([
            ("prep", prep),
            ("model", RandomForestClassifier(
                n_estimators=300, random_state=42,
                class_weight="balanced", min_samples_leaf=5, n_jobs=-1
            ))
        ]),
        "Gradient Boosting": Pipeline([
            ("prep", prep),
            ("model", GradientBoostingClassifier(random_state=42))
        ])
    }

def time_aware_evaluate(df, n_splits=5):
    """
    Time-aware expanding-window validation.
    The dataset must contain an 'as_of_date' column and binary 'churn'.
    """
    data = df.dropna(subset=["as_of_date"]).sort_values("as_of_date").copy()
    X, y = data[FEATURES], data["churn"]

    splitter = TimeSeriesSplit(n_splits=n_splits)
    rows = []

    for name, model in build_models().items():
        fold_scores = []
        for fold, (train_idx, test_idx) in enumerate(splitter.split(X), 1):
            model.fit(X.iloc[train_idx], y.iloc[train_idx])
            prob = model.predict_proba(X.iloc[test_idx])[:, 1]
            pred = (prob >= 0.5).astype(int)

            fold_scores.append({
                "model": name,
                "fold": fold,
                "precision": precision_score(y.iloc[test_idx], pred, zero_division=0),
                "recall": recall_score(y.iloc[test_idx], pred, zero_division=0),
                "f1": f1_score(y.iloc[test_idx], pred, zero_division=0),
                "roc_auc": roc_auc_score(y.iloc[test_idx], prob),
                "pr_auc": average_precision_score(y.iloc[test_idx], prob)
            })
        rows.extend(fold_scores)

    return pd.DataFrame(rows)
