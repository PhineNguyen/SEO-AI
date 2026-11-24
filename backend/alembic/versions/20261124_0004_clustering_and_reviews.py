"""Add Sprint 5 clustering and Review 2 audit tables.

Revision ID: 0004_clustering_and_reviews
Revises: 0003_serp_and_intent
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_clustering_and_reviews"
down_revision: str | None = "0003_serp_and_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "keyword_clusters",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_name", sa.String(length=255), nullable=False),
        sa.Column("primary_keyword_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("cluster_intent", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("clustering_reasoning", sa.Text(), nullable=False),
        sa.Column(
            "scoring_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), server_default="ACTIVE", nullable=False),
        sa.Column("origin", sa.String(length=16), server_default="AI", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
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
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'APPROVED', 'MERGED', 'SPLIT', 'REJECTED')",
            name=op.f("ck_keyword_clusters_status_allowed"),
        ),
        sa.CheckConstraint(
            "origin IN ('AI', 'HUMAN')",
            name=op.f("ck_keyword_clusters_origin_allowed"),
        ),
        sa.CheckConstraint(
            "cluster_intent IS NULL OR cluster_intent IN ('Informational', 'Commercial', 'Transactional', 'Navigational')",
            name=op.f("ck_keyword_clusters_cluster_intent_allowed"),
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_keyword_clusters_confidence_range"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_keyword_clusters_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["primary_keyword_id"],
            ["keywords.id"],
            name=op.f("fk_keyword_clusters_primary_keyword_id_keywords"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_keyword_clusters_research_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keyword_clusters")),
    )
    op.create_index(
        "ix_keyword_clusters_run_status",
        "keyword_clusters",
        ["research_run_id", "status"],
        unique=False,
    )

    op.create_table(
        "cluster_keywords",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="SECONDARY", nullable=False),
        sa.Column("similarity_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("serp_overlap_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("semantic_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("intent_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "is_manual_override",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('PRIMARY', 'SECONDARY', 'SUPPORTING')",
            name=op.f("ck_cluster_keywords_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["keyword_clusters.id"],
            name=op.f("fk_cluster_keywords_cluster_id_keyword_clusters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name=op.f("fk_cluster_keywords_keyword_id_keywords"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cluster_keywords")),
        sa.UniqueConstraint("cluster_id", "keyword_id", name="uq_cluster_keywords_cluster_kw"),
    )
    op.create_index(
        "ix_cluster_keywords_keyword_id",
        "cluster_keywords",
        ["keyword_id"],
        unique=False,
    )

    op.create_table(
        "cluster_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column(
            "before_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "after_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('APPROVE', 'MERGE', 'SPLIT', 'MOVE_KEYWORD', 'CHANGE_PRIMARY', 'RENAME', 'REJECT')",
            name=op.f("ck_cluster_reviews_action_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["keyword_clusters.id"],
            name=op.f("fk_cluster_reviews_cluster_id_keyword_clusters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_cluster_reviews_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cluster_reviews")),
    )
    op.create_index(
        "ix_cluster_reviews_cluster_created",
        "cluster_reviews",
        ["cluster_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cluster_reviews_cluster_created", table_name="cluster_reviews")
    op.drop_table("cluster_reviews")
    op.drop_index("ix_cluster_keywords_keyword_id", table_name="cluster_keywords")
    op.drop_table("cluster_keywords")
    op.drop_index("ix_keyword_clusters_run_status", table_name="keyword_clusters")
    op.drop_table("keyword_clusters")
