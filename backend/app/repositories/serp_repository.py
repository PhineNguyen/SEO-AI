"""Repository for SERP snapshots, SERP results, competitor pages/headings, and keyword intents."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.connectors.safe_fetcher import CompetitorFetchResult
from app.models.serp import (
    CompetitorHeading,
    CompetitorPage,
    KeywordIntent,
    SerpResult,
    SerpSnapshot,
)
from app.schemas.provenance import SerpSnapshotRecord
from app.utils.normalization import normalize_serp_url


class SerpRepository:
    """Data access layer for SERP analysis, competitor headings, and search intents."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_competitor_page(
        self,
        *,
        url: str,
        normalized_url: str,
        domain: str,
    ) -> CompetitorPage:
        existing = self.db.scalar(
            select(CompetitorPage).where(CompetitorPage.normalized_url == normalized_url)
        )
        if existing is not None:
            return existing
        page = CompetitorPage(
            normalized_url=normalized_url,
            url=url,
            domain=domain,
            fetch_status="PENDING",
        )
        self.db.add(page)
        self.db.flush()
        return page

    def save_serp_snapshot(
        self,
        *,
        research_run_id: uuid.UUID,
        keyword_id: uuid.UUID,
        record: SerpSnapshotRecord,
    ) -> SerpSnapshot:
        """Persist an append-only SerpSnapshot and its normalized SerpResults."""
        snapshot = SerpSnapshot(
            research_run_id=research_run_id,
            keyword_id=keyword_id,
            provider_code=record.provider_code,
            query_text=record.query_text,
            country_code=record.country_code,
            language_code=record.language_code,
            location_name=record.location_name,
            device=record.device,
            serp_features=record.serp_features,
            raw_response_metadata=record.raw_metadata,
            data_status=record.data_status.value,
            collected_at=record.collected_at,
        )
        self.db.add(snapshot)
        self.db.flush()

        for res in record.results:
            norm_url = normalize_serp_url(res.url)
            page = self.get_or_create_competitor_page(
                url=res.url,
                normalized_url=norm_url,
                domain=res.domain,
            )
            self.db.add(
                SerpResult(
                    serp_snapshot_id=snapshot.id,
                    position=res.position,
                    url=res.url,
                    normalized_url=norm_url,
                    domain=res.domain,
                    title=res.title,
                    snippet=res.snippet,
                    result_type=res.result_type,
                    competitor_page_id=page.id,
                )
            )
        self.db.flush()
        return snapshot

    def get_latest_snapshot(
        self,
        research_run_id: uuid.UUID,
        keyword_id: uuid.UUID,
    ) -> SerpSnapshot | None:
        stmt = (
            select(SerpSnapshot)
            .where(
                SerpSnapshot.research_run_id == research_run_id,
                SerpSnapshot.keyword_id == keyword_id,
            )
            .options(
                selectinload(SerpSnapshot.results)
                .selectinload(SerpResult.competitor_page)
                .selectinload(CompetitorPage.headings)
            )
            .order_by(SerpSnapshot.collected_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def save_competitor_fetch(
        self,
        page: CompetitorPage,
        fetch_result: CompetitorFetchResult,
    ) -> CompetitorPage:
        """Persist parsed metadata and H1-H3 headings for a competitor page."""
        page.fetch_status = fetch_result.fetch_status
        page.http_status = fetch_result.http_status
        page.page_title = fetch_result.page_title
        page.meta_description = fetch_result.meta_description
        page.content_type_inferred = fetch_result.content_type_inferred
        page.word_count_estimate = fetch_result.word_count_estimate
        page.fetched_at = datetime.now(UTC)

        # Replace headings for this page if freshly fetched
        if fetch_result.fetch_status == "FETCHED":
            page.headings.clear()
            self.db.flush()
            for heading in fetch_result.headings:
                self.db.add(
                    CompetitorHeading(
                        competitor_page_id=page.id,
                        level=heading.level,
                        heading_text=heading.text,
                        position_order=heading.position_order,
                    )
                )
        self.db.flush()
        return page

    def save_keyword_intent(
        self,
        *,
        keyword_id: uuid.UUID,
        serp_snapshot_id: uuid.UUID | None,
        primary_intent: str,
        secondary_intent: str | None,
        confidence: float,
        reasoning: str,
        evidence: dict,
        model_version: str | None,
        prompt_version: str | None,
        origin: str = "AI",
    ) -> KeywordIntent:
        """Persist a new KeywordIntent version while preserving prior AI/Human history."""
        self.db.execute(
            update(KeywordIntent)
            .where(KeywordIntent.keyword_id == keyword_id, KeywordIntent.is_current.is_(True))
            .values(is_current=False)
        )
        intent = KeywordIntent(
            keyword_id=keyword_id,
            serp_snapshot_id=serp_snapshot_id,
            primary_intent=primary_intent,
            secondary_intent=secondary_intent,
            confidence=Decimal(f"{confidence:.3f}"),
            reasoning=reasoning,
            evidence=evidence,
            model_version=model_version,
            prompt_version=prompt_version,
            origin=origin,
            is_current=True,
        )
        self.db.add(intent)
        self.db.flush()
        return intent

    def get_current_intent(self, keyword_id: uuid.UUID) -> KeywordIntent | None:
        return self.db.scalar(
            select(KeywordIntent).where(
                KeywordIntent.keyword_id == keyword_id,
                KeywordIntent.is_current.is_(True),
            )
        )
