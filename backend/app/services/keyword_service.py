"""Application service for Research Runs, multi-source keyword collection, imports, and Review 1."""

import uuid
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.base import BaseDataProvider
from app.connectors.exceptions import ConnectorError
from app.connectors.gkp import GoogleKeywordPlannerImporter
from app.connectors.semrush import SemrushFileImporter
from app.connectors.spineditor import SpineditorFileImporter
from app.models.research import Keyword, ResearchRun, SourceImport
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.repositories.research_repository import ResearchRepository
from app.schemas.provenance import (
    KeywordIdeaRecord,
    ProviderErrorRecord,
    ProviderResult,
)
from app.schemas.research import (
    BulkKeywordReviewRequest,
    CleaningRequest,
    CleaningSummary,
    KeywordMetricItem,
    KeywordResponse,
    KeywordReviewUpdate,
    ManualKeywordCreate,
    ResearchRunCreate,
)
from app.services.cleaning_service import KeywordCleaningService, normalize_keyword_text
from app.services.project_service import DuplicateResourceError, ProjectNotFoundError

ImportSourceCode = Literal["gkp_csv", "spineditor_import", "semrush_csv"]


class ResearchRunNotFoundError(Exception):
    """Raised when a research run does not exist or is not accessible to the caller."""


class KeywordNotFoundError(Exception):
    """Raised when a keyword does not exist or is not accessible to the caller."""


class UnsupportedImportSourceError(Exception):
    """Raised when an unsupported import source_code is requested."""


class KeywordService:
    """Orchestrates Research Runs, multi-source keyword collection, file imports, and Review 1."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.projects = ProjectRepository(db)
        self.repo = ResearchRepository(db)
        self.cleaner = KeywordCleaningService(db)

    def _authorize_project(self, project_id: uuid.UUID, current_user: User):
        project = self.projects.get_by_id(project_id, with_relations=True)
        if project is None:
            raise ProjectNotFoundError("Project not found")
        if project.owner_id != current_user.id and current_user.role != "admin":
            raise ProjectNotFoundError("Project not found")
        return project

    def _authorize_run(
        self,
        run_id: uuid.UUID,
        current_user: User,
        *,
        with_seeds: bool = False,
    ) -> ResearchRun:
        run = self.repo.get_run_by_id(run_id, with_seeds=with_seeds)
        if run is None:
            raise ResearchRunNotFoundError("Research run not found")
        self._authorize_project(run.project_id, current_user)
        return run

    def create_research_run(
        self,
        project_id: uuid.UUID,
        current_user: User,
        payload: ResearchRunCreate,
    ) -> ResearchRun:
        """Create a Research Run snapshotting project settings and persisting seed keywords."""
        project = self._authorize_project(project_id, current_user)
        settings = project.settings

        config_snapshot = {
            "clustering_weights": settings.clustering_weights if settings else {},
            "prioritization_weights": settings.prioritization_weights if settings else {},
            "default_serp_provider": settings.default_serp_provider if settings else "dataforseo",
            "default_device": settings.default_device if settings else "desktop",
            "custom_rules": settings.custom_rules if settings else {},
        }

        country_code = payload.country_code or project.target_country
        language_code = payload.language_code or project.target_language
        device = payload.device or (settings.default_device if settings else "desktop")

        run = self.repo.create_research_run(
            project_id=project.id,
            name=payload.name,
            search_context=payload.search_context,
            country_code=country_code,
            language_code=language_code,
            device=device,
            config_snapshot=config_snapshot,
            created_by=current_user.id,
        )

        manual_source = self.repo.get_data_source_by_code("manual")
        seen_seeds: set[str] = set()
        for seed in payload.seed_keywords:
            if seed.seed_text.lower() in seen_seeds:
                continue
            seen_seeds.add(seed.seed_text.lower())
            self.repo.add_seed_keyword(
                research_run_id=run.id,
                seed_text=seed.seed_text,
                topic=seed.topic,
            )
            kw = self.repo.create_keyword(
                research_run_id=run.id,
                original_keyword=seed.seed_text,
                normalized_keyword=normalize_keyword_text(seed.seed_text),
                language_code=language_code,
                keyword_type="SEED",
                cleaning_status="RAW",
                review_status="PENDING",
                is_manual_entry=True,
            )
            if manual_source is not None:
                self.repo.add_keyword_source(
                    keyword_id=kw.id,
                    source_id=manual_source.id,
                    raw_keyword=seed.seed_text,
                )

        self.db.commit()
        loaded = self.repo.get_run_by_id(run.id, with_seeds=True)
        assert loaded is not None
        return loaded

    def list_research_runs(self, project_id: uuid.UUID, current_user: User) -> list[ResearchRun]:
        self._authorize_project(project_id, current_user)
        return self.repo.list_runs_for_project(project_id)

    def get_research_run_detail(
        self,
        run_id: uuid.UUID,
        current_user: User,
    ) -> tuple[ResearchRun, dict[str, int]]:
        run = self._authorize_run(run_id, current_user, with_seeds=True)
        counts = self.repo.get_keyword_counts(run.id)
        return run, counts

    def persist_keyword_ideas(
        self,
        research_run_id: uuid.UUID,
        ideas: list[KeywordIdeaRecord],
        *,
        source_import_id: uuid.UUID | None = None,
    ) -> int:
        """Persist KeywordIdeaRecords, provenance sources, and append-only metrics."""
        source_cache: dict[str, uuid.UUID] = {}
        persisted = 0

        for idea in ideas:
            source_id = source_cache.get(idea.source_code)
            if source_id is None:
                ds = self.repo.get_data_source_by_code(idea.source_code)
                if ds is None:
                    raise UnsupportedImportSourceError(
                        f"Unknown data_source code: '{idea.source_code}'"
                    )
                source_id = ds.id
                source_cache[idea.source_code] = source_id

            kw = self.repo.create_keyword(
                research_run_id=research_run_id,
                original_keyword=idea.original_keyword,
                normalized_keyword=normalize_keyword_text(idea.original_keyword),
                language_code=idea.language_code,
                keyword_type=idea.keyword_type.value,
                cleaning_status="RAW",
                review_status="PENDING",
            )
            self.repo.add_keyword_source(
                keyword_id=kw.id,
                source_id=source_id,
                raw_keyword=idea.original_keyword,
                source_import_id=source_import_id,
                source_record_id=idea.source_record_id,
            )
            for metric in idea.metrics:
                metric_source_id = source_cache.get(metric.source_code)
                if metric_source_id is None:
                    mds = self.repo.get_data_source_by_code(metric.source_code)
                    metric_source_id = mds.id if mds is not None else source_id
                    source_cache[metric.source_code] = metric_source_id
                self.repo.add_keyword_metric(
                    keyword_id=kw.id,
                    source_id=metric_source_id,
                    metric=metric,
                )
            persisted += 1

        return persisted

    def collect_from_providers(
        self,
        run_id: uuid.UUID,
        current_user: User,
        *,
        providers: list[BaseDataProvider],
        limit_per_seed: int = 50,
    ) -> tuple[int, list[ProviderErrorRecord]]:
        """Run keyword discovery across multiple providers with strict fault isolation."""
        run = self._authorize_run(run_id, current_user, with_seeds=True)
        total_persisted = 0
        errors: list[ProviderErrorRecord] = []

        for provider in providers:
            if not provider.supports_keyword_ideas:
                continue
            for seed in run.seed_keywords:
                try:
                    result: ProviderResult[KeywordIdeaRecord] = provider.get_keyword_ideas(
                        seed.seed_text,
                        country_code=run.country_code,
                        language_code=run.language_code,
                        limit=limit_per_seed,
                    )
                except ConnectorError as exc:
                    errors.append(
                        exc.to_error_record(
                            context={"seed_text": seed.seed_text, "run_id": str(run.id)}
                        )
                    )
                    continue

                if result.errors:
                    errors.extend(result.errors)
                if result.items:
                    total_persisted += self.persist_keyword_ideas(run.id, result.items)

        self.db.commit()
        return total_persisted, errors

    def import_keyword_file(
        self,
        run_id: uuid.UUID,
        current_user: User,
        *,
        source_code: ImportSourceCode,
        file_name: str,
        content: bytes,
        column_mapping: dict[str, str] | None = None,
    ) -> SourceImport:
        """Import keywords from GKP, Spineditor, or Semrush CSV/XLSX files."""
        run = self._authorize_run(run_id, current_user)
        ds = self.repo.get_data_source_by_code(source_code)
        if ds is None:
            raise UnsupportedImportSourceError(f"Unsupported import source: {source_code}")

        if source_code == "gkp_csv":
            importer = GoogleKeywordPlannerImporter()
        elif source_code == "spineditor_import":
            importer = SpineditorFileImporter()
        elif source_code == "semrush_csv":
            importer = SemrushFileImporter()
        else:
            raise UnsupportedImportSourceError(f"Unsupported import source: {source_code}")

        report = importer.import_bytes(
            content,
            file_name=file_name,
            country_code=run.country_code,
            language_code=run.language_code,
            column_mapping=column_mapping,
        )

        source_import = self.repo.create_source_import(
            research_run_id=run.id,
            source_id=ds.id,
            file_name=report.file_name,
            file_hash_sha256=report.file_hash_sha256,
            column_mapping=report.column_mapping,
            total_rows=report.total_rows,
            imported_rows=report.imported_rows,
            error_rows=report.error_rows,
            error_details=report.error_details,
            status=report.result.status,
            created_by=current_user.id,
        )
        if report.result.items:
            self.persist_keyword_ideas(
                run.id,
                report.result.items,
                source_import_id=source_import.id,
            )
        self.db.commit()
        self.db.refresh(source_import)
        return source_import

    def run_cleaning(
        self,
        run_id: uuid.UUID,
        current_user: User,
        payload: CleaningRequest,
    ) -> CleaningSummary:
        """Execute non-destructive cleaning for a research run."""
        run = self._authorize_run(run_id, current_user)
        custom_rules = run.config_snapshot.get("custom_rules") or {}
        configured_negatives = custom_rules.get("negative_keywords") or []
        combined_negatives = list({*configured_negatives, *payload.irrelevant_terms})

        summary = self.cleaner.clean_research_run(
            run.id,
            irrelevant_terms=combined_negatives,
            near_duplicate_threshold=payload.near_duplicate_threshold,
        )
        run.status = "WAITING_REVIEW_1"
        self.db.commit()
        return summary

    def _serialize_keyword(
        self,
        kw: Keyword,
        source_map: dict[uuid.UUID, str],
    ) -> KeywordResponse:
        # Aggregate latest metric per (metric_type, source_code)
        latest_by_key: dict[tuple[str, str], KeywordMetricItem] = {}
        sorted_metrics = sorted(kw.metrics, key=lambda m: m.collected_at)
        for m in sorted_metrics:
            src_code = source_map.get(m.source_id, str(m.source_id))
            latest_by_key[(m.metric_type, src_code)] = KeywordMetricItem(
                metric_type=m.metric_type,
                source_code=src_code,
                numeric_value=float(m.numeric_value) if m.numeric_value is not None else None,
                raw_value=m.raw_value,
                unit=m.unit,
                currency=m.currency,
                data_status=m.data_status,
                collected_at=m.collected_at,
            )

        sources = sorted({source_map.get(s.source_id, str(s.source_id)) for s in kw.sources})
        return KeywordResponse(
            id=kw.id,
            research_run_id=kw.research_run_id,
            original_keyword=kw.original_keyword,
            normalized_keyword=kw.normalized_keyword,
            language_code=kw.language_code,
            keyword_type=kw.keyword_type,
            cleaning_status=kw.cleaning_status,
            duplicate_of_keyword_id=kw.duplicate_of_keyword_id,
            review_status=kw.review_status,
            priority_score=float(kw.priority_score) if kw.priority_score is not None else None,
            priority_tier=kw.priority_tier,
            priority_reasoning=kw.priority_reasoning,
            is_manual_entry=kw.is_manual_entry,
            sources=sources,
            metrics=list(latest_by_key.values()),
            created_at=kw.created_at,
            updated_at=kw.updated_at,
        )

    def list_keywords(
        self,
        run_id: uuid.UUID,
        current_user: User,
        *,
        cleaning_status: str | None = None,
        review_status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[KeywordResponse], int]:
        self._authorize_run(run_id, current_user)
        source_map = self.repo.get_data_source_code_map()
        rows, total = self.repo.list_keywords(
            run_id,
            cleaning_status=cleaning_status,
            review_status=review_status,
            search=search,
            limit=limit,
            offset=offset,
        )
        return [self._serialize_keyword(kw, source_map) for kw in rows], total

    def add_manual_keyword(
        self,
        run_id: uuid.UUID,
        current_user: User,
        payload: ManualKeywordCreate,
    ) -> KeywordResponse:
        """Manually add an approved ACTIVE keyword to a research run."""
        run = self._authorize_run(run_id, current_user)
        normalized = normalize_keyword_text(payload.keyword)
        manual_source = self.repo.get_data_source_by_code("manual")

        try:
            kw = self.repo.create_keyword(
                research_run_id=run.id,
                original_keyword=payload.keyword,
                normalized_keyword=normalized,
                language_code=run.language_code,
                keyword_type=payload.keyword_type,
                cleaning_status="ACTIVE",
                review_status="APPROVED",
                is_manual_entry=True,
            )
            if manual_source is not None:
                self.repo.add_keyword_source(
                    keyword_id=kw.id,
                    source_id=manual_source.id,
                    raw_keyword=payload.keyword,
                )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError(
                f"Active keyword '{normalized}' already exists in this research run"
            ) from exc

        loaded = self.repo.get_keyword_by_id(kw.id)
        assert loaded is not None
        return self._serialize_keyword(loaded, self.repo.get_data_source_code_map())

    def review_keyword(
        self,
        keyword_id: uuid.UUID,
        current_user: User,
        payload: KeywordReviewUpdate,
    ) -> KeywordResponse:
        """Apply Review 1 edits (approve/reject/edit/mark irrelevant) preserving original_keyword."""
        kw = self.repo.get_keyword_by_id(keyword_id)
        if kw is None:
            raise KeywordNotFoundError("Keyword not found")
        self._authorize_run(kw.research_run_id, current_user)

        if payload.review_status is not None:
            kw.review_status = payload.review_status
        if payload.cleaning_status is not None:
            kw.cleaning_status = payload.cleaning_status
        if payload.keyword_type is not None:
            kw.keyword_type = payload.keyword_type
        if payload.edited_keyword is not None:
            kw.normalized_keyword = normalize_keyword_text(payload.edited_keyword)

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateResourceError(
                "Another active keyword with that normalized text already exists"
            ) from exc

        loaded = self.repo.get_keyword_by_id(kw.id)
        assert loaded is not None
        return self._serialize_keyword(loaded, self.repo.get_data_source_code_map())

    def bulk_review_keywords(
        self,
        run_id: uuid.UUID,
        current_user: User,
        payload: BulkKeywordReviewRequest,
    ) -> int:
        """Bulk update Review 1 statuses for selected keywords within a run."""
        self._authorize_run(run_id, current_user)
        targets = self.repo.get_keywords_by_ids(run_id, payload.keyword_ids)
        for kw in targets:
            if payload.review_status is not None:
                kw.review_status = payload.review_status
            if payload.cleaning_status is not None:
                kw.cleaning_status = payload.cleaning_status
        self.db.commit()
        return len(targets)
