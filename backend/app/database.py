"""Database access (SQLAlchemy 2.x + psycopg3 -> Supabase PostgreSQL).

The engine is created lazily so importing this module never needs a live DB.
All money logic lives in SQL functions (place_prediction, settle_market, ...);
the backend calls them inside one transaction per request.
"""
from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set. Fill it in backend/.env")
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": 10,
            # Supabase poolers (pgbouncer/supavisor) do not support server-side
            # prepared statements reliably, so turn them off.
            "prepare_threshold": None,
        },
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One transaction: commit on success, rollback on any error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one transaction per request."""
    with session_scope() as session:
        yield session


def check_db() -> dict[str, Any]:
    """Connectivity probe. Never leaks connection details in the error."""
    started = time.perf_counter()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        return {"ok": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:  # noqa: BLE001 - report type only
        return {"ok": False, "error": type(exc).__name__}


def schema_summary() -> dict[str, Any]:
    """How many public tables exist and how many ledger reconcile issues there are."""
    with get_engine().connect() as conn:
        tables = conn.execute(
            text("select count(*) from pg_tables where schemaname = 'public'")
        ).scalar_one()
        try:
            issues = conn.execute(text("select count(*) from ledger_reconcile()")).scalar_one()
        except Exception:  # noqa: BLE001
            conn.rollback()
            issues = None  # migration not applied yet
    return {"tables": tables, "reconcile_issues": issues}
