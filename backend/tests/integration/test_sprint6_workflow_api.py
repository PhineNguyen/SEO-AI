"""PostgreSQL + FastAPI integration test for Sprint 6 LangGraph + PostgresSaver HITL workflow."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _auth_headers(client: TestClient, email: str = "sprint6@example.com") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Sprint6 User"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_sprint6_durable_postgres_hitl_workflow_start_and_3_resumes(
    api_client: TestClient,
) -> None:
    client = api_client
    headers = _auth_headers(client)
    proj = client.post(
        "/api/v1/projects",
        json={"name": "Workflow Project", "niche": "SaaS", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()
    run = client.post(
        f"/api/v1/projects/{proj['id']}/research-runs",
        json={"name": "HITL Run", "seed_keywords": [{"seed_text": "seo checklist"}]},
        headers=headers,
    ).json()
    run_id = run["id"]

    # Add 1 keyword so cleaning/clustering/prioritization have real DB rows
    kw_resp = client.post(
        f"/api/v1/research-runs/{run_id}/keywords",
        json={"keyword": "seo checklist 2026"},
        headers=headers,
    )
    assert kw_resp.status_code == 201

    # Start -> pauses at WAITING_REVIEW_1 (persisted in PostgresSaver)
    start = client.post(
        f"/api/v1/research-runs/{run_id}/workflow/start",
        json={"use_async_worker": False},
        headers=headers,
    )
    assert start.status_code == 201
    exec_data = start.json()
    exec_id = exec_data["id"]
    assert exec_data["status"] == "WAITING_REVIEW_1"

    # Resume Gate 1 -> pauses at WAITING_REVIEW_2 (reloaded from PostgreSQL checkpoint)
    r1 = client.post(
        f"/api/v1/workflows/{exec_id}/resume",
        json={"decision": "APPROVE", "comment": "Keywords look good"},
        headers=headers,
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "WAITING_REVIEW_2"

    # Resume Gate 2 -> pauses at WAITING_REVIEW_3
    r2 = client.post(
        f"/api/v1/workflows/{exec_id}/resume",
        json={"decision": "APPROVE", "comment": "Clusters verified"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "WAITING_REVIEW_3"

    # Resume Gate 3 -> COMPLETED
    r3 = client.post(
        f"/api/v1/workflows/{exec_id}/resume",
        json={"decision": "APPROVE", "comment": "Briefs ready for export"},
        headers=headers,
    )
    assert r3.status_code == 200
    final_data = r3.json()
    assert final_data["status"] == "COMPLETED"
    assert len(final_data["decisions"]) == 3
    assert len(final_data["checkpoints"]) >= 4
