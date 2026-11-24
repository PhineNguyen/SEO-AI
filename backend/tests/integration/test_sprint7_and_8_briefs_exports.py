"""PostgreSQL + FastAPI integration tests for Sprint 7 Content Briefs & Sprint 8 Exports."""

from io import BytesIO
from pathlib import Path

import httpx
import pytest
import respx
from app.config import get_settings
from app.models.brief import ContentBrief
from app.models.oauth_credential import OAuthCredential
from app.models.user import User
from app.services.export_service import EXPORT_SHEET_NAMES, ExportService
from app.utils.security import TokenEncryptor
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _auth_headers(client: TestClient, email: str = "sprint78@example.com") -> dict[str, str]:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "Sprint78 User"},
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_sprint7_brief_versioning_and_sprint8_excel_and_sheets_export(
    api_client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    client = api_client
    headers = _auth_headers(client)
    proj = client.post(
        "/api/v1/projects",
        json={"name": "Export Demo", "niche": "SaaS", "target_country": "VN", "target_language": "vi"},
        headers=headers,
    ).json()
    run = client.post(
        f"/api/v1/projects/{proj['id']}/research-runs",
        json={"name": "Full Pipeline Run", "seed_keywords": [{"seed_text": "crm software"}]},
        headers=headers,
    ).json()
    run_id = run["id"]

    client.post(
        f"/api/v1/research-runs/{run_id}/keywords",
        json={"keyword": "crm software for startups"},
        headers=headers,
    )
    client.post(
        f"/api/v1/research-runs/{run_id}/clusters/run",
        json={"distance_threshold": 0.45},
        headers=headers,
    )
    client.post(f"/api/v1/research-runs/{run_id}/prioritize", headers=headers)

    # 1. Generate AI Content Brief (v1)
    gen = client.post(f"/api/v1/research-runs/{run_id}/briefs/generate", headers=headers)
    assert gen.status_code == 201
    briefs = gen.json()
    assert len(briefs) == 1
    v1 = briefs[0]
    assert v1["version"] == 1
    assert v1["origin"] == "AI"

    # 2. Review 3: Human edit creates v2 while preserving AI v1 baseline
    edited = client.patch(
        f"/api/v1/briefs/{v1['id']}",
        json={
            "suggested_seo_title": "CRM Software For Startups — 2026 Buyer Guide",
            "feedback_notes": "Tightened SEO title",
        },
        headers=headers,
    )
    assert edited.status_code == 200
    v2 = edited.json()
    assert v2["version"] == 2
    assert v2["origin"] == "HUMAN"
    assert v2["is_current"] is True

    # Verify v1 AI baseline still exists in DB with is_current=False
    all_versions = list(
        db_session.scalars(
            select(ContentBrief)
            .where(ContentBrief.cluster_id == v1["cluster_id"])
            .order_by(ContentBrief.version.asc())
        ).all()
    )
    assert len(all_versions) == 2
    assert all_versions[0].origin == "AI" and all_versions[0].is_current is False
    assert all_versions[1].origin == "HUMAN" and all_versions[1].is_current is True

    # Approve v2
    approved = client.post(
        f"/api/v1/briefs/{v2['id']}/approve",
        json={"feedback_notes": "Ready to publish"},
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    # 3. Sprint 8 TASK-028: Excel 7-sheet export via API
    xlsx_resp = client.post(
        f"/api/v1/research-runs/{run_id}/exports/excel", headers=headers
    )
    assert xlsx_resp.status_code == 200
    assert "X-Export-Job-Id" in xlsx_resp.headers
    wb = load_workbook(BytesIO(xlsx_resp.content))
    assert tuple(wb.sheetnames) == EXPORT_SHEET_NAMES
    assert wb["Content Brief"].max_row >= 2
    assert wb["All Keywords"].max_row >= 2

    # 4. Sprint 8 TASK-029: Google Sheets export fails cleanly without OAuth, succeeds when connected (mocked)
    no_oauth = client.post(
        f"/api/v1/research-runs/{run_id}/exports/google-sheets", headers=headers
    )
    assert no_oauth.status_code == 403

    user = db_session.scalar(select(User).where(User.email == "sprint78@example.com"))
    assert user is not None
    enc = TokenEncryptor(get_settings().OAUTH_TOKEN_ENCRYPTION_KEY.get_secret_value())
    db_session.add(
        OAuthCredential(
            user_id=user.id,
            provider="google_sheets",
            account_email="sprint78@example.com",
            encrypted_access_token=enc.encrypt("mock-sheets-access-token"),
            encrypted_refresh_token=enc.encrypt("mock-sheets-refresh-token"),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
    )
    db_session.commit()

    with respx.mock(assert_all_called=True) as mock_router:
        mock_router.post("https://sheets.googleapis.com/v4/spreadsheets").mock(
            return_value=httpx.Response(
                200,
                json={
                    "spreadsheetId": "sheet_12345",
                    "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/sheet_12345",
                },
            )
        )
        mock_router.post(
            "https://sheets.googleapis.com/v4/spreadsheets/sheet_12345/values:batchUpdate"
        ).mock(return_value=httpx.Response(200, json={"totalUpdatedSheets": 7}))

        with httpx.Client() as mock_client:
            gs_job = ExportService(db_session, export_dir=tmp_path).export_google_sheets(
                run["id"], user.id, http_client=mock_client
            )
            assert gs_job.status == "COMPLETED"
            assert gs_job.google_spreadsheet_id == "sheet_12345"
