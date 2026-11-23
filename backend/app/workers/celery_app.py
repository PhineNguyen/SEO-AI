"""Celery application configuration and worker diagnostics."""

from datetime import UTC, datetime
from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.config import Settings, get_settings
from app.utils.logging import configure_logging


@setup_logging.connect
def configure_celery_logging(**_kwargs: Any) -> None:
    """Route Celery worker logs through the shared structlog configuration."""
    settings = get_settings()
    configure_logging(log_level=settings.LOG_LEVEL, json_logs=settings.use_json_logs)


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Instantiate and configure the Celery application."""
    resolved_settings = settings or get_settings()
    instance = Celery(
        "keyword_research_agent",
        broker=resolved_settings.CELERY_BROKER_URL,
        backend=resolved_settings.CELERY_RESULT_BACKEND,
    )
    instance.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_time_limit=1800,
        task_soft_time_limit=1500,
        broker_connection_retry_on_startup=True,
        result_expires=86400,
        task_track_started=True,
    )
    return instance


celery_app = create_celery_app()


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Diagnostic worker task verifying Celery task execution."""
    return {
        "status": "ok",
        "worker_time_utc": datetime.now(UTC).isoformat(),
    }
