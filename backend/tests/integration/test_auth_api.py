"""Integration tests for /api/v1/auth endpoints and role dependencies against PostgreSQL."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Annotated

import pytest
from app.api.deps import get_current_active_admin
from app.config import get_settings
from app.database.session import get_db
from app.main import create_app
from app.models.user import User
from app.utils.security import create_access_token, hash_password
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def api_client(db_session: Session) -> Iterator[TestClient]:
    """Provide a TestClient wired to the isolated rollback-scoped PostgreSQL session."""
    app = create_app(get_settings())

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_register_normalizes_email_and_omits_password_hash(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "  SEO@Example.com ",
            "password": "Password123!",
            "full_name": "Nguyen Van A",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "seo@example.com"
    assert body["full_name"] == "Nguyen Van A"
    assert body["role"] == "member"
    assert body["is_active"] is True
    assert "password_hash" not in body
    assert "password" not in body


def test_duplicate_email_registration_returns_409(api_client: TestClient) -> None:
    resp1 = api_client.post(
        "/api/v1/auth/register",
        json={"email": "seo@example.com", "password": "Password123!"},
    )
    assert resp1.status_code == 201

    resp2 = api_client.post(
        "/api/v1/auth/register",
        json={"email": "SEO@Example.com", "password": "Password456!"},
    )
    assert resp2.status_code == 409
    err = resp2.json()
    assert err["error"]["code"] == "HTTP_409"


def test_login_and_me_flow(api_client: TestClient) -> None:
    api_client.post(
        "/api/v1/auth/register",
        json={
            "email": "analyst@example.com",
            "password": "StrongPassword123",
            "full_name": "SEO Analyst",
        },
    )

    login_resp = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ANALYST@example.com", "password": "StrongPassword123"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] == 3600
    token = token_data["access_token"]

    me_resp = api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_body = me_resp.json()
    assert me_body["email"] == "analyst@example.com"
    assert me_body["full_name"] == "SEO Analyst"
    assert "password_hash" not in me_body


def test_login_invalid_credentials_returns_401(api_client: TestClient) -> None:
    api_client.post(
        "/api/v1/auth/register",
        json={"email": "user@example.com", "password": "CorrectPassword123"},
    )

    bad_pw = api_client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "WrongPassword"},
    )
    assert bad_pw.status_code == 401
    assert bad_pw.headers.get("WWW-Authenticate") == "Bearer"

    unknown = api_client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "CorrectPassword123"},
    )
    assert unknown.status_code == 401


def test_me_requires_valid_non_expired_bearer_token(
    api_client: TestClient,
    db_session: Session,
) -> None:
    missing = api_client.get("/api/v1/auth/me")
    assert missing.status_code == 401

    invalid = api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid.jwt.token"},
    )
    assert invalid.status_code == 401

    user = User(
        email="expired@example.com",
        password_hash=hash_password("Password123!"),
        role="member",
    )
    db_session.add(user)
    db_session.flush()

    expired_token, _ = create_access_token(
        user.id,
        get_settings(),
        expires_delta=timedelta(seconds=-10),
    )
    expired_resp = api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired_resp.status_code == 401


def test_inactive_user_blocked_on_login_and_me(
    api_client: TestClient,
    db_session: Session,
) -> None:
    user = User(
        email="inactive@example.com",
        password_hash=hash_password("Password123!"),
        role="member",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    token, _ = create_access_token(user.id, get_settings())
    user.is_active = False
    db_session.commit()

    login_resp = api_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 403

    me_resp = api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 401


def test_admin_dependency_enforces_admin_role(db_session: Session) -> None:
    app = create_app(get_settings())

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    @app.get("/_test/admin-only")
    def _admin_only(
        admin: Annotated[User, Depends(get_current_active_admin)],
    ) -> dict[str, str]:
        return {"email": admin.email}

    member = User(
        email="member@example.com",
        password_hash=hash_password("Password123!"),
        role="member",
    )
    admin = User(
        email="admin@example.com",
        password_hash=hash_password("Password123!"),
        role="admin",
    )
    db_session.add_all([member, admin])
    db_session.commit()

    member_token, _ = create_access_token(member.id, get_settings())
    admin_token, _ = create_access_token(admin.id, get_settings())

    client = TestClient(app)
    member_resp = client.get(
        "/_test/admin-only",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert member_resp.status_code == 403

    admin_resp = client.get(
        "/_test/admin-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_resp.status_code == 200
    assert admin_resp.json() == {"email": "admin@example.com"}
