"""PostgreSQL warehouse: same tables as the DuckDB build, and the seven RFM segments.

The PostgreSQL test needs a server:
    RETAILPULSE_TEST_PG_URL=postgresql+psycopg://postgres:postgres@localhost:5432/retailpulse pytest
"""
import os

import pytest

from retailpulse import warehouse

SEGMENTS = {"Champions", "Loyal Customers", "New / Promising", "Potential Loyalists",
            "Needs Attention", "At Risk", "Hibernating / Lost"}

PG_URL = os.getenv("RETAILPULSE_TEST_PG_URL")


def test_rfm_has_seven_named_segments(run_result):
    s, _ = run_result
    con = warehouse.connect(s.warehouse_path, read_only=True)
    try:
        found = set(warehouse.query(con, "SELECT DISTINCT customer_segment FROM analytics.customer_rfm")
                    ["customer_segment"])
    finally:
        con.close()
    assert found <= SEGMENTS


@pytest.mark.skipif(not PG_URL, reason="set RETAILPULSE_TEST_PG_URL to run the PostgreSQL build")
def test_postgres_build_matches_duckdb(run_result):
    from retailpulse.postgres import build_all

    s, _ = run_result
    r = build_all(s, PG_URL)
    bad = [t for t in r["parity"]["tables"] if not t["match"]]
    assert not bad, bad
    assert r["parity"]["segment_agreement"] == 1.0
    assert r["customer_360_clv_rows"] == r["parity"]["customers_compared"]
