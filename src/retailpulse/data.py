"""Data acquisition: download the public Olist dataset or generate a synthetic one.

The Brazilian E-Commerce Public Dataset by Olist is published under CC BY-NC-SA 4.0
(https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce). Olist also mirrors the
CSV files in https://github.com/olist/work-at-olist-data, which is what `download`
uses so no Kaggle credentials are needed. Raw data is never committed to git.

`generate_synthetic` writes CSVs with exactly the same schema, driven by a simple
buy-till-you-die process, so the full pipeline (and the test-suite) can run offline.
"""
from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from .config import OLIST_FILES

log = logging.getLogger(__name__)

OLIST_BASE_URL = "https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets/"


def download_olist(data_dir: Path, overwrite: bool = False) -> list[Path]:
    """Download the Olist CSV files into `data_dir`; returns the file paths."""
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for stem in OLIST_FILES:
        target = data_dir / f"{stem}.csv"
        paths.append(target)
        if target.exists() and not overwrite:
            log.info("exists, skipping: %s", target.name)
            continue
        url = OLIST_BASE_URL + target.name
        log.info("downloading %s", url)
        tmp = target.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed https URL
        tmp.replace(target)
    return paths


def raw_files_present(data_dir: Path) -> bool:
    return all((data_dir / f"{stem}.csv").exists() for stem in OLIST_FILES)


# ---------------------------------------------------------------------------
# Synthetic data
# ---------------------------------------------------------------------------
_STATES = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "DF", "GO", "ES", "PE", "CE"]
_STATE_P = np.array([0.42, 0.13, 0.12, 0.055, 0.05, 0.037, 0.034, 0.022, 0.02, 0.02, 0.017, 0.015])
_CATEGORIES = {
    "cama_mesa_banho": "bed_bath_table",
    "beleza_saude": "health_beauty",
    "esporte_lazer": "sports_leisure",
    "moveis_decoracao": "furniture_decor",
    "informatica_acessorios": "computers_accessories",
    "utilidades_domesticas": "housewares",
    "relogios_presentes": "watches_gifts",
    "telefonia": "telephony",
    "ferramentas_jardim": "garden_tools",
    "automotivo": "auto",
    "brinquedos": "toys",
    "cool_stuff": "cool_stuff",
    "perfumaria": "perfumery",
    "bebes": "baby",
    "eletronicos": "electronics",
}
_CAT_PRICE = {  # median-ish price per category (BRL)
    "cama_mesa_banho": 80, "beleza_saude": 110, "esporte_lazer": 95, "moveis_decoracao": 85,
    "informatica_acessorios": 120, "utilidades_domesticas": 70, "relogios_presentes": 190,
    "telefonia": 60, "ferramentas_jardim": 100, "automotivo": 110, "brinquedos": 90,
    "cool_stuff": 140, "perfumaria": 90, "bebes": 115, "eletronicos": 75,
}


def generate_synthetic(
    data_dir: Path,
    n_customers: int = 8000,
    start: str = "2016-10-01",
    end: str = "2018-08-31",
    seed: int = 42,
) -> list[Path]:
    """Write an Olist-shaped synthetic dataset to `data_dir`.

    Each customer has a latent purchase rate and dropout probability (BG/NBD style).
    Bad experiences (late delivery, low review) raise the dropout probability, so the
    churn model has genuine, learnable signal.
    """
    rng = np.random.default_rng(seed)
    data_dir.mkdir(parents=True, exist_ok=True)
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    span_days = (t1 - t0).days

    cats = list(_CATEGORIES)
    n_products, n_sellers = 1500, 300
    products = pd.DataFrame({
        "product_id": [f"p{i:06d}" for i in range(n_products)],
        "product_category_name": rng.choice(cats, n_products),
        "product_name_lenght": rng.integers(20, 64, n_products),
        "product_description_lenght": rng.integers(100, 2000, n_products),
        "product_photos_qty": rng.integers(1, 6, n_products),
        "product_weight_g": rng.integers(100, 10000, n_products),
        "product_length_cm": rng.integers(10, 80, n_products),
        "product_height_cm": rng.integers(2, 50, n_products),
        "product_width_cm": rng.integers(10, 60, n_products),
    })
    base_price = products["product_category_name"].map(_CAT_PRICE).to_numpy()
    product_price = np.round(base_price * rng.lognormal(0, 0.55, n_products), 2)
    product_pop = rng.pareto(1.2, n_products) + 1
    product_pop /= product_pop.sum()

    sellers = pd.DataFrame({
        "seller_id": [f"s{i:05d}" for i in range(n_sellers)],
        "seller_zip_code_prefix": rng.integers(1000, 99999, n_sellers),
        "seller_city": "cidade",
        "seller_state": rng.choice(_STATES, n_sellers, p=_STATE_P / _STATE_P.sum()),
    })
    seller_quality = rng.beta(8, 2, n_sellers)  # higher = fewer late deliveries
    product_seller = rng.integers(0, n_sellers, n_products)

    # Customers arrive over time (growing marketplace).
    arrival = t0 + pd.to_timedelta(np.sort(span_days * rng.power(1.6, n_customers)).astype(int), unit="D")
    lam = rng.gamma(0.35, 1 / 4.0, n_customers) / 30.0  # purchases per day while alive
    p_drop = rng.beta(1.2, 2.0, n_customers)
    states = rng.choice(_STATES, n_customers, p=_STATE_P / _STATE_P.sum())

    customers, orders, items, payments, reviews = [], [], [], [], []
    oid = 0
    for c in range(n_customers):
        unique_id = f"u{c:07d}"
        t = arrival[c]
        alive = True
        while alive and t <= t1:
            oid += 1
            order_id, cust_id = f"o{oid:08d}", f"c{oid:08d}"  # Olist issues a customer_id per order
            customers.append((cust_id, unique_id, rng.integers(1000, 99999), "cidade", states[c]))

            n_items = 1 + rng.poisson(0.15)
            pidx = rng.choice(n_products, n_items, p=product_pop)
            sidx = product_seller[pidx[0]]
            est_days = int(rng.integers(12, 35))
            late_p = 1 - seller_quality[sidx]
            delay = est_days + (rng.integers(1, 20) if rng.random() < late_p else -rng.integers(1, 12))
            delivered = t + pd.Timedelta(days=max(int(delay), 2), hours=int(rng.integers(0, 23)))
            status = "delivered" if delivered <= t1 else "shipped"
            if rng.random() < 0.012:
                status = "canceled"
            orders.append((
                order_id, cust_id, status, t, t + pd.Timedelta(minutes=int(rng.integers(5, 600))),
                t + pd.Timedelta(days=2), delivered if status == "delivered" else pd.NaT,
                (t + pd.Timedelta(days=est_days)).normalize(),
            ))
            total = 0.0
            for k, p in enumerate(pidx, 1):
                price = product_price[p]
                freight = round(float(rng.uniform(8, 40)), 2)
                total += price + freight
                items.append((order_id, k, products.product_id[p], sellers.seller_id[product_seller[p]],
                              t + pd.Timedelta(days=3), price, freight))
            ptype = rng.choice(["credit_card", "boleto", "voucher", "debit_card"], p=[0.74, 0.19, 0.05, 0.02])
            inst = int(rng.integers(1, 11)) if ptype == "credit_card" else 1
            payments.append((order_id, 1, ptype, inst, round(total, 2)))

            late = delay > est_days
            score = int(np.clip(rng.normal(2.3 if late else 4.4, 1.0), 1, 5))
            if status == "delivered":
                reviews.append((f"r{oid:08d}", order_id, score, None, None,
                                delivered.normalize() + pd.Timedelta(days=1), delivered + pd.Timedelta(days=2)))

            # Dropout is more likely after a bad experience.
            drop = p_drop[c] * (1.8 if late else 1.0) * (1.6 if score <= 2 else 1.0)
            gap = rng.exponential(1 / max(lam[c], 1e-9)) + 1
            if rng.random() < min(drop, 0.97) or gap > span_days:
                alive = False
            else:
                t = t + pd.Timedelta(days=float(gap))

    cols = {
        "olist_customers_dataset": (customers, ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
                                                "customer_city", "customer_state"]),
        "olist_orders_dataset": (orders, ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
                                          "order_approved_at", "order_delivered_carrier_date",
                                          "order_delivered_customer_date", "order_estimated_delivery_date"]),
        "olist_order_items_dataset": (items, ["order_id", "order_item_id", "product_id", "seller_id",
                                              "shipping_limit_date", "price", "freight_value"]),
        "olist_order_payments_dataset": (payments, ["order_id", "payment_sequential", "payment_type",
                                                    "payment_installments", "payment_value"]),
        "olist_order_reviews_dataset": (reviews, ["review_id", "order_id", "review_score", "review_comment_title",
                                                  "review_comment_message", "review_creation_date",
                                                  "review_answer_timestamp"]),
    }
    paths = []
    for stem, (rows, names) in cols.items():
        p = data_dir / f"{stem}.csv"
        pd.DataFrame(rows, columns=names).to_csv(p, index=False)
        paths.append(p)
    for stem, df in {
        "olist_products_dataset": products,
        "olist_sellers_dataset": sellers,
        "product_category_name_translation": pd.DataFrame(
            list(_CATEGORIES.items()), columns=["product_category_name", "product_category_name_english"]),
    }.items():
        p = data_dir / f"{stem}.csv"
        df.to_csv(p, index=False)
        paths.append(p)
    log.info("synthetic dataset: %d customers, %d orders -> %s", n_customers, oid, data_dir)
    return paths
