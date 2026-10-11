"""Retention priority: combine economic value with churn risk."""
from __future__ import annotations

import numpy as np
import pandas as pd

P1 = "P1 - High Value / High Risk"
P2 = "P2 - High Value / Medium Risk"
P3 = "P3 - Low Value / High Risk"
P4 = "P4 - Protect & Grow"
P5 = "Standard Lifecycle"
PRIORITY_ORDER = [P1, P2, P3, P4, P5]

ACTIONS = {
    P1: "Personal outreach: service recovery for bad experiences + strong targeted incentive.",
    P2: "Proactive nurture: personalised recommendations and loyalty perks before they lapse.",
    P3: "Low-cost automated win-back (email/push with modest voucher).",
    P4: "Protect & upsell: cross-category recommendations, early access, no discounting.",
    P5: "Standard lifecycle marketing.",
}


def risk_tier(churn_probability: pd.Series, high: float, medium: float) -> pd.Series:
    return pd.Series(
        np.select([churn_probability >= high, churn_probability >= medium], ["High", "Medium"], "Low"),
        index=churn_probability.index,
    )


def assign_priority(df: pd.DataFrame, value_col: str, high_value_quantile: float,
                    high_risk: float, medium_risk: float) -> pd.DataFrame:
    """Value is "high" above the `high_value_quantile` of `value_col`.

    Risk thresholds apply to churn_probability. Because a marketplace like Olist has a
    very high baseline churn, thresholds are chosen relative to the score
    distribution (see pipeline) rather than fixed at 0.7 / 0.4.
    """
    out = df.copy()
    value_cut = out[value_col].quantile(high_value_quantile)
    high_value = out[value_col] >= value_cut
    tier = risk_tier(out["churn_probability"], high_risk, medium_risk)
    out["value_tier"] = np.where(high_value, "High", "Standard")
    out["risk_tier"] = tier
    out["retention_priority"] = np.select(
        [high_value & (tier == "High"), high_value & (tier == "Medium"), ~high_value & (tier == "High"),
         high_value & (tier == "Low")],
        [P1, P2, P3, P4], P5,
    )
    out["recommended_action"] = out["retention_priority"].map(ACTIONS)
    out.attrs["high_value_threshold"] = float(value_cut)
    return out
