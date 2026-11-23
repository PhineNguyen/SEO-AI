"""Unit tests verifying SQLAlchemy 2.x ORM metadata without a database connection."""

from app import models  # noqa: F401
from app.database.base import Base
from app.models import DEFAULT_CLUSTERING_WEIGHTS
from sqlalchemy.dialects.postgresql import UUID

EXPECTED_TABLES = {
    "users",
    "oauth_credentials",
    "projects",
    "websites",
    "project_settings",
    "competitors",
    "data_sources",
}


def test_expected_tables_registered_in_metadata() -> None:
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_every_table_has_uuid_primary_key_with_server_default() -> None:
    for table_name in EXPECTED_TABLES:
        table = Base.metadata.tables[table_name]
        pk_cols = list(table.primary_key.columns)
        assert len(pk_cols) == 1, f"{table_name} should have a single-column PK"
        pk_col = pk_cols[0]
        assert pk_col.name == "id"
        assert isinstance(pk_col.type, UUID)
        assert pk_col.server_default is not None


def test_expected_constraints_and_unique_names_present() -> None:
    users_table = Base.metadata.tables["users"]
    user_uq_names = {c.name for c in users_table.constraints if hasattr(c, "columns")}
    assert "uq_users_email" in user_uq_names

    projects_table = Base.metadata.tables["projects"]
    project_ck_names = {c.name for c in projects_table.constraints}
    assert "ck_projects_target_country_iso2" in project_ck_names
    assert "ck_projects_target_language_bcp47" in project_ck_names
    assert "ck_projects_status_allowed" in project_ck_names

    websites_table = Base.metadata.tables["websites"]
    website_uq_names = {c.name for c in websites_table.constraints}
    assert "uq_websites_project_id_domain" in website_uq_names
    website_idx_names = {idx.name for idx in websites_table.indexes}
    assert "uq_websites_one_primary_per_project" in website_idx_names


def test_default_clustering_weights_match_specification() -> None:
    assert DEFAULT_CLUSTERING_WEIGHTS == {
        "semantic": 0.3,
        "serp_overlap": 0.5,
        "intent": 0.2,
    }
    assert sum(DEFAULT_CLUSTERING_WEIGHTS.values()) == 1.0
