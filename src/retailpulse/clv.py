"""Customer Lifetime Value.

Two models are provided and backtested against each other:

* **BG/NBD + Gamma-Gamma** (Fader, Hardie & Lee 2005; Fader & Hardie 2013) — the
  standard probabilistic "buy-till-you-die" model. BG/NBD predicts how many orders a
  customer will place in the horizon (and whether they are still "alive");
  Gamma-Gamma predicts the value of those orders with shrinkage toward the
  population mean. Implemented directly with numpy/scipy (no unmaintained deps).
* **Heuristic proxy** (the project's original formula) — monthly revenue run-rate x
  horizon x exp(-recency/365). Kept as a transparent baseline.

`backtest_clv` fits both on a calibration window and scores them on a holdout
window, so the choice of model is evidence-based.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln, hyp2f1


# ---------------------------------------------------------------------------
# RFM summary in BG/NBD form
# ---------------------------------------------------------------------------
def rfm_summary(orders: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Per-customer (x, t_x, T, monetary) using orders strictly before `cutoff`.

    Purchases are counted per *day* (several orders on one day = one purchase
    occasion), as is standard for BG/NBD; otherwise same-day split orders look like
    an extremely high purchase rate. Time is measured in weeks.

    x   = number of repeat purchase days
    t_x = weeks between first and last purchase day
    T   = weeks between first purchase and cutoff
    """
    hist = orders.loc[orders["purchase_ts"] < cutoff]
    day = hist["purchase_ts"].dt.normalize()
    g = hist.assign(day=day).groupby("customer_unique_id")
    out = pd.DataFrame({
        "first": g["day"].min(),
        "last": g["day"].max(),
        "purchase_days": g["day"].nunique(),
        "n_orders": g.size(),
        "revenue": g["order_revenue"].sum(),
    })
    week = pd.Timedelta(days=7)
    out["x"] = out["purchase_days"] - 1
    out["t_x"] = (out["last"] - out["first"]) / week
    out["T"] = (cutoff.normalize() - out["first"]) / week
    out["aov"] = out["revenue"] / out["n_orders"]
    out["value_per_purchase"] = out["revenue"] / out["purchase_days"]
    out["recency_days"] = (cutoff - g["purchase_ts"].max()) / pd.Timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# BG/NBD
# ---------------------------------------------------------------------------
@dataclass
class BetaGeoFitter:
    r: float = np.nan
    alpha: float = np.nan
    a: float = np.nan
    b: float = np.nan

    @staticmethod
    def _negll(log_params, x, tx, T, w):
        r, alpha, a, b = np.exp(log_params)
        a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
        a2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
        a3 = -(r + x) * np.log(alpha + T)
        with np.errstate(divide="ignore", invalid="ignore"):
            a4 = np.where(
                x > 0,
                np.log(a) - np.log(np.maximum(b + x - 1, 1e-12)) - (r + x) * np.log(alpha + tx),
                -np.inf,
            )
        ll = a1 + a2 + np.logaddexp(a3, a4)
        return -(w * ll).sum() / w.sum()

    def fit(self, x, tx, T) -> BetaGeoFitter:
        # Collapse identical (x, t_x, T) rows to speed up the likelihood.
        df = pd.DataFrame({"x": x, "tx": np.round(tx, 3), "T": np.round(T, 3)})
        agg = df.value_counts().reset_index(name="w")
        args = (agg["x"].to_numpy(float), agg["tx"].to_numpy(float),
                agg["T"].to_numpy(float), agg["w"].to_numpy(float))
        best = None
        for init in ([0.0, 0.0, 0.0, 0.0], [np.log(0.1), np.log(10.0), 0.0, np.log(3.0)]):
            res = minimize(self._negll, init, args=args, method="L-BFGS-B", bounds=[(-12.0, 10.0)] * 4)
            if best is None or res.fun < best.fun:
                best = res
        self.r, self.alpha, self.a, self.b = np.exp(best.x)
        return self

    def p_alive(self, x, tx, T):
        x, tx, T = map(np.asarray, (x, tx, T))
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        with np.errstate(divide="ignore", invalid="ignore"):
            term = (a / np.maximum(b + x - 1, 1e-12)) * ((alpha + T) / (alpha + tx)) ** (r + x)
        return np.where(x > 0, 1.0 / (1.0 + term), 1.0)

    def expected_purchases(self, t, x, tx, T):
        """E[# purchases in (T, T+t]] given history (Fader et al. 2005, eq. 10); t in weeks."""
        x, tx, T = map(np.asarray, (x, tx, T))
        r, alpha, a, b = self.r, self.alpha, self.a, self.b
        hyp = hyp2f1(r + x, b + x, a + b + x - 1, t / (alpha + T + t))
        num = (a + b + x - 1) / (a - 1) * (1 - ((alpha + T) / (alpha + T + t)) ** (r + x) * hyp)
        with np.errstate(divide="ignore", invalid="ignore"):
            den = 1 + np.where(x > 0, a / np.maximum(b + x - 1, 1e-12)
                               * ((alpha + T) / (alpha + tx)) ** (r + x), 0.0)
        return np.clip(np.nan_to_num(num / den), 0, None)


# ---------------------------------------------------------------------------
# Gamma-Gamma
# ---------------------------------------------------------------------------
@dataclass
class GammaGammaFitter:
    p: float = np.nan
    q: float = np.nan
    v: float = np.nan

    @staticmethod
    def _negll(log_params, n, m):
        p, q, v = np.exp(log_params)
        ll = (gammaln(p * n + q) - gammaln(p * n) - gammaln(q) + q * np.log(v)
              + (p * n - 1) * np.log(m) + (p * n) * np.log(n) - (p * n + q) * np.log(n * m + v))
        return -ll.mean()

    def fit(self, n_orders, avg_value) -> GammaGammaFitter:
        n = np.asarray(n_orders, float)
        m = np.asarray(avg_value, float)
        keep = (n > 0) & (m > 0)
        res = minimize(self._negll, [np.log(5.0), np.log(5.0), np.log(100.0)],
                       args=(n[keep], m[keep]), method="L-BFGS-B", bounds=[(-8.0, 12.0)] * 3)
        self.p, self.q, self.v = np.exp(res.x)
        return self

    def expected_value(self, n_orders, avg_value):
        n = np.asarray(n_orders, float)
        m = np.asarray(avg_value, float)
        return (self.v + n * m) * self.p / (self.p * n + self.q - 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def heuristic_clv(summary: pd.DataFrame, horizon_days: int) -> pd.Series:
    """Original project proxy: monthly run-rate x horizon x recency decay."""
    observed_months = np.maximum(summary["t_x"] * 7 / 30.44, 1)
    monthly_revenue = summary["revenue"] / observed_months
    return monthly_revenue * (horizon_days / 30.44) * np.exp(-summary["recency_days"] / 365)


def fit_probabilistic(summary: pd.DataFrame) -> tuple[BetaGeoFitter, GammaGammaFitter]:
    bg = BetaGeoFitter().fit(summary["x"], summary["t_x"], summary["T"])
    gg = GammaGammaFitter().fit(summary["purchase_days"], summary["value_per_purchase"])
    return bg, gg


def predict_clv(summary: pd.DataFrame, bg: BetaGeoFitter, gg: GammaGammaFitter,
                horizon_days: int) -> pd.DataFrame:
    out = pd.DataFrame(index=summary.index)
    out["p_alive"] = bg.p_alive(summary["x"], summary["t_x"], summary["T"])
    out["expected_orders"] = bg.expected_purchases(horizon_days / 7, summary["x"], summary["t_x"], summary["T"])
    out["expected_order_value"] = gg.expected_value(summary["purchase_days"], summary["value_per_purchase"])
    out["predicted_clv"] = out["expected_orders"] * out["expected_order_value"]
    out["heuristic_clv"] = heuristic_clv(summary, horizon_days)
    return out


def _evaluate(pred: pd.Series, actual: pd.Series) -> dict:
    top = pred.rank(ascending=False, method="first") <= max(1, int(len(pred) * 0.10))
    total_actual = actual.sum()
    return {
        "predicted_total": float(pred.sum()),
        "actual_total": float(total_actual),
        "total_error_pct": float(pred.sum() / total_actual - 1) if total_actual else None,
        "mae": float((pred - actual).abs().mean()),
        "spearman": float(pred.corr(actual, method="spearman")),
        "top_decile_revenue_capture": float(actual[top].sum() / total_actual) if total_actual else None,
    }


def backtest_clv(orders: pd.DataFrame, data_end: pd.Timestamp, holdout_days: int) -> dict:
    """Fit on [start, data_end - holdout) and score revenue in the holdout window."""
    calib_end = data_end - pd.Timedelta(days=holdout_days)
    summary = rfm_summary(orders, calib_end)
    bg, gg = fit_probabilistic(summary)
    pred = predict_clv(summary, bg, gg, holdout_days)
    hold = orders.loc[(orders["purchase_ts"] >= calib_end) & (orders["purchase_ts"] < data_end)]
    actual = hold.groupby("customer_unique_id")["order_revenue"].sum().reindex(summary.index, fill_value=0.0)
    return {
        "calibration_end": str(calib_end.date()),
        "holdout_days": holdout_days,
        "customers": int(len(summary)),
        "customers_returning_in_holdout": int((actual > 0).sum()),
        "bgnbd_gamma_gamma": _evaluate(pred["predicted_clv"], actual),
        "heuristic_proxy": _evaluate(pred["heuristic_clv"], actual),
        "params": {"bgnbd": vars(bg), "gamma_gamma": vars(gg)},
    }
