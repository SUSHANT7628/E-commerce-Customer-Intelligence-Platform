"""PostgreSQL warehouse: load the raw Olist CSVs, run the PostgreSQL SQL layer
(sql/postgres/), load the model scores, and check parity with the DuckDB build.

    retailpulse run                                    # models + DuckDB warehouse
    retailpulse postgres-build --url postgresql+psycopg://user:pass@host:5432/retailpulse

Requires the `postgres` extra: `pip install -e ".[postgres]"`.
"""
from __future__ import annotations

import csv
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import warehouse
from .config import OLIST_FILES, SQL_DIR, Settings

log = logging.getLogger(__name__)

PG_SQL_DIR = SQL_DIR / "postgres"
TRANSFORMATIONS = ["01_staging.sql", "02_customer_360.sql", "03_rfm_segments.sql", "04_business_marts.sql"]

# (table, numeric columns whose sums must match between DuckDB and PostgreSQL)
PARITY_TABLES = [
    ("staging.order_items", ["item_revenue", "price", "freight_value"]),
    ("staging.orders", ["order_revenue", "n_items", "review_score", "delivery_days", "is_late", "installments"]),
    ("analytics.customer_360", ["total_revenue", "order_count", "recency", "tenure_days", "avg_review_score",
                                "late_delivery_rate", "is_repeat_customer"]),
    ("analytics.customer_rfm", ["r_score", "f_score", "m_score", "rfm_score"]),
    ("analytics.monthly_kpis", ["revenue", "orders", "customers", "new_customers"]),
    ("analytics.category_performance", ["revenue", "orders", "items_sold"]),
    ("analytics.seller_performance", ["revenue", "orders", "avg_delivery_days"]),
    ("analytics.state_performance", ["revenue", "orders", "customers"]),
]


def engine_for(url: str):
    try:
        from sqlalchemy import create_engine
    except ImportError as e:  # pragma: no cover
        raise SystemExit('Install the extra first: pip install -e ".[postgres]"') from e
    return create_engine(url)


def _exec_script(engine, sql: str) -> None:
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute(sql)          # no parameters -> multiple statements allowed
        raw.commit()
    finally:
        raw.close()


def load_raw(engine, data_dir: Path) -> dict[str, int]:
    """Create raw.* as TEXT columns and bulk-load each CSV with COPY."""
    _exec_script(engine, "CREATE SCHEMA IF NOT EXISTS raw;")
    counts = {}
    raw = engine.raw_connection()
    try:
        for stem, table in OLIST_FILES.items():
            path = data_dir / f"{stem}.csv"
            if not path.exists():
                raise FileNotFoundError(f"Missing {path}. Run `retailpulse download` first.")
            with open(path, newline="", encoding="utf-8-sig") as fh:   # strips a BOM if present
                header = next(csv.reader(fh))
            cols = ", ".join(f'"{c}" TEXT' for c in header)
            with raw.cursor() as cur:
                cur.execute(f"DROP TABLE IF EXISTS raw.{table} CASCADE; CREATE TABLE raw.{table} ({cols});")
                with open(path, "rb") as fh, cur.copy(
                        f"COPY raw.{table} FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
                    while chunk := fh.read(1 << 20):
                        cp.write(chunk)
                cur.execute(f"SELECT COUNT(*) FROM raw.{table}")
                counts[table] = cur.fetchone()[0]
            raw.commit()
            log.info("raw.%-22s %8d rows", table, counts[table])
    finally:
        raw.close()
    return counts


def build(engine) -> None:
    for name in TRANSFORMATIONS:
        log.info("postgres: running %s", name)
        _exec_script(engine, (PG_SQL_DIR / name).read_text())


def load_scores(engine, settings: Settings, schema: str = "analytics") -> int:
    """Copy the model output table (CLV, churn, priority per customer) from the DuckDB run."""
    con = warehouse.connect(settings.warehouse_path, read_only=True)
    try:
        df = warehouse.query(con, "SELECT * FROM analytics.customer_360_clv")
    finally:
        con.close()
    _exec_script(engine, f"DROP TABLE IF EXISTS {schema}.customer_360_clv CASCADE;")
    df.to_sql("customer_360_clv", engine, schema=schema, if_exists="replace", index=False, chunksize=10_000)
    _exec_script(engine, f"CREATE UNIQUE INDEX ON {schema}.customer_360_clv (customer_unique_id);")
    return len(df)


def parity(engine, settings: Settings, rtol: float = 1e-9) -> dict:
    """Compare every SQL-built table between the DuckDB warehouse and PostgreSQL."""
    con = warehouse.connect(settings.warehouse_path, read_only=True)
    rows = []
    try:
        for table, cols in PARITY_TABLES:
            sums = ", ".join(f"SUM(CAST({c} AS DOUBLE PRECISION)) AS {c}" for c in cols)
            q = f"SELECT COUNT(*) AS n, {sums} FROM {table}"
            d = warehouse.query(con, q.replace("DOUBLE PRECISION", "DOUBLE")).iloc[0]
            p = pd.read_sql(q, engine).iloc[0]
            worst = max(abs(float(d[c]) - float(p[c])) / max(abs(float(d[c])), 1e-12) for c in cols)
            rows.append({"table": table, "rows_duckdb": int(d["n"]), "rows_postgres": int(p["n"]),
                         "max_rel_diff_in_column_sums": worst,
                         "match": int(d["n"]) == int(p["n"]) and worst <= rtol})
        seg_d = warehouse.query(con, "SELECT customer_unique_id, customer_segment FROM analytics.customer_rfm")
    finally:
        con.close()
    seg_p = pd.read_sql("SELECT customer_unique_id, customer_segment FROM analytics.customer_rfm", engine)
    m = seg_d.merge(seg_p, on="customer_unique_id", suffixes=("_duckdb", "_postgres"))
    same = (m["customer_segment_duckdb"] == m["customer_segment_postgres"]).mean()
    counts = seg_p["customer_segment"].value_counts().rename_axis("segment").reset_index(name="customers")
    return {"tables": rows, "customers_compared": int(len(m)), "segment_agreement": float(same),
            "segments_postgres": counts.to_dict(orient="records")}


def build_all(settings: Settings, url: str, check_parity: bool = True) -> dict:
    t0 = time.time()
    engine = engine_for(url)
    counts = load_raw(engine, settings.data_dir)
    build(engine)
    n_scores = load_scores(engine, settings) if settings.warehouse_path.exists() else 0
    result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "server_version": pd.read_sql("SHOW server_version", engine).iloc[0, 0],
              "raw_rows": counts, "customer_360_clv_rows": n_scores}
    if check_parity and settings.warehouse_path.exists():
        result["parity"] = parity(engine, settings)
    result["elapsed_s"] = round(time.time() - t0, 1)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (settings.artifacts_dir / "postgres_build.json").write_text(json.dumps(result, indent=2, default=str))
    (settings.artifacts_dir / "POSTGRES.md").write_text(render_markdown(result))
    return result


def render_markdown(r: dict) -> str:
    lines = [
        "# RetailPulse — PostgreSQL warehouse build",
        "",
        f"_Generated by `retailpulse postgres-build` on {r['generated_at']} against PostgreSQL "
        f"{r['server_version']} ({r['elapsed_s']} s)._",
        "",
        "The SQL layer in `sql/postgres/` (staging → Customer 360 → RFM segments → business marts) was run",
        "on PostgreSQL and compared table by table with the DuckDB build of `sql/` from the same raw files.",
        "",
        "| Table | Rows (PostgreSQL) | Rows (DuckDB) | Max relative difference in column sums | Match |",
        "|---|---|---|---|---|",
    ]
    for t in r.get("parity", {}).get("tables", []):
        lines.append(f"| `{t['table']}` | {t['rows_postgres']:,} | {t['rows_duckdb']:,} | "
                     f"{t['max_rel_diff_in_column_sums']:.1e} | {'✅' if t['match'] else '❌'} |")
    p = r.get("parity")
    if p:
        lines += ["", f"Per-customer RFM segment agreement: **{p['segment_agreement']:.4%}** of "
                      f"{p['customers_compared']:,} customers.", "",
                  "| Segment | Customers |", "|---|---|"]
        lines += [f"| {s['segment']} | {s['customers']:,} |" for s in p["segments_postgres"]]
    lines += ["", f"`analytics.customer_360_clv` (model scores) loaded: {r['customer_360_clv_rows']:,} rows.", ""]
    return "\n".join(lines)
