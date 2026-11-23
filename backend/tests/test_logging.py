"""Unit tests for structured logging and sensitive field redaction."""

import logging

from app.utils.logging import REDACTED_VALUE, configure_logging, redact_sensitive_fields


def test_redact_sensitive_fields_masks_secrets_recursively() -> None:
    payload = {
        "event": "connector_init",
        "password": "my-db-password",
        "api_key": "sk-123456",
        "Authorization": "Bearer secret-jwt",
        "nested": {
            "oauth_token": "ya29.secret",
            "country": "vn",
        },
        "items": [{"client_secret": "top-secret", "keyword": "seo tools"}],
    }
    redacted = redact_sensitive_fields(None, "info", payload)

    assert redacted["event"] == "connector_init"
    assert redacted["password"] == REDACTED_VALUE
    assert redacted["api_key"] == REDACTED_VALUE
    assert redacted["Authorization"] == REDACTED_VALUE
    assert redacted["nested"]["oauth_token"] == REDACTED_VALUE
    assert redacted["nested"]["country"] == "vn"
    assert redacted["items"][0]["client_secret"] == REDACTED_VALUE
    assert redacted["items"][0]["keyword"] == "seo tools"


def test_configure_logging_is_idempotent() -> None:
    configure_logging(log_level="INFO", json_logs=False)
    configure_logging(log_level="DEBUG", json_logs=True)

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1
    assert root_logger.level == logging.DEBUG
