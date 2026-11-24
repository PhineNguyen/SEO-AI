"""Add SERP snapshots, SERP results, competitor pages/headings, and keyword intents tables.

Revision ID: 0003_serp_and_intent
Revises: 0002_keyword_research
Create Date: 2026-11-24 03:35:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_serp_and_intent"
down_revision: str | Sequence[str] | None = "0002_keyword_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competitor_pages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column(
            "fetch_status",
            sa.String(length=20),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
        sa.Column("page_title", sa.Text(), nullable=True),
        sa.Column("meta_description", sa.Text(), nullable=True),
        sa.Column("content_type_inferred", sa.String(length=50), nullable=True),
        sa.Column("word_count_estimate", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
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
            "fetch_status IN ('PENDING', 'FETCHED', 'BLOCKED_ROBOTS', 'BLOCKED_SSRF', 'TIMEOUT', 'ERROR')",
            name="ck_competitor_pages_fetch_status_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitor_pages"),
        sa.UniqueConstraint("normalized_url", name="uq_competitor_pages_normalized_url"),
    )

    op.create_table(
        "competitor_headings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("competitor_page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("heading_text", sa.Text(), nullable=False),
        sa.Column("position_order", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("level >= 1 AND level <= 6", name="ck_competitor_headings_level_range"),
        sa.ForeignKeyConstraint(
            ["competitor_page_id"],
            ["competitor_pages.id"],
            name="fk_competitor_headings_competitor_page_id_competitor_pages",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitor_headings"),
    )
    op.create_index(
        "ix_competitor_headings_competitor_page_id",
        "competitor_headings",
        ["competitor_page_id"],
        unique=False,
    )

    op.create_table(
        "serp_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("research_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_code", sa.String(length=50), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=False),
        sa.Column("location_name", sa.String(length=255), nullable=True),
        sa.Column(
            "device",
            sa.String(length=10),
            server_default=sa.text("'desktop'"),
            nullable=False,
        ),
        sa.Column(
            "serp_features",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "raw_response_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "data_status",
            sa.String(length=20),
            server_default=sa.text("'AVAILABLE'"),
            nullable=False,
        ),
        sa.Column(
            "collected_at",
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
        sa.CheckConstraint(
            "country_code ~ '^[A-Z]{2}$'",
            name="ck_serp_snapshots_country_code_iso2",
        ),
        sa.CheckConstraint(
            "device IN ('desktop', 'mobile')",
            name="ck_serp_snapshots_device_allowed",
        ),
        sa.CheckConstraint(
            "data_status IN ('AVAILABLE', 'NOT_AVAILABLE', 'NOT_COLLECTED', 'SOURCE_ERROR', 'NOT_APPLICABLE')",
            name="ck_serp_snapshots_data_status_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_serp_snapshots_keyword_id_keywords",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_run_id"],
            ["research_runs.id"],
            name="fk_serp_snapshots_research_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_serp_snapshots"),
    )
    op.create_index("ix_serp_snapshots_keyword_id", "serp_snapshots", ["keyword_id"], unique=False)
    op.create_index(
        "ix_serp_snapshots_research_run_id",
        "serp_snapshots",
        ["research_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_serp_snapshots_run_kw_collected",
        "serp_snapshots",
        ["research_run_id", "keyword_id", "collected_at"],
        unique=False,
    )

    op.create_table(
        "serp_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("serp_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column(
            "result_type",
            sa.String(length=30),
            server_default=sa.text("'ORGANIC'"),
            nullable=False,
        ),
        sa.Column("competitor_page_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("position >= 1", name="ck_serp_results_position_positive"),
        sa.CheckConstraint(
            "result_type IN ('ORGANIC', 'FEATURED_SNIPPET', 'VIDEO', 'FORUM', 'ECOMMERCE', 'OTHER')",
            name="ck_serp_results_result_type_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["competitor_page_id"],
            ["competitor_pages.id"],
            name="fk_serp_results_competitor_page_id_competitor_pages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["serp_snapshot_id"],
            ["serp_snapshots.id"],
            name="fk_serp_results_serp_snapshot_id_serp_snapshots",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_serp_results"),
    )
    op.create_index("ix_serp_results_normalized_url", "serp_results", ["normalized_url"], unique=False)
    op.create_index("ix_serp_results_serp_snapshot_id", "serp_results", ["serp_snapshot_id"], unique=False)
    op.create_index(
        "ix_serp_results_snapshot_pos",
        "serp_results",
        ["serp_snapshot_id", "position"],
        unique=False,
    )

    op.create_table(
        "keyword_intents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("serp_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("primary_intent", sa.String(length=20), nullable=False),
        sa.Column("secondary_intent", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column(
            "origin",
            sa.String(length=10),
            server_default=sa.text("'AI'"),
            nullable=False,
        ),
        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=sa.text("true"),
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
            "primary_intent IN ('INFORMATIONAL', 'NAVIGATIONAL', 'COMMERCIAL', 'TRANSACTIONAL')",
            name="ck_keyword_intents_primary_intent_allowed",
        ),
        sa.CheckConstraint(
            "secondary_intent IS NULL OR secondary_intent IN "
            "('INFORMATIONAL', 'NAVIGATIONAL', 'COMMERCIAL', 'TRANSACTIONAL')",
            name="ck_keyword_intents_secondary_intent_allowed",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_keyword_intents_confidence_range",
        ),
        sa.CheckConstraint(
            "origin IN ('AI', 'HUMAN')",
            name="ck_keyword_intents_origin_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["keyword_id"],
            ["keywords.id"],
            name="fk_keyword_intents_keyword_id_keywords",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["serp_snapshot_id"],
            ["serp_snapshots.id"],
            name="fk_keyword_intents_serp_snapshot_id_serp_snapshots",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_keyword_intents"),
    )
    op.create_index("ix_keyword_intents_keyword_id", "keyword_intents", ["keyword_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_keyword_intents_keyword_id", table_name="keyword_intents")
    op.drop_table("keyword_intents")

    op.drop_index("ix_serp_results_snapshot_pos", table_name="serp_results")
    op.drop_index("ix_serp_results_serp_snapshot_id", table_name="serp_results")
    op.drop_index("ix_serp_results_normalized_url", table_name="serp_results")
    op.drop_table("serp_results")

    op.drop_index("ix_serp_snapshots_run_kw_collected", table_name="serp_snapshots")
    op.drop_index("ix_serp_snapshots_research_run_id", table_name="serp_snapshots")
    op.drop_index("ix_serp_snapshots_keyword_id", table_name="serp_snapshots")
    op.drop_table("serp_snapshots")

    op.drop_index("ix_competitor_headings_competitor_page_id", table_name="competitor_headings")
    op.drop_table("competitor_headings")

    op.drop_table("competitor_pages")
