"""Structured logging configuration using structlog and standard logging integration."""

import logging
import re
import sys
from typing import Any

import structlog

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|secret|token|api_key|authorization)",
    re.IGNORECASE,
)
REDACTED_VALUE = "***REDACTED***"


def _redact_value(value: Any) -> Any:
    """Recursively redact sensitive dictionary keys inside log event payloads."""
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and SENSITIVE_KEY_PATTERN.search(key):
                sanitized[key] = REDACTED_VALUE
            else:
                sanitized[key] = _redact_value(item)
        return sanitized
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_sensitive_fields(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that masks secrets, tokens, passwords, and API keys."""
    return _redact_value(event_dict)


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure structlog and route stdlib/uvicorn/celery logs through one formatter.

    Idempotent: clears existing root handlers before attaching the configured handler.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_fields,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery"):
        lib_logger = logging.getLogger(logger_name)
        lib_logger.handlers.clear()
        lib_logger.propagate = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
