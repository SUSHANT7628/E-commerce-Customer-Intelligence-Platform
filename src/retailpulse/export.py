"""Optional: copy the analytics tables from DuckDB into PostgreSQL.

Requires the `postgres` extra: `pip install -e ".[postgres]"`.
"""
from __future__ import annotations

import logging

from . import warehouse
from .config import Settings

log = logging.getLogger(__name__)

TABLES = ["customer_360_clv", "customer_rfm", "monthly_kpis", "category_performance",
          "product_performance", "seller_performance", "state_performance"]


def export_to_postgres(settings: Settings, url: str, schema: str = "analytics") -> None:
    try:
        from sqlalchemy import create_engine, text
    except ImportError as e:  # pragma: no cover
        raise SystemExit('Install the extra first: pip install -e ".[postgres]"') from e
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
    con = warehouse.connect(settings.warehouse_path, read_only=True)
    try:
        for t in TABLES:
            df = warehouse.query(con, f"SELECT * FROM analytics.{t}")
            df.to_sql(t, engine, schema=schema, if_exists="replace", index=False, chunksize=10_000)
            log.info("exported %s.%s (%d rows)", schema, t, len(df))
    finally:
        con.close()
