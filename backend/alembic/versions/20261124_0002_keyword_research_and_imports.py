"""Add keyword research, source imports, keyword metrics, and tags tables.

Revision ID: 0002_keyword_research
Revises: 0001_init_core
Create Date: 2026-11-24 03:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_keyword_research"
down_revision: str | Sequence[str] | None = "0001_init_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("search_context", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column(
            "device",
            sa.String(length=10),
            server_default=sa.text("'desktop'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'DRAFT'"),
            nullable=False,
        ),
        sa.Column(
            "config_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("country_code ~ '^[A-Z]{2}$'", name="ck_research_runs_country_code_iso2"),
        sa.CheckConstraint(
            "language_code ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'",
            name="ck_research_runs_language_code_bcp47",
        ),
        sa.CheckConstraint(
            "device IN ('desktop', 'mobile')",
            name="ck_research_runs_device_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'RUNNING', 'WAITING_REVIEW_1', 'WAITING_REVIEW_2', "
            "'WAITING_REVIEW_3', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_research_runs_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_research_runs_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_research_runs_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_runs"),
    )
    op.create_index("ix_research_runs_created_by", "research_runs", ["created_by"], unique=False)
    op.create_index("ix_research_runs_project_id", "research_runs", ["project_id"], unique=False)

    op.create_table(
        "seed_keywords",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seed_text", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name="fk_seed_keywords_research_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_seed_keywords"),
        sa.UniqueConstraint(
            "research_run_id",
            "seed_text",
            name="uq_seed_keywords_research_run_id_seed_text",
        ),
    )
    op.create_index(
        "ix_seed_keywords_research_run_id",
        "seed_keywords",
        ["research_run_id"],
        unique=False,
    )

    op.create_table(
        "source_imports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_hash_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "column_mapping",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("imported_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_rows", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
            "status IN ('OK', 'PARTIAL', 'ERROR')",
            name="ck_source_imports_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_source_imports_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name="fk_source_imports_research_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name="fk_source_imports_source_id_data_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_imports"),
    )
    op.create_index(
        "ix_source_imports_research_run_id",
        "source_imports",
        ["research_run_id"],
        unique=False,
    )

    op.create_table(
        "keywords",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_keyword", sa.Text(), nullable=False),
        sa.Column("normalized_keyword", sa.Text(), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column(
            "keyword_type",
            sa.String(length=30),
            server_default=sa.text("'RELATED'"),
            nullable=False,
        ),
        sa.Column(
            "cleaning_status",
            sa.String(length=20),
            server_default=sa.text("'RAW'"),
            nullable=False,
        ),
        sa.Column("duplicate_of_keyword_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("priority_score", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("priority_tier", sa.String(length=10), nullable=True),
        sa.Column("priority_reasoning", sa.Text(), nullable=True),
        sa.Column(
            "is_manual_entry",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
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
            "keyword_type IN ('SEED', 'PRIMARY_CANDIDATE', 'RELATED', 'LONG_TAIL', "
            "'QUESTION', 'SUPPORTING', 'VARIATION')",
            name="ck_keywords_keyword_type_allowed",
        ),
        sa.CheckConstraint(
            "cleaning_status IN ('RAW', 'ACTIVE', 'DUPLICATE', 'NEAR_DUPLICATE', "
            "'IRRELEVANT', 'INVALID')",
            name="ck_keywords_cleaning_status_allowed",
        ),
        sa.CheckConstraint(
            "review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_keywords_review_status_allowed",
        ),
        sa.CheckConstraint(
            "priority_tier IS NULL OR priority_tier IN ('P1', 'P2', 'P3')",
            name="ck_keywords_priority_tier_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_keyword_id"],
            ["keywords.id"],
            name="fk_keywords_duplicate_of_keyword_id_keywords",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name="fk_keywords_research_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keywords"),
    )
    op.create_index("ix_keywords_research_run_id", "keywords", ["research_run_id"], unique=False)
    op.create_index(
        "ix_keywords_run_review_cleaning",
        "keywords",
        ["research_run_id", "review_status", "cleaning_status"],
        unique=False,
    )
    op.create_index(
        "uq_keywords_active_normalized_per_run",
        "keywords",
        ["research_run_id", "normalized_keyword"],
        unique=True,
        postgresql_where=sa.text("cleaning_status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_keywords_normalized_trgm",
        "keywords",
        ["normalized_keyword"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"normalized_keyword": "gin_trgm_ops"},
    )

    op.create_table(
        "keyword_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_record_id", sa.String(length=255), nullable=True),
        sa.Column("raw_keyword", sa.Text(), nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_keyword_sources_keyword_id_keywords",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name="fk_keyword_sources_source_id_data_sources",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_import_id"],
            ["source_imports.id"],
            name="fk_keyword_sources_source_import_id_source_imports",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_sources"),
    )
    op.create_index("ix_keyword_sources_keyword_id", "keyword_sources", ["keyword_id"], unique=False)

    op.create_table(
        "keyword_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_type", sa.String(length=30), nullable=False),
        sa.Column("numeric_value", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column("data_status", sa.String(length=20), nullable=False),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "extra_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
            "metric_type IN ('SEARCH_VOLUME', 'KEYWORD_DIFFICULTY', 'CPC', 'COMPETITION', "
            "'GSC_IMPRESSIONS', 'GSC_CLICKS', 'GSC_CTR', 'GSC_POSITION')",
            name="ck_keyword_metrics_metric_type_allowed",
        ),
        sa.CheckConstraint(
            "data_status IN ('AVAILABLE', 'NOT_AVAILABLE', 'NOT_COLLECTED', "
            "'SOURCE_ERROR', 'NOT_APPLICABLE')",
            name="ck_keyword_metrics_data_status_allowed",
        ),
        sa.CheckConstraint(
            "(data_status = 'AVAILABLE' AND numeric_value IS NOT NULL) OR "
            "(data_status <> 'AVAILABLE' AND numeric_value IS NULL)",
            name="ck_keyword_metrics_value_matches_status",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_keyword_metrics_keyword_id_keywords",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name="fk_keyword_metrics_source_id_data_sources",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_metrics"),
    )
    op.create_index("ix_keyword_metrics_keyword_id", "keyword_metrics", ["keyword_id"], unique=False)
    op.create_index(
        "ix_keyword_metrics_kw_type_collected",
        "keyword_metrics",
        ["keyword_id", "metric_type", "collected_at"],
        unique=False,
    )

    op.create_table(
        "keyword_tags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_name", sa.String(length=100), nullable=False),
        sa.Column(
            "tag_source",
            sa.String(length=10),
            server_default=sa.text("'RULE'"),
            nullable=False,
        ),
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
            "tag_source IN ('AI', 'RULE', 'USER')",
            name="ck_keyword_tags_tag_source_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_keyword_tags_keyword_id_keywords",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_tags"),
        sa.UniqueConstraint("keyword_id", "tag_name", name="uq_keyword_tags_keyword_id_tag_name"),
    )
    op.create_index("ix_keyword_tags_keyword_id", "keyword_tags", ["keyword_id"], unique=False)

    op.execute(
        """
        INSERT INTO data_sources (code, name, source_type) VALUES
            ('gkp_csv', 'Google Keyword Planner CSV/Excel Import', 'FILE_IMPORT')
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM data_sources WHERE code = 'gkp_csv'")

    op.drop_index("ix_keyword_tags_keyword_id", table_name="keyword_tags")
    op.drop_table("keyword_tags")

    op.drop_index("ix_keyword_metrics_kw_type_collected", table_name="keyword_metrics")
    op.drop_index("ix_keyword_metrics_keyword_id", table_name="keyword_metrics")
    op.drop_table("keyword_metrics")

    op.drop_index("ix_keyword_sources_keyword_id", table_name="keyword_sources")
    op.drop_table("keyword_sources")

    op.drop_index("ix_keywords_normalized_trgm", table_name="keywords")
    op.drop_index("uq_keywords_active_normalized_per_run", table_name="keywords")
    op.drop_index("ix_keywords_run_review_cleaning", table_name="keywords")
    op.drop_index("ix_keywords_research_run_id", table_name="keywords")
    op.drop_table("keywords")

    op.drop_index("ix_source_imports_research_run_id", table_name="source_imports")
    op.drop_table("source_imports")

    op.drop_index("ix_seed_keywords_research_run_id", table_name="seed_keywords")
    op.drop_table("seed_keywords")

    op.drop_index("ix_research_runs_project_id", table_name="research_runs")
    op.drop_index("ix_research_runs_created_by", table_name="research_runs")
    op.drop_table("research_runs")
