"""Tests for Celery application configuration and diagnostic ping task."""

from datetime import datetime

from app.config import get_settings
from app.workers.celery_app import create_celery_app, ping


def test_celery_configuration_values() -> None:
    celery = create_celery_app(get_settings())
    assert celery.conf.task_serializer == "json"
    assert celery.conf.result_serializer == "json"
    assert celery.conf.accept_content == ["json"]
    assert celery.conf.timezone == "UTC"
    assert celery.conf.enable_utc is True
    assert celery.conf.task_acks_late is True
    assert celery.conf.task_reject_on_worker_lost is True
    assert celery.conf.worker_prefetch_multiplier == 1


def test_celery_ping_task_executes_eagerly() -> None:
    result = ping.apply().get()
    assert result["status"] == "ok"
    parsed_time = datetime.fromisoformat(result["worker_time_utc"])
    assert parsed_time.tzinfo is not None
