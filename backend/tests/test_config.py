"""Unit tests for Pydantic Settings loading and production safety validation."""

import pytest
from app.config import Settings, get_settings
from pydantic import ValidationError


def test_settings_defaults_load_in_test_env() -> None:
    settings = get_settings()
    assert settings.APP_ENV == "test"
    assert settings.EMBEDDING_PROVIDER == "openai"
    assert settings.OPENAI_EMBEDDING_MODEL == "text-embedding-3-small"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.is_production is False


def test_cors_origins_parses_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, http://localhost:3000 ")
    settings = Settings()
    assert settings.CORS_ORIGINS == ["https://app.example.com", "http://localhost:3000"]


def test_log_level_normalizes_lowercase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = Settings()
    assert settings.LOG_LEVEL == "DEBUG"


def test_invalid_embedding_provider_raises_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "unsupported_provider")
    with pytest.raises(ValidationError):
        Settings()


def test_production_rejects_placeholder_jwt_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "replace-with-a-secure-random-64-char-secret-key")
    monkeypatch.setenv(
        "OAUTH_TOKEN_ENCRYPTION_KEY",
        "valid-non-placeholder-fernet-key-example-32-bytes=",
    )
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings()


def test_production_rejects_app_debug_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("JWT_SECRET_KEY", "a-very-strong-production-secret-key-over-32-chars")
    monkeypatch.setenv(
        "OAUTH_TOKEN_ENCRYPTION_KEY",
        "valid-non-placeholder-fernet-key-example-32-bytes=",
    )
    with pytest.raises(ValidationError, match="APP_DEBUG"):
        Settings()


def test_valid_production_settings_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "false")
    monkeypatch.setenv("JWT_SECRET_KEY", "prod-secret-key-with-more-than-32-characters-12345")
    monkeypatch.setenv(
        "OAUTH_TOKEN_ENCRYPTION_KEY",
        "Z3JpZGNvbmZpZy1wcm9kLWZlcm5ldC1rZXktMzItYnl0ZXM=",
    )
    settings = Settings()
    assert settings.is_production is True
    assert settings.use_json_logs is True


def test_secret_values_masked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_jwt = "super-secret-jwt-value-must-never-appear-in-repr"
    secret_openai = "sk-test-fake-openai-key-for-repr-check"
    monkeypatch.setenv("JWT_SECRET_KEY", secret_jwt)
    monkeypatch.setenv("OPENAI_API_KEY", secret_openai)

    settings = Settings()
    rendered = repr(settings)
    assert secret_jwt not in rendered
    assert secret_openai not in rendered
