import numpy as np
import pandas as pd
import pytest

from retailpulse import churn, clv, priority


def _orders(rows):
    df = pd.DataFrame(rows, columns=["customer_unique_id", "purchase_ts", "order_revenue"])
    df["purchase_ts"] = pd.to_datetime(df["purchase_ts"])
    df["customer_state"] = "SP"
    df["n_items"] = 1
    df["installments"] = 1
    df["payment_type"] = "credit_card"
    df["review_score"] = 5.0
    df["delivery_days"] = 10.0
    df["is_late"] = 0
    return df


ORDERS = _orders([
    ("a", "2018-01-01", 100.0),
    ("a", "2018-03-01", 50.0),
    ("a", "2018-06-15", 80.0),   # after cutoff: must not leak into features
    ("b", "2018-02-01", 200.0),
    ("c", "2018-07-01", 30.0),   # first order after cutoff: not in snapshot
])
CUTOFF = pd.Timestamp("2018-04-01")


def test_snapshot_features_use_only_past_orders():
    f = churn.snapshot_features(ORDERS, CUTOFF)
    assert set(f.index) == {"a", "b"}
    assert f.loc["a", "frequency"] == 2
    assert f.loc["a", "monetary"] == 150.0
    assert f.loc["a", "recency_days"] == 31
    assert f.loc["a", "avg_days_between_orders"] == 59
    assert np.isnan(f.loc["b", "avg_days_between_orders"])


def test_labels_look_forward_only():
    f = churn.snapshot_features(ORDERS, CUTOFF)
    lab = churn.label_snapshot(f, ORDERS, CUTOFF, horizon_days=120)
    assert lab.loc["a", "churn"] == 0   # ordered on 2018-06-15, inside the window
    assert lab.loc["b", "churn"] == 1
    lab_short = churn.label_snapshot(f, ORDERS, CUTOFF, horizon_days=30)
    assert lab_short.loc["a", "churn"] == 1


def test_snapshot_dates_leave_room_for_label_window():
    dates = churn.snapshot_dates(pd.Timestamp("2017-01-01"), pd.Timestamp("2018-09-01"), 120, 30, 180)
    assert dates == sorted(dates)
    assert dates[-1] + pd.Timedelta(days=120) <= pd.Timestamp("2018-09-01")
    assert dates[0] >= pd.Timestamp("2017-06-30")


def test_recency_is_not_the_label():
    """Regression test for the original leakage: label must not be a function of recency alone."""
    f = churn.snapshot_features(ORDERS, CUTOFF)
    lab = churn.label_snapshot(f, ORDERS, CUTOFF, horizon_days=120)
    # a is more recent than b and did return; with the same recency it could still churn.
    assert lab.loc["a", "recency_days"] < lab.loc["b", "recency_days"]
    assert "churn" not in churn.FEATURES


def test_bgnbd_recovers_simulated_parameters():
    rng = np.random.default_rng(0)
    n, T = 6000, 52.0
    r, alpha, a, b = 0.25, 4.0, 0.8, 2.5
    lam = rng.gamma(r, 1 / alpha, n)
    p = rng.beta(a, b, n)
    xs, txs = [], []
    for i in range(n):
        t, x, tx = 0.0, 0, 0.0
        while True:
            t += rng.exponential(1 / lam[i])
            if t > T:
                break
            x += 1
            tx = t
            if rng.random() < p[i]:
                break
        xs.append(x)
        txs.append(tx)
    bg = clv.BetaGeoFitter().fit(np.array(xs), np.array(txs), np.full(n, T))
    assert bg.r == pytest.approx(r, rel=0.35)
    assert bg.alpha == pytest.approx(alpha, rel=0.5)
    e = bg.expected_purchases(26, np.array(xs), np.array(txs), np.full(n, T))
    assert (e >= 0).all()
    pa = bg.p_alive(np.array(xs), np.array(txs), np.full(n, T))
    assert ((pa >= 0) & (pa <= 1)).all()


def test_gamma_gamma_shrinks_toward_population_mean():
    rng = np.random.default_rng(1)
    n = rng.integers(1, 6, 3000)
    m = rng.gamma(5, 30, 3000)
    gg = clv.GammaGammaFitter().fit(n, m)
    pop = gg.v * gg.p / (gg.q - 1)
    low = gg.expected_value(np.array([1]), np.array([10.0]))[0]
    assert 10.0 < low < pop


def test_rfm_summary_counts_purchase_days():
    o = _orders([("a", "2018-01-01 10:00", 10), ("a", "2018-01-01 12:00", 10), ("a", "2018-01-08 00:00", 10)])
    s = clv.rfm_summary(o, pd.Timestamp("2018-01-15"))
    assert s.loc["a", "x"] == 1
    assert s.loc["a", "n_orders"] == 3
    assert s.loc["a", "t_x"] == pytest.approx(1.0)
    assert s.loc["a", "T"] == pytest.approx(2.0)


def test_priority_assignment():
    df = pd.DataFrame({"v": [100, 90, 1, 2], "churn_probability": [0.9, 0.5, 0.95, 0.1]})
    out = priority.assign_priority(df, "v", 0.5, high_risk=0.8, medium_risk=0.4)
    assert out["retention_priority"].tolist() == [priority.P1, priority.P2, priority.P3, priority.P5]
    assert out["recommended_action"].notna().all()
