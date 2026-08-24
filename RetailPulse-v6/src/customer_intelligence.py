import pandas as pd
import numpy as np

def add_rfm_segments(df: pd.DataFrame) -> pd.DataFrame:
    """Create RFM scores and interpretable customer segments."""
    out = df.copy()
    out["last_purchase"] = pd.to_datetime(out["last_purchase"])
    snapshot = out["last_purchase"].max() + pd.Timedelta(days=1)

    out["recency"] = (snapshot - out["last_purchase"]).dt.days
    out["frequency"] = out["order_count"]
    out["monetary"] = out["total_revenue"]

    # Rank first so qcut remains stable when many customers have equal values.
    out["r_score"] = 6 - pd.qcut(
        out["recency"].rank(method="first"), 5, labels=False
    )
    out["f_score"] = pd.qcut(
        out["frequency"].rank(method="first"), 5, labels=False
    ) + 1
    out["m_score"] = pd.qcut(
        out["monetary"].rank(method="first"), 5, labels=False
    ) + 1

    out["rfm_score"] = (
        out["r_score"].astype(int) +
        out["f_score"].astype(int) +
        out["m_score"].astype(int)
    )

    def segment(row):
        r, f, m = row["r_score"], row["f_score"], row["m_score"]
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"
        if r >= 4 and f >= 3:
            return "Loyal Customers"
        if r >= 4 and f <= 2:
            return "New / Promising"
        if r <= 2 and f >= 4 and m >= 4:
            return "Can't Lose Them"
        if r <= 2 and f >= 3:
            return "At Risk"
        if r <= 2 and f <= 2:
            return "Hibernating / Lost"
        return "Potential Loyalists"

    out["customer_segment"] = out.apply(segment, axis=1)
    return out
