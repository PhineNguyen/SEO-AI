"""SERP Analysis, Competitor Content, and Search Intent ORM models."""

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
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CompetitorPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Deduplicated competitor webpage fetched with SSRF protection for heading analysis."""

    __tablename__ = "competitor_pages"
    __table_args__ = (
        CheckConstraint(
            "fetch_status IN ('PENDING', 'FETCHED', 'BLOCKED_ROBOTS', 'BLOCKED_SSRF', 'TIMEOUT', 'ERROR')",
            name="fetch_status_allowed",
        ),
    )

    normalized_url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetch_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )
    page_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type_inferred: Mapped[str | None] = mapped_column(String(50), nullable=True)
    word_count_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    headings: Mapped[list["CompetitorHeading"]] = relationship(
        back_populates="competitor_page",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CompetitorHeading(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Extracted H1-H6 heading structure for a fetched competitor page."""

    __tablename__ = "competitor_headings"
    __table_args__ = (
        CheckConstraint("level >= 1 AND level <= 6", name="level_range"),
    )

    competitor_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    heading_text: Mapped[str] = mapped_column(Text, nullable=False)
    position_order: Mapped[int] = mapped_column(Integer, nullable=False)

    competitor_page: Mapped["CompetitorPage"] = relationship(back_populates="headings")


class SerpSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only SERP snapshot bound to country, language, device, and timestamp."""

    __tablename__ = "serp_snapshots"
    __table_args__ = (
        CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="country_code_iso2"),
        CheckConstraint("device IN ('desktop', 'mobile')", name="device_allowed"),
        CheckConstraint(
            "data_status IN ('AVAILABLE', 'NOT_AVAILABLE', 'NOT_COLLECTED', 'SOURCE_ERROR', 'NOT_APPLICABLE')",
            name="data_status_allowed",
        ),
        Index(
            "ix_serp_snapshots_run_kw_collected",
            "research_run_id",
            "keyword_id",
            "collected_at",
        ),
    )

    research_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_code: Mapped[str] = mapped_column(String(50), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="desktop",
        server_default=text("'desktop'"),
    )
    serp_features: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    raw_response_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    data_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="AVAILABLE",
        server_default=text("'AVAILABLE'"),
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    results: Mapped[list["SerpResult"]] = relationship(
        back_populates="serp_snapshot",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SerpResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Individual ranked result item within a SERP snapshot."""

    __tablename__ = "serp_results"
    __table_args__ = (
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(
            "result_type IN ('ORGANIC', 'FEATURED_SNIPPET', 'VIDEO', 'FORUM', 'ECOMMERCE', 'OTHER')",
            name="result_type_allowed",
        ),
        Index("ix_serp_results_snapshot_pos", "serp_snapshot_id", "position"),
        Index("ix_serp_results_normalized_url", "normalized_url"),
    )

    serp_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("serp_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ORGANIC",
        server_default=text("'ORGANIC'"),
    )
    competitor_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competitor_pages.id", ondelete="SET NULL"),
        nullable=True,
    )

    serp_snapshot: Mapped["SerpSnapshot"] = relationship(back_populates="results")
    competitor_page: Mapped["CompetitorPage | None"] = relationship()


class KeywordIntent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evidence-based Search Intent classification preserving AI baseline and history."""

    __tablename__ = "keyword_intents"
    __table_args__ = (
        CheckConstraint(
            "primary_intent IN ('INFORMATIONAL', 'NAVIGATIONAL', 'COMMERCIAL', 'TRANSACTIONAL')",
            name="primary_intent_allowed",
        ),
        CheckConstraint(
            "secondary_intent IS NULL OR secondary_intent IN "
            "('INFORMATIONAL', 'NAVIGATIONAL', 'COMMERCIAL', 'TRANSACTIONAL')",
            name="secondary_intent_allowed",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("origin IN ('AI', 'HUMAN')", name="origin_allowed"),
    )

    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    serp_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("serp_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    primary_intent: Mapped[str] = mapped_column(String(20), nullable=False)
    secondary_intent: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    origin: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="AI",
        server_default=text("'AI'"),
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
