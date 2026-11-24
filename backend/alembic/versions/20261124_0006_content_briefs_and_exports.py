"""Add Sprint 7 & 8 Content Briefs, Review 3 audit, and Export Jobs tables.

Revision ID: 0006_content_briefs_and_exports
Revises: 0005_workflow_and_hitl
Create Date: 2026-11-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_content_briefs_and_exports"
down_revision: str | None = "0005_workflow_and_hitl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_briefs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("primary_keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_current", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("origin", sa.String(length=16), server_default="AI", nullable=False),
        sa.Column(
            "status", sa.String(length=32), server_default="PENDING_REVIEW", nullable=False
        ),
        sa.Column("search_intent", sa.String(length=32), nullable=False),
        sa.Column("target_audience", sa.Text(), nullable=False),
        sa.Column("content_objective", sa.Text(), nullable=False),
        sa.Column("content_angle", sa.Text(), nullable=False),
        sa.Column("suggested_seo_title", sa.String(length=255), nullable=False),
        sa.Column("meta_description", sa.Text(), nullable=False),
        sa.Column("h1", sa.String(length=255), nullable=False),
        sa.Column(
            "competitor_insights",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "important_topics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "content_recommendations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "keyword_coverage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
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
            "origin IN ('AI', 'HUMAN')",
            name=op.f("ck_content_briefs_origin_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'NEEDS_REVISION', 'REJECTED')",
            name=op.f("ck_content_briefs_status_allowed"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_content_briefs_version_positive")),
        sa.ForeignKeyConstraint(
            ["cluster_id"],
            ["keyword_clusters.id"],
            name=op.f("fk_content_briefs_cluster_id_keyword_clusters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["primary_keyword_id"],
            ["keywords.id"],
            name=op.f("fk_content_briefs_primary_keyword_id_keywords"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_content_briefs_research_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_content_briefs")),
    )
    op.create_index(
        "ix_content_briefs_run_current",
        "content_briefs",
        ["research_run_id", "is_current"],
        unique=False,
    )
    op.create_index(
        "uq_content_briefs_one_current_per_cluster",
        "content_briefs",
        ["cluster_id"],
        unique=True,
        postgresql_where=sa.text("is_current = true"),
    )

    op.create_table(
        "brief_keywords",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_brief_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_role", sa.String(length=16), nullable=False),
        sa.Column("placement_hint", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "usage_role IN ('PRIMARY', 'SECONDARY', 'SUPPORTING')",
            name=op.f("ck_brief_keywords_usage_role_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["content_brief_id"],
            ["content_briefs.id"],
            name=op.f("fk_brief_keywords_content_brief_id_content_briefs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name=op.f("fk_brief_keywords_keyword_id_keywords"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brief_keywords")),
    )
    op.create_index(
        "ix_brief_keywords_brief_id",
        "brief_keywords",
        ["content_brief_id"],
        unique=False,
    )

    op.create_table(
        "brief_sections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_brief_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_section_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("heading_level", sa.SmallInteger(), nullable=False),
        sa.Column("heading_text", sa.String(length=255), nullable=False),
        sa.Column("section_order", sa.Integer(), nullable=False),
        sa.Column(
            "key_points",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "target_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.CheckConstraint(
            "heading_level IN (2, 3)",
            name=op.f("ck_brief_sections_heading_level_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["content_brief_id"],
            ["content_briefs.id"],
            name=op.f("fk_brief_sections_content_brief_id_content_briefs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_section_id"],
            ["brief_sections.id"],
            name=op.f("fk_brief_sections_parent_section_id_brief_sections"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brief_sections")),
    )
    op.create_index(
        "ix_brief_sections_brief_order",
        "brief_sections",
        ["content_brief_id", "section_order"],
        unique=False,
    )

    op.create_table(
        "brief_faqs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_brief_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_guidance", sa.Text(), nullable=False),
        sa.Column("source_evidence", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_brief_id"],
            ["content_briefs.id"],
            name=op.f("fk_brief_faqs_content_brief_id_content_briefs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brief_faqs")),
    )
    op.create_index(
        "ix_brief_faqs_brief_order",
        "brief_faqs",
        ["content_brief_id", "display_order"],
        unique=False,
    )

    op.create_table(
        "brief_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("content_brief_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("feedback_notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('EDIT', 'APPROVE', 'REJECT', 'REGENERATE')",
            name=op.f("ck_brief_reviews_action_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["content_brief_id"],
            ["content_briefs.id"],
            name=op.f("fk_brief_reviews_content_brief_id_content_briefs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
            name=op.f("fk_brief_reviews_reviewer_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brief_reviews")),
    )
    op.create_index(
        "ix_brief_reviews_brief_created",
        "brief_reviews",
        ["content_brief_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "export_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="PENDING", nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("google_spreadsheet_id", sa.String(length=128), nullable=True),
        sa.Column("google_spreadsheet_url", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "export_type IN ('EXCEL', 'GOOGLE_SHEETS')",
            name=op.f("ck_export_jobs_export_type_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name=op.f("ck_export_jobs_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_export_jobs_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name=op.f("fk_export_jobs_research_run_id_research_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_jobs")),
    )
    op.create_index(
        "ix_export_jobs_run_created",
        "export_jobs",
        ["research_run_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_run_created", table_name="export_jobs")
    op.drop_table("export_jobs")
    op.drop_index("ix_brief_reviews_brief_created", table_name="brief_reviews")
    op.drop_table("brief_reviews")
    op.drop_index("ix_brief_faqs_brief_order", table_name="brief_faqs")
    op.drop_table("brief_faqs")
    op.drop_index("ix_brief_sections_brief_order", table_name="brief_sections")
    op.drop_table("brief_sections")
    op.drop_index("ix_brief_keywords_brief_id", table_name="brief_keywords")
    op.drop_table("brief_keywords")
    op.drop_index("uq_content_briefs_one_current_per_cluster", table_name="content_briefs")
    op.drop_index("ix_content_briefs_run_current", table_name="content_briefs")
    op.drop_table("content_briefs")
