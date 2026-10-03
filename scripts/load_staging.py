"""
load_staging.py
---------------
Loads the CSVs produced by synthesize_data.py into the employee_staging
database. Run it after setup_database.py.

    python scripts/load_staging.py
    python scripts/load_staging.py --data-dir data/synthetic
"""
import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import text

import _common  # noqa: F401
from _common import ROOT
from src.db_manager import STAGING_DB, DatabaseConnection

TABLES = {
    "stg_employee_snapshot": {"parse_dates": ["hire_date"]},
    "stg_employee_history": {"parse_dates": ["effective_start", "effective_end"]},
    "stg_projects": {"parse_dates": ["start_date", "end_date"]},
    "stg_assignments": {"parse_dates": ["start_date", "end_date"]},
    "stg_reviews": {"parse_dates": ["review_date"], "dtype": {"project_id": "Int64"}},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "synthetic")
    parser.add_argument("--chunk", type=int, default=5000)
    args = parser.parse_args()

    engine = DatabaseConnection().engine(STAGING_DB)
    for table, options in TABLES.items():
        csv_path = args.data_dir / f"{table}.csv"
        if not csv_path.exists():
            raise SystemExit(f"Missing {csv_path}. Run scripts/synthesize_data.py first.")
        frame = pd.read_csv(csv_path, **options)
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table}"))
        frame.to_sql(table, engine, if_exists="append", index=False,
                     chunksize=args.chunk, method="multi")
        print(f"  loaded {len(frame):>9,} rows into {table}")
    print("Staging is loaded.")


if __name__ == "__main__":
    main()
