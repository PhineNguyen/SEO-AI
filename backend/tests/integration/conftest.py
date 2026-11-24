"""Shared PostgreSQL integration fixtures using Alembic and transactional rollbacks."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/keyword_research_test"
)


def get_base_test_database_url() -> str:
    """Return configured TEST_DATABASE_URL or default local Docker Postgres URL."""
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def make_alembic_config(database_url: str) -> Config:
    """Build an Alembic Config pointing at the repository alembic directory and explicit URL."""
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def create_fresh_database(database_url: str) -> None:
    """Drop and recreate the target PostgreSQL database via the maintenance 'postgres' DB."""
    parsed = make_url(database_url)
    db_name = parsed.database
    if not db_name:
        raise ValueError("TEST_DATABASE_URL must specify a database name")
    maintenance_url = parsed.set(database="postgres")
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL not reachable for integration tests: {type(exc).__name__}")
    finally:
        engine.dispose()


def drop_database(database_url: str) -> None:
    """Drop a temporary test database via the maintenance 'postgres' DB."""
    parsed = make_url(database_url)
    db_name = parsed.database
    if not db_name:
        return
    maintenance_url = parsed.set(database="postgres")
    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> Iterator[str]:
    """Provision an isolated PostgreSQL database for constraint integration tests."""
    url = get_base_test_database_url()
    create_fresh_database(url)
    try:
        yield url
    finally:
        drop_database(url)


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    """Run Alembic migrations to head and yield an engine bound to the test DB."""
    from app.agents.checkpointer import open_postgres_checkpointer

    cfg = make_alembic_config(test_database_url)
    command.upgrade(cfg, "head")
    with open_postgres_checkpointer(test_database_url, run_setup=True):
        pass
    engine = create_engine(test_database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """Provide an isolated SQLAlchemy Session rolled back after each test."""
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def api_client(db_session: Session) -> Iterator[object]:
    """Provide a FastAPI TestClient wired to the isolated PostgreSQL db_session."""
    from app.config import get_settings
    from app.database.session import get_db
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(get_settings())

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
