"""Integration tests for /api/v1/projects CRUD, ownership isolation, and child resources."""

from collections.abc import Iterator

import pytest
from app.config import get_settings
from app.database.session import get_db
from app.main import create_app
from app.models.project import DEFAULT_CLUSTERING_WEIGHTS
from app.models.user import User
from app.utils.security import create_access_token, hash_password
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


@pytest.fixture
def api_client(db_session: Session) -> Iterator[TestClient]:
    """Provide a TestClient wired to the rollback-scoped PostgreSQL session."""
    app = create_app(get_settings())

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_user_with_headers(db_session: Session, email: str) -> tuple[User, dict[str, str]]:
    user = User(
        email=email,
        password_hash=hash_password("StrongPassword123"),
        role="member",
    )
    db_session.add(user)
    db_session.commit()
    token, _ = create_access_token(user.id, get_settings())
    return user, {"Authorization": f"Bearer {token}"}


def test_projects_require_authentication(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/projects")
    assert resp.status_code == 401


def test_create_project_creates_default_settings_and_enforces_uniqueness(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _user_a, headers_a = _create_user_with_headers(db_session, "owner_a@example.com")
    _user_b, headers_b = _create_user_with_headers(db_session, "owner_b@example.com")

    payload = {
        "name": "  B2B CRM Vietnam  ",
        "niche": "SaaS CRM",
        "target_country": "vn",
        "target_language": "VI",
        "target_audience": "SME Founders",
    }
    resp = api_client.post("/api/v1/projects", json=payload, headers=headers_a)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "B2B CRM Vietnam"
    assert body["target_country"] == "VN"
    assert body["target_language"] == "vi"
    assert body["status"] == "ACTIVE"
    assert body["settings"]["clustering_weights"] == DEFAULT_CLUSTERING_WEIGHTS
    assert body["settings"]["default_serp_provider"] == "dataforseo"
    assert body["websites"] == []
    assert body["competitors"] == []

    # Duplicate project name for same owner -> 409
    dup_resp = api_client.post("/api/v1/projects", json=payload, headers=headers_a)
    assert dup_resp.status_code == 409

    # Same project name for a different owner -> 201
    other_resp = api_client.post("/api/v1/projects", json=payload, headers=headers_b)
    assert other_resp.status_code == 201


def test_list_filter_ownership_isolation_update_and_delete(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _user_a, headers_a = _create_user_with_headers(db_session, "iso_a@example.com")
    _user_b, headers_b = _create_user_with_headers(db_session, "iso_b@example.com")

    p1 = api_client.post(
        "/api/v1/projects",
        json={
            "name": "SEO SaaS",
            "niche": "Marketing",
            "target_country": "US",
            "target_language": "en",
        },
        headers=headers_a,
    ).json()
    p2 = api_client.post(
        "/api/v1/projects",
        json={
            "name": "Fintech Blog",
            "niche": "Finance",
            "target_country": "VN",
            "target_language": "vi",
        },
        headers=headers_a,
    ).json()
    api_client.post(
        "/api/v1/projects",
        json={
            "name": "Other User Project",
            "target_country": "VN",
            "target_language": "vi",
        },
        headers=headers_b,
    )

    # User A sees only their 2 projects
    list_a = api_client.get("/api/v1/projects?limit=10&offset=0", headers=headers_a)
    assert list_a.status_code == 200
    assert list_a.json()["total"] == 2

    # Search filter
    search_a = api_client.get("/api/v1/projects?search=fintech", headers=headers_a)
    assert search_a.json()["total"] == 1
    assert search_a.json()["items"][0]["id"] == p2["id"]

    # Ownership isolation: User B cannot view, update, or delete User A's project
    assert api_client.get(f"/api/v1/projects/{p1['id']}", headers=headers_b).status_code == 404
    assert (
        api_client.patch(
            f"/api/v1/projects/{p1['id']}",
            json={"name": "Hijacked"},
            headers=headers_b,
        ).status_code
        == 404
    )
    assert (
        api_client.delete(f"/api/v1/projects/{p1['id']}", headers=headers_b).status_code == 404
    )

    # Archive p1 and filter by status
    patch_resp = api_client.patch(
        f"/api/v1/projects/{p1['id']}",
        json={"status": "ARCHIVED", "name": "SEO SaaS Archived"},
        headers=headers_a,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "ARCHIVED"

    archived_list = api_client.get("/api/v1/projects?status=ARCHIVED", headers=headers_a)
    assert archived_list.json()["total"] == 1
    assert archived_list.json()["items"][0]["id"] == p1["id"]

    # Delete p1
    del_resp = api_client.delete(f"/api/v1/projects/{p1['id']}", headers=headers_a)
    assert del_resp.status_code == 204
    assert api_client.get(f"/api/v1/projects/{p1['id']}", headers=headers_a).status_code == 404


def test_project_settings_get_update_and_validation(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _user, headers = _create_user_with_headers(db_session, "settings@example.com")
    project_id = api_client.post(
        "/api/v1/projects",
        json={"name": "Settings Project", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()["id"]

    get_resp = api_client.get(f"/api/v1/projects/{project_id}/settings", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["clustering_weights"] == DEFAULT_CLUSTERING_WEIGHTS

    bad_put = api_client.put(
        f"/api/v1/projects/{project_id}/settings",
        json={"clustering_weights": {"semantic": 0.9, "serp_overlap": 0.5, "intent": 0.2}},
        headers=headers,
    )
    assert bad_put.status_code == 422

    ok_put = api_client.put(
        f"/api/v1/projects/{project_id}/settings",
        json={
            "clustering_weights": {"semantic": 0.25, "serp_overlap": 0.55, "intent": 0.2},
            "prioritization_weights": {"search_volume": 0.3, "business_relevance": 0.7},
            "default_device": "mobile",
        },
        headers=headers,
    )
    assert ok_put.status_code == 200
    updated = ok_put.json()
    assert updated["default_device"] == "mobile"
    assert updated["clustering_weights"]["serp_overlap"] == 0.55
    assert updated["prioritization_weights"]["business_relevance"] == 0.7


def test_websites_crud_and_primary_atomic_switch(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _user, headers = _create_user_with_headers(db_session, "websites@example.com")
    project_id = api_client.post(
        "/api/v1/projects",
        json={"name": "Websites Project", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()["id"]

    w1_resp = api_client.post(
        f"/api/v1/projects/{project_id}/websites",
        json={
            "domain": "https://WWW.MySite.vn/blog",
            "base_url": "https://MySite.vn/",
            "gsc_property_uri": "sc-domain:mysite.vn",
            "is_primary": True,
        },
        headers=headers,
    )
    assert w1_resp.status_code == 201
    w1 = w1_resp.json()
    assert w1["domain"] == "mysite.vn"
    assert w1["base_url"] == "https://mysite.vn"
    assert w1["is_primary"] is True

    # Duplicate normalized domain -> 409
    dup = api_client.post(
        f"/api/v1/projects/{project_id}/websites",
        json={"domain": "mysite.vn", "base_url": "https://mysite.vn"},
        headers=headers,
    )
    assert dup.status_code == 409

    # Adding second website as primary automatically demotes w1
    w2_resp = api_client.post(
        f"/api/v1/projects/{project_id}/websites",
        json={
            "domain": "blog.mysite.vn",
            "base_url": "https://blog.mysite.vn",
            "is_primary": True,
        },
        headers=headers,
    )
    assert w2_resp.status_code == 201
    w2 = w2_resp.json()
    assert w2["is_primary"] is True

    websites = api_client.get(
        f"/api/v1/projects/{project_id}/websites",
        headers=headers,
    ).json()
    by_id = {w["id"]: w for w in websites}
    assert by_id[w1["id"]]["is_primary"] is False
    assert by_id[w2["id"]]["is_primary"] is True

    # Promote w1 back via PATCH
    promote_w1 = api_client.patch(
        f"/api/v1/projects/{project_id}/websites/{w1['id']}",
        json={"is_primary": True},
        headers=headers,
    )
    assert promote_w1.status_code == 200
    assert promote_w1.json()["is_primary"] is True

    # Delete w2
    del_w2 = api_client.delete(
        f"/api/v1/projects/{project_id}/websites/{w2['id']}",
        headers=headers,
    )
    assert del_w2.status_code == 204
    remaining = api_client.get(f"/api/v1/projects/{project_id}/websites", headers=headers).json()
    assert len(remaining) == 1


def test_competitors_crud_and_duplicate_conflict(
    api_client: TestClient,
    db_session: Session,
) -> None:
    _user, headers = _create_user_with_headers(db_session, "comp@example.com")
    project_id = api_client.post(
        "/api/v1/projects",
        json={"name": "Competitors Project", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()["id"]

    c1_resp = api_client.post(
        f"/api/v1/projects/{project_id}/competitors",
        json={"domain": "www.Rival.vn", "name": "Rival JSC", "notes": "Top organic competitor"},
        headers=headers,
    )
    assert c1_resp.status_code == 201
    c1 = c1_resp.json()
    assert c1["domain"] == "rival.vn"

    dup = api_client.post(
        f"/api/v1/projects/{project_id}/competitors",
        json={"domain": "https://rival.vn/pricing"},
        headers=headers,
    )
    assert dup.status_code == 409

    patch_resp = api_client.patch(
        f"/api/v1/projects/{project_id}/competitors/{c1['id']}",
        json={"name": "Rival Vietnam"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Rival Vietnam"

    listed = api_client.get(f"/api/v1/projects/{project_id}/competitors", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    del_resp = api_client.delete(
        f"/api/v1/projects/{project_id}/competitors/{c1['id']}",
        headers=headers,
    )
    assert del_resp.status_code == 204
    assert (
        api_client.get(f"/api/v1/projects/{project_id}/competitors", headers=headers).json() == []
    )
