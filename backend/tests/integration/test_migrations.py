"""PostgreSQL integration tests for Alembic upgrade, check, downgrade, and seed data."""

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine.url import make_url

from tests.integration.conftest import (
    create_fresh_database,
    drop_database,
    get_base_test_database_url,
    make_alembic_config,
)

pytestmark = pytest.mark.integration

EXPECTED_DOMAIN_TABLES = {
    "users",
    "oauth_credentials",
    "projects",
    "websites",
    "project_settings",
    "competitors",
    "data_sources",
    "research_runs",
    "seed_keywords",
    "source_imports",
    "keywords",
    "keyword_sources",
    "keyword_metrics",
    "keyword_tags",
    "serp_snapshots",
    "serp_results",
    "competitor_pages",
    "competitor_headings",
    "keyword_intents",
    "keyword_clusters",
    "cluster_keywords",
    "cluster_reviews",
    "workflow_executions",
    "workflow_checkpoints",
    "review_decisions",
    "content_briefs",
    "brief_keywords",
    "brief_sections",
    "brief_faqs",
    "brief_reviews",
    "export_jobs",
}

EXPECTED_SEEDED_SOURCES = {
    ("dataforseo_kw", "API"),
    ("dataforseo_serp", "API"),
    ("gkp_csv", "FILE_IMPORT"),
    ("gsc_api", "API"),
    ("manual", "MANUAL"),
    ("semrush_api", "API"),
    ("semrush_csv", "FILE_IMPORT"),
    ("spineditor_import", "FILE_IMPORT"),
}


def test_migration_upgrade_check_downgrade_and_reupgrade() -> None:
    base_url = make_url(get_base_test_database_url())
    migration_db_url = base_url.set(database="keyword_research_test_migrations").render_as_string(
        hide_password=False
    )

    create_fresh_database(migration_db_url)
    cfg = make_alembic_config(migration_db_url)
    engine = create_engine(migration_db_url, pool_pre_ping=True)

    try:
        # 1. Upgrade to head
        command.upgrade(cfg, "head")

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert EXPECTED_DOMAIN_TABLES.issubset(tables)
        assert "alembic_version" in tables

        with engine.connect() as conn:
            ext_row = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
            ).fetchone()
            assert ext_row is not None, "pg_trgm extension must be installed"

            seeded_rows = conn.execute(
                text("SELECT code, source_type FROM data_sources")
            ).fetchall()
            assert set(seeded_rows) == EXPECTED_SEEDED_SOURCES

        # 2. Verify zero autogenerate drift between ORM models and migration 001
        command.check(cfg)

        # 3. Downgrade back to base cleanly
        command.downgrade(cfg, "base")
        inspector_after_down = inspect(engine)
        remaining_tables = set(inspector_after_down.get_table_names())
        assert EXPECTED_DOMAIN_TABLES.isdisjoint(remaining_tables)
        with engine.connect() as conn:
            ext_after_down = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm'")
            ).fetchone()
            assert ext_after_down is None

        # 4. Re-upgrade to head to confirm idempotent repeatability
        command.upgrade(cfg, "head")
        assert EXPECTED_DOMAIN_TABLES.issubset(set(inspect(engine).get_table_names()))
    finally:
        engine.dispose()
        drop_database(migration_db_url)
