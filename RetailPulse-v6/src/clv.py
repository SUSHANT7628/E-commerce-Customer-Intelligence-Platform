import pandas as pd
import numpy as np

def estimate_clv(customer_df: pd.DataFrame, horizon_months: int = 12) -> pd.DataFrame:
    """
    Simple, transparent historical CLV proxy.
    CLV = expected monthly revenue * expected active months.
    For this project, active months are estimated from observed customer tenure
    and capped by the selected forecast horizon.
    """
    df = customer_df.copy()
    df["first_purchase"] = pd.to_datetime(df["first_purchase"])
    df["last_purchase"] = pd.to_datetime(df["last_purchase"])

    tenure_days = (df["last_purchase"] - df["first_purchase"]).dt.days.clip(lower=1)
    df["observed_months"] = np.maximum(tenure_days / 30.44, 1)
    df["monthly_revenue"] = df["total_revenue"] / df["observed_months"]

    # Conservative forecast: recent monthly run-rate × forecast horizon,
    # discounted by a simple recency factor.
    recency = df["recency"].clip(lower=0)
    recency_factor = np.exp(-recency / 365)

    df["predicted_12m_clv"] = (
        df["monthly_revenue"] * horizon_months * recency_factor
    )

    return df
