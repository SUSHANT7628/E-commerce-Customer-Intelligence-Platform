"""DuckDB warehouse: load raw CSVs and run the SQL transformation layer."""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import pandas as pd

from .config import OLIST_FILES, SQL_DIR

log = logging.getLogger(__name__)

TRANSFORMATIONS = [
    "01_staging.sql",
    "02_customer_360.sql",
    "03_rfm_segments.sql",
    "04_business_marts.sql",
]


def connect(path: Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def load_raw(con: duckdb.DuckDBPyConnection, data_dir: Path) -> dict[str, int]:
    """Load every Olist CSV into the `raw` schema; returns row counts."""
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    counts = {}
    for stem, table in OLIST_FILES.items():
        path = data_dir / f"{stem}.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Run `retailpulse download` (real Olist data) "
                f"or `retailpulse generate` (synthetic data) first."
            )
        # all_varchar keeps ids like zip prefixes intact; SQL casts what it needs.
        con.execute(
            f"CREATE OR REPLACE TABLE raw.{table} AS "
            f"SELECT * FROM read_csv(?, header=true, all_varchar=true)",
            [str(path)],
        )
        counts[table] = con.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
        log.info("raw.%-22s %8d rows", table, counts[table])
    return counts


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    log.info("running %s", path.name)
    con.execute(path.read_text())


def build(con: duckdb.DuckDBPyConnection) -> None:
    for name in TRANSFORMATIONS:
        run_sql_file(con, SQL_DIR / name)


def query(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> pd.DataFrame:
    return con.execute(sql, params or []).df()


def write_table(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, table: str) -> None:
    con.register("_tmp_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _tmp_df")
    con.unregister("_tmp_df")
