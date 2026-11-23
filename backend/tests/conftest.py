"""Shared pytest fixtures for backend unit and API tests."""

from collections.abc import Iterator

import pytest
from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_test_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide safe deterministic test environment variables and clear cached settings."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://test_user:test_pass@127.0.0.1:5432/test_db",
    )
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "test-only-jwt-secret-key-at-least-32-characters-long",
    )
    monkeypatch.setenv(
        "OAUTH_TOKEN_ENCRYPTION_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Return a FastAPI TestClient wired with isolated test settings."""
    application = create_app(get_settings())
    return TestClient(application)
