"""
run_etl.py
----------
Staging -> OLTP -> Data Warehouse, using the stored procedures.

    python scripts/run_etl.py
"""
import time

import _common  # noqa: F401
from src.db_manager import DW_DB, OLTP_DB, DatabaseConnection

CHECKS = [
    (OLTP_DB, "employees", "SELECT COUNT(*) AS n FROM employees"),
    (OLTP_DB, "employee_job_history", "SELECT COUNT(*) AS n FROM employee_job_history"),
    (OLTP_DB, "performance_reviews", "SELECT COUNT(*) AS n FROM performance_reviews"),
    (DW_DB, "dim_employee (all versions)", "SELECT COUNT(*) AS n FROM dim_employee"),
    (DW_DB, "dim_employee (current rows)", "SELECT COUNT(*) AS n FROM dim_employee WHERE is_current = 1"),
    (DW_DB, "dim_department", "SELECT COUNT(*) AS n FROM dim_department"),
    (DW_DB, "dim_project", "SELECT COUNT(*) AS n FROM dim_project"),
    (DW_DB, "dim_date", "SELECT COUNT(*) AS n FROM dim_date"),
    (DW_DB, "fact_performance_reviews", "SELECT COUNT(*) AS n FROM fact_performance_reviews"),
]


def main() -> None:
    db = DatabaseConnection()
    for label, procedure, schema in [("staging -> OLTP", "sp_load_oltp_from_staging", OLTP_DB),
                                     ("OLTP -> warehouse", "sp_run_full_etl", DW_DB)]:
        started = time.time()
        db.call_procedure(procedure, [], schema)
        print(f"  {label:<20} done in {time.time() - started:5.1f}s")
    print("\nRow counts")
    for schema, label, sql in CHECKS:
        print(f"  {label:<30} {db.fetch_all(sql, schema=schema)[0]['n']:>10,}")


if __name__ == "__main__":
    main()
