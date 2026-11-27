"""One-Click Auto Pipeline & Free Google Suggest Discovery Service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.google_suggest import GoogleSuggestConnector
from app.models.data_source import DataSource
from app.models.research import Keyword, KeywordSource, ResearchRun
from app.models.serp import KeywordIntent
from app.models.user import User
from app.schemas.research import CleaningRequest
from app.services.brief_service import ContentBriefService
from app.services.cleaning_service import normalize_keyword_text
from app.services.clustering_service import ClusteringService
from app.services.intent_service import HeuristicIntentClassifier
from app.services.keyword_service import KeywordService, ResearchRunNotFoundError
from app.services.prioritization_service import PrioritizationService
from app.services.project_service import ProjectNotFoundError


class AutoPipelineService:
    """Provides 1-click Google Suggest discovery and end-to-end auto-research execution."""

    def __init__(
        self,
        db: Session,
        suggest_connector: GoogleSuggestConnector | None = None,
    ) -> None:
        self._db = db
        self._suggest = suggest_connector or GoogleSuggestConnector()

    def _get_or_create_suggest_source(self) -> DataSource:
        ds = self._db.scalar(select(DataSource).where(DataSource.code == "google_suggest"))
        if ds is None:
            ds = DataSource(
                code="google_suggest",
                name="Google Autocomplete (Free)",
                source_type="API",
                is_active=True,
            )
            self._db.add(ds)
            self._db.flush()
        return ds

    def _authorize_run(self, run_id: UUID, current_user: User) -> ResearchRun:
        kw_service = KeywordService(self._db)
        try:
            return kw_service._authorize_run(run_id, current_user)
        except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
            ) from exc

    def discover_google_suggest(
        self,
        run_id: UUID,
        current_user: User,
        *,
        seed_keyword: str,
        expand_modifiers: bool = True,
        max_keywords: int = 40,
    ) -> dict[str, Any]:
        """Fetch real Google Autocomplete suggestions and persist them with provenance."""
        run = self._authorize_run(run_id, current_user)
        result = self._suggest.get_keyword_ideas(
            seed_keyword,
            country_code=run.country_code,
            language_code=run.language_code,
            limit=max_keywords,
            expand_modifiers=expand_modifiers,
        )

        source = self._get_or_create_suggest_source()
        existing_norm = {
            row
            for row in self._db.scalars(
                select(Keyword.normalized_keyword).where(Keyword.research_run_id == run.id)
            ).all()
        }

        inserted_keywords: list[str] = []
        # Always include the seed itself if not present
        candidates = [seed_keyword.strip(), *[item.original_keyword for item in result.items]]
        for raw_kw in candidates:
            if not raw_kw:
                continue
            norm = normalize_keyword_text(raw_kw)
            if not norm or norm in existing_norm:
                continue
            existing_norm.add(norm)
            kw = Keyword(
                research_run_id=run.id,
                original_keyword=raw_kw,
                normalized_keyword=norm,
                language_code=run.language_code,
                keyword_type="SEED" if raw_kw.lower() == seed_keyword.strip().lower() else "RELATED",
                cleaning_status="RAW",
                review_status="PENDING",
                is_manual_entry=False,
            )
            self._db.add(kw)
            self._db.flush()
            self._db.add(
                KeywordSource(
                    keyword_id=kw.id,
                    source_id=source.id,
                    raw_keyword=raw_kw,
                )
            )
            inserted_keywords.append(raw_kw)

        self._db.commit()
        return {
            "research_run_id": str(run.id),
            "seed_keyword": seed_keyword.strip(),
            "discovered_count": len(result.items),
            "inserted_count": len(inserted_keywords),
            "keywords": inserted_keywords,
            "errors": [e.message for e in result.errors],
        }

    def run_all_pipeline(
        self,
        run_id: UUID,
        current_user: User,
        *,
        seed_keyword: str | None = None,
        expand_modifiers: bool = True,
        max_keywords: int = 40,
        distance_threshold: float = 0.45,
    ) -> dict[str, Any]:
        """Run Discover (optional) -> Clean -> Heuristic Intent -> Cluster -> Prioritize -> Briefs."""
        run = self._authorize_run(run_id, current_user)
        discovered_count = 0
        inserted_count = 0

        if seed_keyword and seed_keyword.strip():
            disc = self.discover_google_suggest(
                run.id,
                current_user,
                seed_keyword=seed_keyword.strip(),
                expand_modifiers=expand_modifiers,
                max_keywords=max_keywords,
            )
            discovered_count = disc["discovered_count"]
            inserted_count = disc["inserted_count"]

        # 1. Non-destructive cleaning
        clean_summary = KeywordService(self._db).run_cleaning(
            run.id, current_user, CleaningRequest()
        )

        # 2. Fast heuristic intent classification for active keywords missing current intent
        active_kws = list(
            self._db.scalars(
                select(Keyword).where(
                    Keyword.research_run_id == run.id,
                    Keyword.cleaning_status.in_(("ACTIVE", "RAW")),
                )
            ).all()
        )
        kw_ids = [k.id for k in active_kws]
        already_classified = set(
            self._db.scalars(
                select(KeywordIntent.keyword_id).where(
                    KeywordIntent.keyword_id.in_(kw_ids),
                    KeywordIntent.is_current.is_(True),
                )
            ).all()
        ) if kw_ids else set()

        classifier = HeuristicIntentClassifier()
        intents_classified = 0
        for kw in active_kws:
            if kw.id in already_classified:
                continue
            pred = classifier.classify(
                keyword=kw.original_keyword,
                country_code=run.country_code,
                language_code=run.language_code,
                serp_features=[],
                serp_results=[],
            )
            self._db.add(
                KeywordIntent(
                    keyword_id=kw.id,
                    serp_snapshot_id=None,
                    primary_intent=str(pred.primary_intent),
                    secondary_intent=str(pred.secondary_intent) if pred.secondary_intent else None,
                    confidence=pred.confidence,
                    reasoning=pred.reasoning,
                    evidence=[],
                    model_version="heuristic-v1",
                    prompt_version="heuristic-v1",
                    origin="AI",
                    is_current=True,
                )
            )
            intents_classified += 1
        self._db.commit()

        # 3. Hybrid Clustering
        clusters = ClusteringService(self._db).run_clustering(
            run.id,
            current_user.id,
            distance_threshold=distance_threshold,
            include_pending_keywords=True,
        )

        # 4. Prioritization
        scored_count, _, _ = PrioritizationService(self._db).prioritize_run(
            run.id, current_user.id
        )

        # 5. Evidence-based Content Briefs
        briefs = ContentBriefService(self._db).generate_briefs_for_run(
            run.id, current_user.id
        )

        return {
            "research_run_id": str(run.id),
            "discovered_count": discovered_count,
            "inserted_count": inserted_count,
            "active_keywords": clean_summary.active_count,
            "duplicate_keywords": clean_summary.duplicate_count + clean_summary.near_duplicate_count,
            "intents_classified": intents_classified,
            "clusters_created": len(clusters),
            "prioritized_keywords": scored_count,
            "briefs_generated": len(briefs),
        }
