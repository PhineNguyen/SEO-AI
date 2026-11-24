"""PostgreSQL integration tests for Sprint 4: SERP collection, headings, and Search Intent."""

import socket

import httpx
import pytest
import respx
from app.connectors import MockDataForSeoProvider
from app.connectors.safe_fetcher import SafeCompetitorFetcher
from app.models.project import Project, ProjectSettings
from app.models.research import Keyword, ResearchRun
from app.models.serp import KeywordIntent, SerpSnapshot
from app.models.user import User
from app.repositories.serp_repository import SerpRepository
from app.services.intent_service import HeuristicIntentClassifier, IntentService
from app.services.serp_service import SerpService
from app.utils.security import hash_password
from sqlalchemy import select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _fake_public_dns(_host: str, _port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


@respx.mock
def test_serp_collection_heading_fetch_and_versioned_intent(db_session: Session) -> None:
    user = User(email="sprint4@example.com", password_hash=hash_password("Password123!"))
    db_session.add(user)
    db_session.flush()

    project = Project(
        owner_id=user.id,
        name="SERP Test Project",
        target_country="VN",
        target_language="vi",
    )
    db_session.add(project)
    db_session.flush()
    db_session.add(ProjectSettings(project_id=project.id))

    run = ResearchRun(
        project_id=project.id,
        name="SERP Run 1",
        country_code="VN",
        language_code="vi",
        device="desktop",
        created_by=user.id,
    )
    db_session.add(run)
    db_session.flush()

    kw = Keyword(
        research_run_id=run.id,
        original_keyword="crm là gì",
        normalized_keyword="crm là gì",
        language_code="vi",
        cleaning_status="ACTIVE",
        review_status="APPROVED",
    )
    db_session.add(kw)
    db_session.commit()

    # 1. Collect SERP snapshot append-only twice (verifying history is not overwritten)
    serp_service = SerpService(db_session)
    mock_provider = MockDataForSeoProvider()
    snaps1, errors1 = serp_service.collect_serp_for_keywords(
        run,
        [kw],
        provider=mock_provider,
        depth=3,
    )
    assert errors1 == []
    assert len(snaps1) == 1

    snaps2, _ = serp_service.collect_serp_for_keywords(
        run,
        [kw],
        provider=mock_provider,
        depth=3,
    )
    all_snaps = list(
        db_session.scalars(select(SerpSnapshot).where(SerpSnapshot.keyword_id == kw.id)).all()
    )
    assert len(all_snaps) == 2

    # 2. Fetch headings for Top-3 competitor pages with SSRF-safe fetcher
    latest = SerpRepository(db_session).get_latest_snapshot(run.id, kw.id)
    assert latest is not None
    for res in latest.results:
        respx.get(res.url).mock(
            return_value=httpx.Response(
                200,
                text="<html><head><title>CRM là gì</title></head>"
                "<body><h1>CRM là gì?</h1><h2>Lợi ích CRM</h2></body></html>",
            )
        )

    fetcher = SafeCompetitorFetcher(dns_resolver=_fake_public_dns)
    fetched_pages = serp_service.fetch_headings_for_snapshot(latest, fetcher=fetcher, max_pages=3)
    assert len(fetched_pages) == 3
    assert all(p.fetch_status == "FETCHED" for p in fetched_pages)

    # 3. Classify Search Intent twice and confirm history preservation (is_current)
    latest_reloaded = SerpRepository(db_session).get_latest_snapshot(run.id, kw.id)
    intent_service = IntentService(db_session)
    classifier = HeuristicIntentClassifier()

    intent1 = intent_service.classify_and_save(
        keyword=kw,
        serp_snapshot=latest_reloaded,
        classifier=classifier,
        country_code="VN",
        language_code="vi",
    )
    assert intent1.primary_intent == "INFORMATIONAL"
    assert intent1.is_current is True
    assert len(intent1.evidence["evidence_urls"]) > 0

    intent2 = intent_service.classify_and_save(
        keyword=kw,
        serp_snapshot=latest_reloaded,
        classifier=classifier,
        country_code="VN",
        language_code="vi",
    )
    all_intents = list(
        db_session.scalars(select(KeywordIntent).where(KeywordIntent.keyword_id == kw.id)).all()
    )
    assert len(all_intents) == 2
    assert sum(1 for i in all_intents if i.is_current) == 1
    assert intent2.is_current is True
