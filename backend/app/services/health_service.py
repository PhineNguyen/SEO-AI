"""Service checks for PostgreSQL and Redis readiness."""

import time
from typing import Any

import psycopg
import redis

from app.config import Settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def to_psycopg_dsn(database_url: str) -> str:
    """Convert SQLAlchemy-style PostgreSQL URL to a raw psycopg connection DSN."""
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url[len("postgresql+psycopg://") :]
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url[len("postgresql+psycopg2://") :]
    return database_url


def check_database(database_url: str, timeout_seconds: int = 3) -> dict[str, Any]:
    """Execute a lightweight SELECT 1 against PostgreSQL without leaking credentials."""
    start = time.perf_counter()
    dsn = to_psycopg_dsn(database_url)
    try:
        with psycopg.connect(dsn, connect_timeout=timeout_seconds) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {"status": "ok", "latency_ms": latency_ms, "error": None}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        error_type = type(exc).__name__
        logger.warning("database_readiness_check_failed", error_type=error_type)
        return {"status": "error", "latency_ms": latency_ms, "error": error_type}


def check_redis(redis_url: str, timeout_seconds: float = 2.0) -> dict[str, Any]:
    """Ping Redis server without leaking credentials on connection errors."""
    start = time.perf_counter()
    client: redis.Redis[Any] | None = None
    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_timeout=timeout_seconds,
            socket_connect_timeout=timeout_seconds,
        )
        client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {"status": "ok", "latency_ms": latency_ms, "error": None}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)
        error_type = type(exc).__name__
        logger.warning("redis_readiness_check_failed", error_type=error_type)
        return {"status": "error", "latency_ms": latency_ms, "error": error_type}
    finally:
        if client is not None:
            client.close()


def run_readiness_checks(settings: Settings) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Run all backing service readiness checks and return overall readiness flag."""
    db_check = check_database(settings.DATABASE_URL)
    redis_check = check_redis(settings.REDIS_URL)
    checks = {
        "database": db_check,
        "redis": redis_check,
    }
    is_ready = db_check["status"] == "ok" and redis_check["status"] == "ok"
    return is_ready, checks
