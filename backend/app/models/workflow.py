"""SQLAlchemy 2.x ORM models for Sprint 6 (LangGraph Workflow & HITL Audit)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, UUIDPrimaryKeyMixin

WORKFLOW_STATUSES = (
    "PENDING",
    "RUNNING",
    "WAITING_REVIEW_1",
    "WAITING_REVIEW_2",
    "WAITING_REVIEW_3",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)
REVIEW_GATES = ("REVIEW_1_KEYWORDS", "REVIEW_2_CLUSTERS", "REVIEW_3_BRIEFS")
REVIEW_DECISIONS = ("APPROVE", "REJECT", "EDIT_AND_APPROVE", "REGENERATE")


class WorkflowExecution(UUIDPrimaryKeyMixin, Base):
    """Tracks a LangGraph workflow execution tied to a research run."""

    __tablename__ = "workflow_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW_1', 'WAITING_REVIEW_2', 'WAITING_REVIEW_3', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="status_allowed",
        ),
        Index("ix_workflow_executions_run_status", "research_run_id", "status"),
    )

    research_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    langgraph_thread_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", server_default="PENDING"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    checkpoints: Mapped[list["WorkflowCheckpoint"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["ReviewDecision"]] = relationship(
        back_populates="execution", cascade="all, delete-orphan"
    )


class WorkflowCheckpoint(UUIDPrimaryKeyMixin, Base):
    """Domain-level checkpoint log for each workflow stage."""

    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        Index("ix_workflow_checkpoints_exec_created", "workflow_execution_id", "created_at"),
    )

    workflow_execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_name: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="COMPLETED", server_default="COMPLETED"
    )
    metrics_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    execution: Mapped[WorkflowExecution] = relationship(back_populates="checkpoints")


class ReviewDecision(UUIDPrimaryKeyMixin, Base):
    """Human-in-the-loop review decision recorded at Review 1, 2, or 3."""

    __tablename__ = "review_decisions"
    __table_args__ = (
        CheckConstraint(
            "review_gate IN ('REVIEW_1_KEYWORDS', 'REVIEW_2_CLUSTERS', 'REVIEW_3_BRIEFS')",
            name="review_gate_allowed",
        ),
        CheckConstraint(
            "decision IN ('APPROVE', 'REJECT', 'EDIT_AND_APPROVE', 'REGENERATE')",
            name="decision_allowed",
        ),
        Index("ix_review_decisions_exec_gate", "workflow_execution_id", "review_gate"),
    )

    workflow_execution_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    review_gate: Mapped[str] = mapped_column(String(32), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    summary_diff: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    reviewer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    execution: Mapped[WorkflowExecution] = relationship(back_populates="decisions")
