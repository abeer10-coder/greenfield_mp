"""
db_manager.py
-------------
Database connection manager supporting both local environment variables (.env)
and Streamlit Community Cloud (st.secrets) with Aiven MySQL SSL enforcement.
"""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import pandas as pd
import pymysql
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

STAGING_DB = "employee_staging"
OLTP_DB = "employee_oltp"
DW_DB = "employee_dw"


def _get_credential(key: str, default: str = "") -> str:
    """Check Streamlit Cloud Secrets first, then fallback to local os.environ."""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return str(os.getenv(key, default))


class DatabaseError(Exception):
    """Custom exception wrapper for database operations."""
    pass


class DatabaseConnection:
    """Singleton managing database engines and connections for Aiven / MySQL."""

    _instance: Optional[DatabaseConnection] = None
    _lock = threading.Lock()

    def __new__(cls) -> DatabaseConnection:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._engines = {}
        return cls._instance

    def __init__(self):
        self.host = _get_credential(
            "MYSQL_HOST",
            _get_credential("DB_HOST", "mysql-350b651f-greenfieldminiproject.h.aivencloud.com"),
        )
        self.port = int(
            _get_credential(
                "MYSQL_PORT",
                _get_credential("DB_PORT", "10999"),
            )
        )
        self.user = _get_credential(
            "MYSQL_USER",
            _get_credential("DB_USER", "avnadmin"),
        )
        self.password = _get_credential(
            "MYSQL_PASSWORD",
            _get_credential("DB_PASSWORD", "AVNS_sGB23mznLiJ5mbGWO2_"),
        )
        self.database = _get_credential(
            "MYSQL_DATABASE",
            _get_credential("DB_NAME", "defaultdb"),
        )

    def get_connection(self, schema: Optional[str] = None):
        """Creates a PyMySQL connection with TLS/SSL enabled for Aiven."""
        try:
            return pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=schema or self.database,
                cursorclass=pymysql.cursors.DictCursor,
                ssl={"check_hostname": False},
                connect_timeout=10,
            )
        except Exception as e:
            raise DatabaseError(f"Failed to connect to MySQL: {e}") from e

    def engine(self, schema: Optional[str] = None) -> Engine:
        """Returns or creates a SQLAlchemy engine configured for Aiven SSL."""
        target_schema = schema or self.database
        if not hasattr(self, "_engines"):
            self._engines = {}
        if target_schema not in self._engines:
            url = f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{target_schema}"
            self._engines[target_schema] = create_engine(
                url,
                connect_args={"ssl": {"check_hostname": False}},
                pool_pre_ping=True,
                pool_recycle=300,
            )
        return self._engines[target_schema]

    def _friendly(self, exc: Exception) -> str:
        return str(getattr(exc, "orig", exc))

    def ping(self) -> bool:
        """Verifies if the database server is reachable."""
        try:
            conn = self.get_connection()
            conn.ping(reconnect=True)
            conn.close()
            return True
        except Exception as err:
            st.warning(f"Connection diagnostic error: {err}")
            return False

    def fetch_df(self, sql: str, params: Optional[dict] = None, schema: Optional[str] = None) -> pd.DataFrame:
        try:
            with self.engine(schema).connect() as conn:
                return pd.read_sql(text(sql), conn, params=params or {})
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Query failed: {self._friendly(exc)}") from exc

    def fetch_all(self, sql: str, params: Optional[dict] = None, schema: Optional[str] = None) -> list[dict]:
        try:
            with self.engine(schema).connect() as conn:
                return [dict(row._mapping) for row in conn.execute(text(sql), params or {})]
        except SQLAlchemyError as exc:
            raise DatabaseError(f"Query failed: {self._friendly(exc)}") from exc

    def execute(self, sql: str, params: Optional[dict] = None, schema: Optional[str] = None) -> int:
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

    def call_procedure(self, name: str, args: Sequence[Any] = (), schema: Optional[str] = None) -> None:
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
