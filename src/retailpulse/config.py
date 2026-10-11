"""Central configuration: paths and modelling assumptions.

Every business assumption lives here so it is documented in one place and can be
overridden from the CLI or environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"

# The ten Olist tables expected in the raw-data folder (file stem -> raw table name).
OLIST_FILES: dict[str, str] = {
    "olist_customers_dataset": "customers",
    "olist_orders_dataset": "orders",
    "olist_order_items_dataset": "order_items",
    "olist_order_payments_dataset": "order_payments",
    "olist_order_reviews_dataset": "order_reviews",
    "olist_products_dataset": "products",
    "olist_sellers_dataset": "sellers",
    "product_category_name_translation": "category_translation",
}


@dataclass
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("RETAILPULSE_DATA_DIR", PROJECT_ROOT / "data" / "raw"))
    )
    artifacts_dir: Path = field(
        default_factory=lambda: Path(os.getenv("RETAILPULSE_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts"))
    )

    # --- Churn definition -------------------------------------------------
    # A customer "churns" at a snapshot date if they place no order in the
    # following `churn_horizon_days`. Features only use history before the snapshot.
    churn_horizon_days: int = 120
    # Spacing between historical training snapshots.
    snapshot_step_days: int = 30
    # Minimum history before the first snapshot (lets features stabilise).
    min_history_days: int = 180

    # --- CLV ---------------------------------------------------------------
    clv_horizon_days: int = 365
    # Holdout length used to backtest the CLV models.
    clv_holdout_days: int = 180

    # --- Retention priority -----------------------------------------------
    high_value_quantile: float = 0.75
    # Risk tiers are quantiles of churn_probability (top 25% = High, next 25% =
    # Medium). Absolute cut-offs such as 0.7/0.4 are meaningless when ~95%+ of a
    # marketplace's customers never return.
    risk_high_quantile: float = 0.75
    risk_medium_quantile: float = 0.50

    random_state: int = 42

    @property
    def warehouse_path(self) -> Path:
        return self.artifacts_dir / "warehouse.duckdb"

    @property
    def model_path(self) -> Path:
        return self.artifacts_dir / "models" / "churn_model.joblib"

    @property
    def exports_dir(self) -> Path:
        return self.artifacts_dir / "exports"

    @property
    def metrics_path(self) -> Path:
        return self.artifacts_dir / "metrics.json"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.artifacts_dir, self.model_path.parent, self.exports_dir):
            p.mkdir(parents=True, exist_ok=True)
