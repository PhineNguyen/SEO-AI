"""Add Sprint 6 workflow executions, checkpoints, and HITL review decisions tables.

Revision ID: 0005_workflow_and_hitl
Revises: 0004_clustering_and_reviews
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_workflow_and_hitl"
down_revision: str | None = "0004_clustering_and_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_executions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("langgraph_thread_id", sa.String(length=128), nullable=False),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("current_node", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'WAITING_REVIEW_1', 'WAITING_REVIEW_2', 'WAITING_REVIEW_3', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name=op.f("ck_workflow_executions_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_workflow_executions_research_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_executions")),
        sa.UniqueConstraint(
            "langgraph_thread_id", name=op.f("uq_workflow_executions_langgraph_thread_id")
        ),
    )
    op.create_index(
        "ix_workflow_executions_run_status",
        "workflow_executions",
        ["research_run_id", "status"],
        unique=False,
    )

    op.create_table(
        "workflow_checkpoints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_name", sa.String(length=64), nullable=False),
        sa.Column("checkpoint_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="COMPLETED", nullable=False),
        sa.Column(
            "metrics_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name=op.f("fk_workflow_checkpoints_workflow_execution_id_workflow_executions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_checkpoints")),
    )
    op.create_index(
        "ix_workflow_checkpoints_exec_created",
        "workflow_checkpoints",
        ["workflow_execution_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "review_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workflow_execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_gate", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column(
            "summary_diff",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_gate IN ('REVIEW_1_KEYWORDS', 'REVIEW_2_CLUSTERS', 'REVIEW_3_BRIEFS')",
            name=op.f("ck_review_decisions_review_gate_allowed"),
        ),
        sa.CheckConstraint(
            "decision IN ('APPROVE', 'REJECT', 'EDIT_AND_APPROVE', 'REGENERATE')",
            name=op.f("ck_review_decisions_decision_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_review_decisions_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_execution_id"],
            ["workflow_executions.id"],
            name=op.f("fk_review_decisions_workflow_execution_id_workflow_executions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_decisions")),
    )
    op.create_index(
        "ix_review_decisions_exec_gate",
        "review_decisions",
        ["workflow_execution_id", "review_gate"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_review_decisions_exec_gate", table_name="review_decisions")
    op.drop_table("review_decisions")
    op.drop_index("ix_workflow_checkpoints_exec_created", table_name="workflow_checkpoints")
    op.drop_table("workflow_checkpoints")
    op.drop_index("ix_workflow_executions_run_status", table_name="workflow_executions")
    op.drop_table("workflow_executions")
