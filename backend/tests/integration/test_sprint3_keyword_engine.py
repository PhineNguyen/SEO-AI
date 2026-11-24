"""PostgreSQL integration tests for Sprint 3: Research Runs, Imports, Cleaning, and Review 1."""

from collections.abc import Iterator

import pytest
from app.config import get_settings
from app.connectors import BaseDataProvider, ConnectorUpstreamError, MockDataForSeoProvider
from app.database.session import get_db
from app.main import create_app
from app.models.project import Project, ProjectSettings
from app.models.user import User
from app.schemas.provenance import KeywordIdeaRecord, ProviderResult
from app.services.keyword_service import KeywordService
from app.utils.security import create_access_token, hash_password
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


class _FailingProvider(BaseDataProvider):
    provider_code = "semrush_api"

    def check_credentials(self) -> bool:
        return True

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        raise ConnectorUpstreamError(self.provider_code, "Simulated 503 outage")

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return ProviderResult(provider_code=self.provider_code, status="ERROR")

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        raise ConnectorUpstreamError(self.provider_code, "Simulated 503 outage")


@pytest.fixture
def api_client(db_session: Session) -> Iterator[TestClient]:
    app = create_app(get_settings())

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_user_and_project(db_session: Session) -> tuple[User, Project, dict[str, str]]:
    user = User(
        email="sprint3@example.com",
        password_hash=hash_password("StrongPassword123"),
        role="member",
    )
    db_session.add(user)
    db_session.flush()
    project = Project(
        owner_id=user.id,
        name="Vietnam CRM SEO",
        niche="B2B SaaS",
        target_country="VN",
        target_language="vi",
    )
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectSettings(project_id=project.id))
    db_session.commit()
    token, _ = create_access_token(user.id, get_settings())
    return user, project, {"Authorization": f"Bearer {token}"}


def test_sprint3_end_to_end_import_clean_and_review1(
    api_client: TestClient,
    db_session: Session,
) -> None:
    user, project, headers = _seed_user_and_project(db_session)

    # 1. Create Research Run with seed keywords
    run_resp = api_client.post(
        f"/api/v1/projects/{project.id}/research-runs",
        json={
            "name": "Q4 CRM Research",
            "search_context": "B2B SME buyers in Vietnam",
            "seed_keywords": [{"seed_text": "phần mềm crm", "topic": "CRM"}],
        },
        headers=headers,
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]
    assert run_resp.json()["config_snapshot"]["default_serp_provider"] == "dataforseo"

    # 2. Multi-source provider collection with fault isolation (1 failing, 1 succeeding)
    svc = KeywordService(db_session)
    persisted, errors = svc.collect_from_providers(
        run_id=run_id,
        current_user=user,
        providers=[_FailingProvider(), MockDataForSeoProvider()],
        limit_per_seed=3,
    )
    assert persisted == 3
    assert len(errors) == 1
    assert errors[0].error_code == "CONNECTOR_UPSTREAM_ERROR"

    # 3. Upload free Google Keyword Planner CSV (includes exact dup, accent near-dup,
    #    zero-volume keyword, irrelevant keyword, and invalid symbol-only keyword)
    gkp_csv = (
        "Keyword,Currency,Avg. monthly searches,Competition (indexed value)\n"
        "Phần Mềm CRM,VND,5400,60\n"
        "phan mem crm,VND,1000,50\n"
        "từ khóa volume thấp,VND,0,-\n"
        "crm miễn phí crack,VND,800,20\n"
        "!!!123,VND,10,10\n"
    ).encode()
    imp_resp = api_client.post(
        f"/api/v1/research-runs/{run_id}/imports",
        data={"source_code": "gkp_csv"},
        files={"file": ("gkp_export.csv", gkp_csv, "text/csv")},
        headers=headers,
    )
    assert imp_resp.status_code == 201
    assert imp_resp.json()["imported_rows"] == 5

    # 4. Run non-destructive cleaning (must keep low/zero-volume keyword ACTIVE!)
    clean_resp = api_client.post(
        f"/api/v1/research-runs/{run_id}/clean",
        json={"irrelevant_terms": ["crack"]},
        headers=headers,
    )
    assert clean_resp.status_code == 200
    summary = clean_resp.json()
    assert summary["duplicate_count"] >= 1
    assert summary["near_duplicate_count"] >= 1
    assert summary["irrelevant_count"] == 1
    assert summary["invalid_count"] == 1

    # Verify zero-volume keyword was NOT deleted or dropped
    low_vol = api_client.get(
        f"/api/v1/research-runs/{run_id}/keywords?search=volume%20th%E1%BA%A5p",
        headers=headers,
    )
    assert low_vol.status_code == 200
    assert low_vol.json()["total"] == 1
    low_kw = low_vol.json()["items"][0]
    assert low_kw["cleaning_status"] == "ACTIVE"

    # 5. Review 1: manual keyword add, single review edit, and bulk approve
    manual_resp = api_client.post(
        f"/api/v1/research-runs/{run_id}/keywords",
        json={"keyword": "crm cho spa", "keyword_type": "LONG_TAIL"},
        headers=headers,
    )
    assert manual_resp.status_code == 201
    manual_kw_id = manual_resp.json()["id"]
    assert manual_resp.json()["review_status"] == "APPROVED"

    patch_resp = api_client.patch(
        f"/api/v1/keywords/{low_kw['id']}",
        json={"review_status": "APPROVED", "edited_keyword": "từ khóa volume thấp 2026"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["original_keyword"] == "từ khóa volume thấp"
    assert patch_resp.json()["normalized_keyword"] == "từ khóa volume thấp 2026"
    assert patch_resp.json()["review_status"] == "APPROVED"

    bulk_resp = api_client.post(
        f"/api/v1/research-runs/{run_id}/keywords/bulk-review",
        json={"keyword_ids": [manual_kw_id, low_kw["id"]], "review_status": "APPROVED"},
        headers=headers,
    )
    assert bulk_resp.status_code == 200
    assert bulk_resp.json()["updated_count"] == 2
