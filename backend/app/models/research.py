"""Keyword research ORM models: ResearchRun, SeedKeyword, SourceImport, Keyword, Metrics, Tags."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResearchRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single keyword research execution scoped to a project with config snapshot."""

    __tablename__ = "research_runs"
    __table_args__ = (
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_iso2"),
        CheckConstraint(
            "language_code ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'",
            name="language_code_bcp47",
        ),
        CheckConstraint("device IN ('desktop', 'mobile')", name="device_allowed"),
        CheckConstraint(
            "status IN ('DRAFT', 'RUNNING', 'WAITING_REVIEW_1', 'WAITING_REVIEW_2', "
            "'WAITING_REVIEW_3', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="status_allowed",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    search_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    device: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="desktop",
        server_default=text("'desktop'"),
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="DRAFT",
        server_default=text("'DRAFT'"),
    )
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    seed_keywords: Mapped[list["SeedKeyword"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    keywords: Mapped[list["Keyword"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    source_imports: Mapped[list["SourceImport"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SeedKeyword(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Initial seed keyword or topic provided by the user for a research run."""

    __tablename__ = "seed_keywords"
    __table_args__ = (UniqueConstraint("research_run_id", "seed_text"),)

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seed_text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)

    research_run: Mapped["ResearchRun"] = relationship(back_populates="seed_keywords")


class SourceImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Audit record for CSV/Excel file imports (GKP, Spineditor, Semrush)."""

    __tablename__ = "source_imports"
    __table_args__ = (
        CheckConstraint("status IN ('OK', 'PARTIAL', 'ERROR')", name="status_allowed"),
    )

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    column_mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    total_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    imported_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_rows: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_details: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    research_run: Mapped["ResearchRun"] = relationship(back_populates="source_imports")


class Keyword(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Discovered or imported keyword candidate with non-destructive cleaning state."""

    __tablename__ = "keywords"
    __table_args__ = (
        CheckConstraint(
            "keyword_type IN ('SEED', 'PRIMARY_CANDIDATE', 'RELATED', 'LONG_TAIL', "
            "'QUESTION', 'SUPPORTING', 'VARIATION')",
            name="keyword_type_allowed",
        ),
        CheckConstraint(
            "cleaning_status IN ('RAW', 'ACTIVE', 'DUPLICATE', 'NEAR_DUPLICATE', "
            "'IRRELEVANT', 'INVALID')",
            name="cleaning_status_allowed",
        ),
        CheckConstraint(
            "review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="review_status_allowed",
        ),
        CheckConstraint(
            "priority_tier IS NULL OR priority_tier IN ('P1', 'P2', 'P3')",
            name="priority_tier_allowed",
        ),
        Index(
            "ix_keywords_run_review_cleaning",
            "research_run_id",
            "review_status",
            "cleaning_status",
        ),
        Index(
            "uq_keywords_active_normalized_per_run",
            "research_run_id",
            "normalized_keyword",
            unique=True,
            postgresql_where=text("cleaning_status = 'ACTIVE'"),
        ),
        Index(
            "ix_keywords_normalized_trgm",
            "normalized_keyword",
            postgresql_using="gin",
            postgresql_ops={"normalized_keyword": "gin_trgm_ops"},
        ),
    )

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    keyword_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="RELATED",
        server_default=text("'RELATED'"),
    )
    cleaning_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="RAW",
        server_default=text("'RAW'"),
    )
    duplicate_of_keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    priority_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    priority_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    priority_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_manual_entry: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    research_run: Mapped["ResearchRun"] = relationship(back_populates="keywords")
    sources: Mapped[list["KeywordSource"]] = relationship(
        back_populates="keyword",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    metrics: Mapped[list["KeywordMetric"]] = relationship(
        back_populates="keyword",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tags: Mapped[list["KeywordTag"]] = relationship(
        back_populates="keyword",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class KeywordSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance join table linking a keyword to every data source that discovered it."""

    __tablename__ = "keyword_sources"

    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_imports.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    keyword: Mapped["Keyword"] = relationship(back_populates="sources")


class KeywordMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only time-series SEO metric observation with strict provenance."""

    __tablename__ = "keyword_metrics"
    __table_args__ = (
        CheckConstraint(
            "metric_type IN ('SEARCH_VOLUME', 'KEYWORD_DIFFICULTY', 'CPC', 'COMPETITION', "
            "'GSC_IMPRESSIONS', 'GSC_CLICKS', 'GSC_CTR', 'GSC_POSITION')",
            name="metric_type_allowed",
        ),
        CheckConstraint(
            "data_status IN ('AVAILABLE', 'NOT_AVAILABLE', 'NOT_COLLECTED', "
            "'SOURCE_ERROR', 'NOT_APPLICABLE')",
            name="data_status_allowed",
        ),
        CheckConstraint(
            "(data_status = 'AVAILABLE' AND numeric_value IS NOT NULL) OR "
            "(data_status <> 'AVAILABLE' AND numeric_value IS NULL)",
            name="value_matches_status",
        ),
        Index(
            "ix_keyword_metrics_kw_type_collected",
            "keyword_id",
            "metric_type",
            "collected_at",
        ),
    )

    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric_type: Mapped[str] = mapped_column(String(30), nullable=False)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    data_status: Mapped[str] = mapped_column(String(20), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    keyword: Mapped["Keyword"] = relationship(back_populates="metrics")


class KeywordTag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Flexible tag attached to a keyword by rule, AI, or human reviewer."""

    __tablename__ = "keyword_tags"
    __table_args__ = (
        UniqueConstraint("keyword_id", "tag_name"),
        CheckConstraint("tag_source IN ('AI', 'RULE', 'USER')", name="tag_source_allowed"),
    )

    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tag_source: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="RULE",
        server_default=text("'RULE'"),
    )

    keyword: Mapped["Keyword"] = relationship(back_populates="tags")
