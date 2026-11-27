"""PostgreSQL integration tests for Google Suggest Discovery & 1-Click Auto Pipeline."""

import httpx
import pytest
import respx
from app.connectors.google_suggest import GOOGLE_SUGGEST_URL, GoogleSuggestConnector
from app.models.user import User
from app.services.auto_pipeline_service import AutoPipelineService
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def test_one_click_run_all_pipeline_end_to_end(
    api_client: TestClient, db_session: Session
) -> None:
    api_client.post(
        "/api/v1/auth/register",
        json={"email": "autopipe@example.com", "password": "Password123!", "full_name": "Auto"},
    )
    token = api_client.post(
        "/api/v1/auth/login",
        json={"email": "autopipe@example.com", "password": "Password123!"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj = api_client.post(
        "/api/v1/projects",
        json={"name": "Auto Pipe", "niche": "SaaS", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()
    run = api_client.post(
        f"/api/v1/projects/{proj['id']}/research-runs",
        json={"name": "One Click Run", "seed_keywords": []},
        headers=headers,
    ).json()

    user = db_session.scalar(select(User).where(User.email == "autopipe@example.com"))
    assert user is not None

    with respx.mock() as mock_router:
        mock_router.get(GOOGLE_SUGGEST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    "phan mem crm",
                    [
                        "phan mem crm tot nhat",
                        "gia phan mem crm",
                        "phan mem crm la gi",
                    ],
                ],
            )
        )
        with httpx.Client() as mock_http:
            summary = AutoPipelineService(
                db_session, suggest_connector=GoogleSuggestConnector(http_client=mock_http)
            ).run_all_pipeline(
                run["id"],
                user,
                seed_keyword="phan mem crm",
                expand_modifiers=False,
            )
            assert summary["discovered_count"] == 3
            assert summary["inserted_count"] == 4
            assert summary["active_keywords"] >= 3
            assert summary["intents_classified"] >= 3
            assert summary["clusters_created"] >= 1
            assert summary["briefs_generated"] >= 1
