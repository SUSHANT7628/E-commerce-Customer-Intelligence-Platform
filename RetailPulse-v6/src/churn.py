import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    average_precision_score, classification_report
)

def make_churn_target(df: pd.DataFrame, inactivity_days: int = 120) -> pd.DataFrame:
    """Define churn as inactivity beyond a transparent business threshold."""
    out = df.copy()
    out["churn"] = (out["recency"] >= inactivity_days).astype(int)
    return out

def train_models(df: pd.DataFrame):
    data = df.copy()
    features = [
        "frequency", "monetary", "avg_order_value",
        "recency", "observed_months"
    ]
    features = [c for c in features if c in data.columns]
    X = data[features]
    y = data["churn"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pre = ColumnTransformer([
        ("num", Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler())
        ]), features)
    ])

    models = {
        "logistic_regression": LogisticRegression(
            max_iter=2000, class_weight="balanced"
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300, random_state=42, class_weight="balanced",
            n_jobs=-1, min_samples_leaf=5
        )
    }

    results = {}
    for name, model in models.items():
        pipe = Pipeline([("preprocess", pre), ("model", model)])
        pipe.fit(X_train, y_train)
        prob = pipe.predict_proba(X_test)[:, 1]
        pred = (prob >= 0.5).astype(int)

        results[name] = {
            "model": pipe,
            "precision": precision_score(y_test, pred, zero_division=0),
            "recall": recall_score(y_test, pred, zero_division=0),
            "f1": f1_score(y_test, pred, zero_division=0),
            "roc_auc": roc_auc_score(y_test, prob),
            "pr_auc": average_precision_score(y_test, prob),
            "report": classification_report(y_test, pred, zero_division=0)
        }

    return results
