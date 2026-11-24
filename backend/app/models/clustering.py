"""SQLAlchemy 2.x ORM models for Sprint 5 (Hybrid Keyword Clustering & Review 2)."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

CLUSTER_STATUSES = ("ACTIVE", "APPROVED", "MERGED", "SPLIT", "REJECTED")
CLUSTER_ORIGINS = ("AI", "HUMAN")
CLUSTER_KEYWORD_ROLES = ("PRIMARY", "SECONDARY", "SUPPORTING")
CLUSTER_REVIEW_ACTIONS = (
    "APPROVE",
    "MERGE",
    "SPLIT",
    "MOVE_KEYWORD",
    "CHANGE_PRIMARY",
    "RENAME",
    "REJECT",
)


class KeywordCluster(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Topic cluster grouping semantically and SERP-aligned keywords."""

    __tablename__ = "keyword_clusters"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'APPROVED', 'MERGED', 'SPLIT', 'REJECTED')",
            name="status_allowed",
        ),
        CheckConstraint("origin IN ('AI', 'HUMAN')", name="origin_allowed"),
        CheckConstraint(
            "cluster_intent IS NULL OR cluster_intent IN ('Informational', 'Commercial', 'Transactional', 'Navigational')",
            name="cluster_intent_allowed",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_keyword_clusters_run_status", "research_run_id", "status"),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    cluster_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_keyword_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="SET NULL"),
        nullable=True,
    )
    cluster_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    clustering_reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scoring_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, default="AI", server_default="AI"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    members: Mapped[list["ClusterKeyword"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )
    reviews: Mapped[list["ClusterReview"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )


class ClusterKeyword(UUIDPrimaryKeyMixin, Base):
    """Association linking a keyword to a cluster with hybrid similarity breakdown."""

    __tablename__ = "cluster_keywords"
    __table_args__ = (
        UniqueConstraint("cluster_id", "keyword_id", name="uq_cluster_keywords_cluster_kw"),
        CheckConstraint(
            "role IN ('PRIMARY', 'SECONDARY', 'SUPPORTING')",
            name="role_allowed",
        ),
        Index("ix_cluster_keywords_keyword_id", "keyword_id"),
    )

    cluster_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keyword_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SECONDARY", server_default="SECONDARY"
    )
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    serp_overlap_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    semantic_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    intent_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    is_manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    cluster: Mapped[KeywordCluster] = relationship(back_populates="members")


class ClusterReview(UUIDPrimaryKeyMixin, Base):
    """Audit log of Review 2 human actions preserving before/after snapshots."""

    __tablename__ = "cluster_reviews"
    __table_args__ = (
        CheckConstraint(
            "action IN ('APPROVE', 'MERGE', 'SPLIT', 'MOVE_KEYWORD', 'CHANGE_PRIMARY', 'RENAME', 'REJECT')",
            name="action_allowed",
        ),
        Index("ix_cluster_reviews_cluster_created", "cluster_id", "created_at"),
    )

    cluster_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("keyword_clusters.id", ondelete="CASCADE"),
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
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    cluster: Mapped[KeywordCluster] = relationship(back_populates="reviews")
