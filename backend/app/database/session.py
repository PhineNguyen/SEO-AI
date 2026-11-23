"""Synchronous SQLAlchemy engine, sessionmaker, and FastAPI DB session dependency."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def create_db_engine(database_url: str, **kwargs: Any) -> Engine:
    """Create a synchronous SQLAlchemy engine configured for PostgreSQL."""
    engine_kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 1800,
    }
    engine_kwargs.update(kwargs)
    return create_engine(database_url, **engine_kwargs)


@lru_cache
def get_engine() -> Engine:
    """Return the cached application SQLAlchemy engine."""
    return create_db_engine(get_settings().DATABASE_URL)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the cached session factory bound to the application engine."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped SQLAlchemy Session.

    Rolls back on unhandled exceptions; callers/services own explicit commit().
    """
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
