"""SQLAlchemy 2.x ORM models for Sprint 7 & 8 (Content Briefs, Review 3, and Export Jobs)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ContentBrief(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned, evidence-based SEO Content Brief tied to a KeywordCluster."""

    __tablename__ = "content_briefs"
    __table_args__ = (
        CheckConstraint("origin IN ('AI', 'HUMAN')", name="origin_allowed"),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'NEEDS_REVISION', 'REJECTED')",
            name="status_allowed",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_content_briefs_run_current", "research_run_id", "is_current"),
        Index(
            "uq_content_briefs_one_current_per_cluster",
            "cluster_id",
            unique=True,
            postgresql_where=text("is_current = true"),
        ),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    cluster_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keyword_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    primary_keyword_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default="AI", server_default="AI"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PENDING_REVIEW",
        server_default="PENDING_REVIEW",
    )
    search_intent: Mapped[str] = mapped_column(String(32), nullable=False)
    target_audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_angle: Mapped[str] = mapped_column(Text, nullable=False, default="")
    suggested_seo_title: Mapped[str] = mapped_column(String(255), nullable=False)
    meta_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    h1: Mapped[str] = mapped_column(String(255), nullable=False)
    competitor_insights: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    important_topics: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    content_recommendations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    keyword_coverage: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="brief-v1")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="prompt-v1")

    brief_keywords: Mapped[list["BriefKeyword"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan"
    )
    sections: Mapped[list["BriefSection"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan", order_by="BriefSection.section_order"
    )
    faqs: Mapped[list["BriefFaq"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan", order_by="BriefFaq.display_order"
    )
    reviews: Mapped[list["BriefReview"]] = relationship(
        back_populates="brief", cascade="all, delete-orphan"
    )


class BriefKeyword(UUIDPrimaryKeyMixin, Base):
    """Keywords mapped to a content brief with usage role and placement guidance."""

    __tablename__ = "brief_keywords"
    __table_args__ = (
        CheckConstraint(
            "usage_role IN ('PRIMARY', 'SECONDARY', 'SUPPORTING')",
            name="usage_role_allowed",
        ),
        Index("ix_brief_keywords_brief_id", "content_brief_id"),
    )

    content_brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_briefs.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    usage_role: Mapped[str] = mapped_column(String(16), nullable=False, default="SECONDARY")
    placement_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)

    brief: Mapped[ContentBrief] = relationship(back_populates="brief_keywords")


class BriefSection(UUIDPrimaryKeyMixin, Base):
    """H2/H3 outline section within a Content Brief."""

    __tablename__ = "brief_sections"
    __table_args__ = (
        CheckConstraint("heading_level IN (2, 3)", name="heading_level_allowed"),
        Index("ix_brief_sections_brief_order", "content_brief_id", "section_order"),
    )

    content_brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_briefs.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_section_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("brief_sections.id", ondelete="SET NULL"),
        nullable=True,
    )
    heading_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=2)
    heading_text: Mapped[str] = mapped_column(String(255), nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    key_points: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    target_keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    brief: Mapped[ContentBrief] = relationship(back_populates="sections")


class BriefFaq(UUIDPrimaryKeyMixin, Base):
    """Evidence-backed FAQ item in a Content Brief."""

    __tablename__ = "brief_faqs"
    __table_args__ = (
        Index("ix_brief_faqs_brief_order", "content_brief_id", "display_order"),
    )

    content_brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_briefs.id", ondelete="CASCADE"),
        nullable=False,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_guidance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    brief: Mapped[ContentBrief] = relationship(back_populates="faqs")


class BriefReview(UUIDPrimaryKeyMixin, Base):
    """Review 3 audit log preserving before/after snapshots."""

    __tablename__ = "brief_reviews"
    __table_args__ = (
        CheckConstraint(
            "action IN ('EDIT', 'APPROVE', 'REJECT', 'REGENERATE')",
            name="action_allowed",
        ),
        Index("ix_brief_reviews_brief_created", "content_brief_id", "created_at"),
    )

    content_brief_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_briefs.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    before_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    after_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    feedback_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    brief: Mapped[ContentBrief] = relationship(back_populates="reviews")


class ExportJob(UUIDPrimaryKeyMixin, Base):
    """Tracks Excel (.xlsx) and Google Sheets export jobs."""

    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint("export_type IN ('EXCEL', 'GOOGLE_SHEETS')", name="export_type_allowed"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="status_allowed",
        ),
        Index("ix_export_jobs_run_created", "research_run_id", "created_at"),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    export_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", server_default="PENDING"
    )
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_spreadsheet_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    google_spreadsheet_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
