"""
db_manager.py
-------------
Everything that talks to MySQL goes through this file.

* DatabaseConnection - a Singleton. No matter how many managers or
  Streamlit reruns ask for it, there is exactly one object (and one set of
  connection pools) per process. That keeps us from opening a fresh pile of
  connections every time someone clicks a button.
* DatabaseHandler    - a small base class the manager classes inherit from.
  It wraps the singleton with friendly helpers (fetch a DataFrame, run a
  transaction, call a stored procedure).
* DatabaseError      - the one exception type the rest of the app has to
  worry about.

Credentials come from Streamlit secrets (when deployed) or from
environment variables / a .env file (when running locally).
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, URL
from sqlalchemy.exc import SQLAlchemyError

try:                                    # .env is optional
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:                     # pragma: no cover
    pass

STAGING_DB = "employee_staging"
OLTP_DB = "employee_oltp"
DW_DB = "employee_dw"


class DatabaseError(Exception):
    """Raised when MySQL says no. The message is written for humans."""


def _load_settings() -> dict[str, Any]:
    settings: dict[str, Any] = {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "port": os.getenv("DB_PORT", "3306"),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "ssl_ca": os.getenv("DB_SSL_CA", ""),
    }
    try:                                # Streamlit Cloud / local secrets.toml
        import streamlit as st
        if "mysql" in st.secrets:
            settings.update(dict(st.secrets["mysql"]))
    except Exception:                   # no secrets file, or not running in Streamlit
        pass
    settings["port"] = int(settings["port"])
    return settings


class DatabaseConnection:
    """Thread-safe Singleton that hands out SQLAlchemy engines per schema."""

    _instance: Optional["DatabaseConnection"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DatabaseConnection":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:           # double-checked locking
                    instance = super().__new__(cls)
                    instance._settings = _load_settings()
                    instance._engines = {}
                    instance._engine_lock = threading.Lock()
                    cls._instance = instance
        return cls._instance

    # ------------------------------------------------------------ engines
    def engine(self, schema: Optional[str] = None) -> Engine:
        key = schema or ""
        with self._engine_lock:
            if key not in self._engines:
                s = self._settings
                url = URL.create("mysql+pymysql", username=s["user"], password=s["password"],
                                 host=s["host"], port=s["port"], database=schema)
                connect_args = {"ssl": {"ca": s["ssl_ca"]}} if s.get("ssl_ca") else {}
                self._engines[key] = create_engine(
                    url, pool_pre_ping=True, pool_recycle=1800,
                    pool_size=5, max_overflow=5, connect_args=connect_args)
            return self._engines[key]

    @staticmethod
    def _friendly(exc: Exception) -> str:
        original = getattr(exc, "orig", None)
        return str(original or exc)

    # ------------------------------------------------------------ queries
    def ping(self) -> bool:
        try:
            with self.engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def fetch_df(self, sql: str, params: Optional[dict] = None,
                 schema: Optional[str] = None) -> pd.DataFrame:
        try:
            with self.engine(schema).connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Query failed: {self._friendly(exc)}") from exc

    def fetch_all(self, sql: str, params: Optional[dict] = None,
                  schema: Optional[str] = None) -> list[dict]:
        try:
            with self.engine(schema).connect() as conn:
                return [dict(row._mapping) for row in conn.execute(text(sql), params or {})]
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Query failed: {self._friendly(exc)}") from exc

    def execute(self, sql: str, params: Optional[dict] = None,
                schema: Optional[str] = None) -> int:
        try:
            with self.engine(schema).begin() as conn:
                return conn.execute(text(sql), params or {}).rowcount
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Statement failed: {self._friendly(exc)}") from exc

    @contextmanager
    def transaction(self, schema: Optional[str] = None) -> Iterator[Connection]:
        """Everything inside the `with` block commits together, or not at all."""
        try:
            with self.engine(schema).begin() as conn:
                yield conn
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Transaction rolled back: {self._friendly(exc)}") from exc

    def call_procedure(self, name: str, args: Sequence[Any] = (),
                       schema: Optional[str] = None) -> None:
        placeholders = ", ".join(f":a{i}" for i in range(len(args)))
        params = {f"a{i}": value for i, value in enumerate(args)}
        self.execute(f"CALL {name}({placeholders})", params, schema)


class DatabaseHandler:
    """Base class for the manager classes: knows its schema and how to query it."""

    def __init__(self, schema: str) -> None:
        self._schema = schema
        self._db = DatabaseConnection()

    def _fetch_df(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        return self._db.fetch_df(sql, params, self._schema)

    def _fetch_all(self, sql: str, params: Optional[dict] = None) -> list[dict]:
        return self._db.fetch_all(sql, params, self._schema)

    def _execute(self, sql: str, params: Optional[dict] = None) -> int:
        return self._db.execute(sql, params, self._schema)

    def _transaction(self):
        return self._db.transaction(self._schema)
