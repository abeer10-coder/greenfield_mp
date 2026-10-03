"""
setup_database.py
-----------------
Runs the SQL files in sql/ (01 -> 05) against your MySQL server: databases,
staging tables, OLTP schema, star schema and every stored procedure.

    python scripts/setup_database.py

Heads up: the DDL files DROP and recreate their tables, so running this
again wipes whatever is in them. That's what you want while developing,
less so after you've loaded 100k rows.
"""
import _common  # noqa: F401  (sets up the import path)
from _common import ROOT
from src.db_manager import DatabaseConnection

SQL_FILES = [
    "01_schemas_and_staging.sql",
    "02_oltp_ddl.sql",
    "03_olap_ddl.sql",
    "04_staging_to_oltp.sql",
    "05_dw_etl_procedures.sql",
]


def split_statements(script: str):
    """Split a .sql file into statements, understanding Workbench-style DELIMITER lines."""
    delimiter, buffer = ";", []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1].strip()
            continue
        if not stripped or stripped.startswith("--"):
            if buffer:
                buffer.append(line)
            continue
        buffer.append(line)
        if stripped.endswith(delimiter):
            statement = "\n".join(buffer).strip()
            statement = statement[: -len(delimiter)].strip()
            if statement:
                yield statement
            buffer = []


def main() -> None:
    db = DatabaseConnection()
    if not db.ping():
        raise SystemExit("Can't reach MySQL. Check DB_HOST / DB_USER / DB_PASSWORD in your .env file.")
    raw = db.engine().raw_connection()
    try:
        cursor = raw.cursor()
        for name in SQL_FILES:
            statements = list(split_statements((ROOT / "sql" / name).read_text(encoding="utf-8")))
            for statement in statements:
                cursor.execute(statement)
            raw.commit()
            print(f"  ran {name} ({len(statements)} statements)")
    finally:
        raw.close()
    print("Database is ready.")


if __name__ == "__main__":
    main()
