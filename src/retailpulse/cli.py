"""Command-line interface: `retailpulse <command>`."""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from .config import PROJECT_ROOT, Settings


def _settings(args: argparse.Namespace) -> Settings:
    s = Settings()
    if getattr(args, "data_dir", None):
        s.data_dir = Path(args.data_dir)
    if getattr(args, "artifacts_dir", None):
        s.artifacts_dir = Path(args.artifacts_dir)
    if getattr(args, "churn_horizon", None):
        s.churn_horizon_days = args.churn_horizon
    return s


def cmd_download(args):
    from .data import download_olist
    download_olist(_settings(args).data_dir, overwrite=args.overwrite)


def cmd_generate(args):
    from .data import generate_synthetic
    generate_synthetic(_settings(args).data_dir, n_customers=args.customers, seed=args.seed)


def cmd_run(args):
    from . import pipeline
    from .data import generate_synthetic, raw_files_present
    s = _settings(args)
    if not raw_files_present(s.data_dir):
        if args.synthetic:
            generate_synthetic(s.data_dir)
        else:
            sys.exit(f"No raw data in {s.data_dir}. Run `retailpulse download` (real Olist data) "
                     "or `retailpulse run --synthetic`.")
    m = pipeline.run(s, n_folds=args.folds)
    print(f"\nDone. Best churn model: {m['churn']['best_model']}. "
          f"Results: {s.artifacts_dir / 'RESULTS.md'}")


def cmd_serve(args):
    import uvicorn
    uvicorn.run("retailpulse.api:app", host=args.host, port=args.port, reload=False)


def cmd_dashboard(args):
    app = PROJECT_ROOT / "dashboard" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app),
                    "--server.port", str(args.port), "--server.address", args.host], check=True)


def cmd_export_postgres(args):
    from .export import export_to_postgres
    export_to_postgres(_settings(args), args.url, schema=args.schema)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="retailpulse", description="E-commerce customer intelligence")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--data-dir", help="raw CSV folder (default: data/raw)")
    p.add_argument("--artifacts-dir", help="output folder (default: artifacts)")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("download", help="download the public Olist dataset")
    d.add_argument("--overwrite", action="store_true")
    d.set_defaults(func=cmd_download)

    g = sub.add_parser("generate", help="generate a synthetic Olist-shaped dataset")
    g.add_argument("--customers", type=int, default=8000)
    g.add_argument("--seed", type=int, default=42)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="build warehouse, train models, score customers, export")
    r.add_argument("--synthetic", action="store_true", help="generate synthetic data if none is present")
    r.add_argument("--churn-horizon", type=int, help="churn window in days (default 120)")
    r.add_argument("--folds", type=int, default=4, help="time-aware validation folds")
    r.set_defaults(func=cmd_run)

    sv = sub.add_parser("serve", help="start the REST API")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=cmd_serve)

    db = sub.add_parser("dashboard", help="start the Streamlit dashboard")
    db.add_argument("--host", default="127.0.0.1")
    db.add_argument("--port", type=int, default=8501)
    db.set_defaults(func=cmd_dashboard)

    pg = sub.add_parser("export-postgres", help="copy analytics tables to PostgreSQL")
    pg.add_argument("--url", required=True, help="postgresql+psycopg://user:pass@host:5432/db")
    pg.add_argument("--schema", default="analytics")
    pg.set_defaults(func=cmd_export_postgres)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S")
    args.func(args)


if __name__ == "__main__":
    main()
