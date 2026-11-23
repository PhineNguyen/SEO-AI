"""Tests for /health, /ready, RequestContextMiddleware, and error envelopes."""

import pytest
from app.config import get_settings
from app.main import create_app
from app.services import health_service
from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok_and_request_id(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["version"] == "0.1.0"
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) == 32


def test_incoming_valid_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-abc.123_ok"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-abc.123_ok"


def test_incoming_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad id with spaces!"})
    assert response.status_code == 200
    returned_id = response.headers["X-Request-ID"]
    assert returned_id != "bad id with spaces!"
    assert len(returned_id) == 32


def test_readiness_returns_200_when_dependencies_ok(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_service,
        "check_database",
        lambda _url: {"status": "ok", "latency_ms": 1.2, "error": None},
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda _url: {"status": "ok", "latency_ms": 0.8, "error": None},
    )

    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"


def test_readiness_returns_503_when_database_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_service,
        "check_database",
        lambda _url: {"status": "error", "latency_ms": 5.0, "error": "OperationalError"},
    )
    monkeypatch.setattr(
        health_service,
        "check_redis",
        lambda _url: {"status": "ok", "latency_ms": 0.9, "error": None},
    )

    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["status"] == "error"
    assert body["checks"]["redis"]["status"] == "ok"


def test_unknown_route_returns_standard_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nonexistent", headers={"X-Request-ID": "req-404"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "HTTP_404"
    assert body["error"]["request_id"] == "req-404"
    assert response.headers["X-Request-ID"] == "req-404"


def test_validation_and_unhandled_error_envelopes() -> None:
    app = create_app(get_settings())

    @app.get("/_test/validate/{item_id}")
    def _validate(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/_test/boom")
    def _boom() -> dict[str, str]:
        raise RuntimeError("sensitive internal detail")

    local_client = TestClient(app, raise_server_exceptions=False)

    val_resp = local_client.get("/_test/validate/not-an-int", headers={"X-Request-ID": "req-422"})
    assert val_resp.status_code == 422
    assert val_resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert val_resp.json()["error"]["request_id"] == "req-422"

    err_resp = local_client.get("/_test/boom", headers={"X-Request-ID": "req-500"})
    assert err_resp.status_code == 500
    err_body = err_resp.json()
    assert err_body["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert err_body["error"]["message"] == "Internal server error"
    assert err_body["error"]["request_id"] == "req-500"
    assert "sensitive internal detail" not in err_resp.text


def test_to_psycopg_dsn_strips_driver_suffix() -> None:
    assert (
        health_service.to_psycopg_dsn("postgresql+psycopg://user:pass@db:5432/app")
        == "postgresql://user:pass@db:5432/app"
    )
    assert (
        health_service.to_psycopg_dsn("postgresql+psycopg2://user:pass@db:5432/app")
        == "postgresql://user:pass@db:5432/app"
    )


def test_check_database_unreachable_does_not_leak_credentials() -> None:
    secret_password = "super_secret_db_password_987"
    result = health_service.check_database(
        f"postgresql+psycopg://testuser:{secret_password}@127.0.0.1:1/testdb",
        timeout_seconds=1,
    )
    assert result["status"] == "error"
    assert result["error"] is not None
    assert secret_password not in result["error"]
