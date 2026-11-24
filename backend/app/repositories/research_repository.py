"""Repository for ResearchRun, SeedKeyword, SourceImport, Keyword, and KeywordMetric persistence."""

import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.data_source import DataSource
from app.models.research import (
    Keyword,
    KeywordMetric,
    KeywordSource,
    ResearchRun,
    SeedKeyword,
    SourceImport,
)
from app.schemas.provenance import MetricRecord


class ResearchRepository:
    """Data access layer for Sprint 3 keyword research entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_data_source_by_code(self, code: str) -> DataSource | None:
        return self.db.scalar(select(DataSource).where(DataSource.code == code))

    def get_data_source_code_map(self) -> dict[uuid.UUID, str]:
        rows = self.db.execute(select(DataSource.id, DataSource.code)).all()
        return {row[0]: row[1] for row in rows}

    def create_research_run(
        self,
        *,
        project_id: uuid.UUID,
        name: str,
        search_context: str | None,
        country_code: str,
        language_code: str,
        device: str,
        config_snapshot: dict,
        created_by: uuid.UUID,
    ) -> ResearchRun:
        run = ResearchRun(
            project_id=project_id,
            name=name,
            search_context=search_context,
            country_code=country_code,
            language_code=language_code,
            device=device,
            config_snapshot=config_snapshot,
            created_by=created_by,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def get_run_by_id(
        self,
        run_id: uuid.UUID,
        *,
        with_seeds: bool = False,
    ) -> ResearchRun | None:
        stmt = select(ResearchRun).where(ResearchRun.id == run_id)
        if with_seeds:
            stmt = stmt.options(selectinload(ResearchRun.seed_keywords))
        return self.db.scalar(stmt)

    def list_runs_for_project(self, project_id: uuid.UUID) -> list[ResearchRun]:
        stmt = (
            select(ResearchRun)
            .where(ResearchRun.project_id == project_id)
            .order_by(ResearchRun.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def add_seed_keyword(
        self,
        *,
        research_run_id: uuid.UUID,
        seed_text: str,
        topic: str | None,
    ) -> SeedKeyword:
        seed = SeedKeyword(
            research_run_id=research_run_id,
            seed_text=seed_text,
            topic=topic,
        )
        self.db.add(seed)
        self.db.flush()
        return seed

    def create_source_import(
        self,
        *,
        research_run_id: uuid.UUID,
        source_id: uuid.UUID,
        file_name: str,
        file_hash_sha256: str,
        column_mapping: dict,
        total_rows: int,
        imported_rows: int,
        error_rows: int,
        error_details: list[dict],
        status: str,
        created_by: uuid.UUID,
    ) -> SourceImport:
        record = SourceImport(
            research_run_id=research_run_id,
            source_id=source_id,
            file_name=file_name,
            file_hash_sha256=file_hash_sha256,
            column_mapping=column_mapping,
            total_rows=total_rows,
            imported_rows=imported_rows,
            error_rows=error_rows,
            error_details=error_details,
            status=status,
            created_by=created_by,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def create_keyword(
        self,
        *,
        research_run_id: uuid.UUID,
        original_keyword: str,
        normalized_keyword: str,
        language_code: str,
        keyword_type: str = "RELATED",
        cleaning_status: str = "RAW",
        review_status: str = "PENDING",
        is_manual_entry: bool = False,
    ) -> Keyword:
        kw = Keyword(
            research_run_id=research_run_id,
            original_keyword=original_keyword,
            normalized_keyword=normalized_keyword,
            language_code=language_code,
            keyword_type=keyword_type,
            cleaning_status=cleaning_status,
            review_status=review_status,
            is_manual_entry=is_manual_entry,
        )
        self.db.add(kw)
        self.db.flush()
        return kw

    def add_keyword_source(
        self,
        *,
        keyword_id: uuid.UUID,
        source_id: uuid.UUID,
        raw_keyword: str,
        source_import_id: uuid.UUID | None = None,
        source_record_id: str | None = None,
    ) -> KeywordSource:
        ks = KeywordSource(
            keyword_id=keyword_id,
            source_id=source_id,
            source_import_id=source_import_id,
            source_record_id=source_record_id,
            raw_keyword=raw_keyword,
        )
        self.db.add(ks)
        self.db.flush()
        return ks

    def add_keyword_metric(
        self,
        *,
        keyword_id: uuid.UUID,
        source_id: uuid.UUID,
        metric: MetricRecord,
    ) -> KeywordMetric:
        row = KeywordMetric(
            keyword_id=keyword_id,
            source_id=source_id,
            metric_type=metric.metric_type.value,
            numeric_value=(
                Decimal(str(metric.numeric_value)) if metric.numeric_value is not None else None
            ),
            raw_value=metric.raw_value,
            unit=metric.unit,
            currency=metric.currency,
            country_code=metric.country_code,
            language_code=metric.language_code,
            data_status=metric.data_status.value,
            collected_at=metric.collected_at,
            extra_metadata=metric.extra_metadata,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_all_keywords_for_cleaning(self, research_run_id: uuid.UUID) -> list[Keyword]:
        stmt = (
            select(Keyword)
            .where(Keyword.research_run_id == research_run_id)
            .options(selectinload(Keyword.metrics))
            .order_by(Keyword.created_at.asc(), Keyword.id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_keyword_counts(self, research_run_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(Keyword.cleaning_status, func.count(Keyword.id))
            .where(Keyword.research_run_id == research_run_id)
            .group_by(Keyword.cleaning_status)
        ).all()
        counts = {row[0]: int(row[1]) for row in rows}
        counts["TOTAL"] = sum(counts.values())
        return counts

    def list_keywords(
        self,
        research_run_id: uuid.UUID,
        *,
        cleaning_status: str | None = None,
        review_status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Keyword], int]:
        filters = [Keyword.research_run_id == research_run_id]
        if cleaning_status is not None:
            filters.append(Keyword.cleaning_status == cleaning_status)
        if review_status is not None:
            filters.append(Keyword.review_status == review_status)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    Keyword.original_keyword.ilike(pattern),
                    Keyword.normalized_keyword.ilike(pattern),
                )
            )

        total = int(
            self.db.scalar(select(func.count()).select_from(Keyword).where(*filters)) or 0
        )
        stmt = (
            select(Keyword)
            .where(*filters)
            .options(selectinload(Keyword.sources), selectinload(Keyword.metrics))
            .order_by(Keyword.created_at.asc(), Keyword.id.asc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total

    def get_keyword_by_id(self, keyword_id: uuid.UUID) -> Keyword | None:
        stmt = (
            select(Keyword)
            .where(Keyword.id == keyword_id)
            .options(selectinload(Keyword.sources), selectinload(Keyword.metrics))
        )
        return self.db.scalar(stmt)

    def get_keywords_by_ids(
        self,
        research_run_id: uuid.UUID,
        keyword_ids: list[uuid.UUID],
    ) -> list[Keyword]:
        stmt = select(Keyword).where(
            Keyword.research_run_id == research_run_id,
            Keyword.id.in_(keyword_ids),
        )
        return list(self.db.scalars(stmt).all())
