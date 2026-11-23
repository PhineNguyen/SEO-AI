"""PostgreSQL integration tests verifying ORM relationships, defaults, and constraints."""

import uuid

import pytest
from app.models import (
    DEFAULT_CLUSTERING_WEIGHTS,
    Competitor,
    Project,
    ProjectSettings,
    User,
    Website,
)
from sqlalchemy import select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _create_user(db: Session, email: str = "seo@example.com") -> User:
    user = User(email=email, password_hash="hashed_pw", full_name="SEO Lead")
    db.add(user)
    db.flush()
    return user


def _create_project(db: Session, owner: User, name: str = "Vietnam SaaS") -> Project:
    project = Project(
        owner_id=owner.id,
        name=name,
        niche="B2B SaaS",
        target_country="VN",
        target_language="vi",
        target_audience="Marketing Managers",
    )
    db.add(project)
    db.flush()
    return project


def test_create_project_graph_with_defaults_and_timestamps(db_session: Session) -> None:
    user = _create_user(db_session)
    project = _create_project(db_session, user)
    settings = ProjectSettings(project_id=project.id)
    website = Website(
        project_id=project.id,
        domain="example.vn",
        base_url="https://example.vn",
        is_primary=True,
    )
    competitor = Competitor(
        project_id=project.id,
        domain="competitor.vn",
        name="Top Competitor",
    )
    db_session.add_all([settings, website, competitor])
    db_session.flush()
    db_session.expire_all()

    loaded_settings = db_session.scalar(
        select(ProjectSettings).where(ProjectSettings.project_id == project.id)
    )
    assert loaded_settings is not None
    assert loaded_settings.clustering_weights == DEFAULT_CLUSTERING_WEIGHTS
    assert loaded_settings.default_serp_provider == "dataforseo"
    assert loaded_settings.default_device == "desktop"
    assert isinstance(project.id, uuid.UUID)
    assert project.created_at.tzinfo is not None


def test_duplicate_user_email_rejected(db_session: Session) -> None:
    _create_user(db_session, email="dup@example.com")
    with pytest.raises(IntegrityError), db_session.begin_nested():
        _create_user(db_session, email="dup@example.com")


def test_duplicate_website_domain_per_project_rejected(db_session: Session) -> None:
    user = _create_user(db_session, email="web1@example.com")
    project = _create_project(db_session, user)
    db_session.add(
        Website(project_id=project.id, domain="site.vn", base_url="https://site.vn")
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Website(project_id=project.id, domain="site.vn", base_url="https://site.vn/blog")
        )
        db_session.flush()


def test_second_primary_website_in_same_project_rejected(db_session: Session) -> None:
    user = _create_user(db_session, email="web2@example.com")
    project = _create_project(db_session, user)
    db_session.add(
        Website(
            project_id=project.id,
            domain="primary.vn",
            base_url="https://primary.vn",
            is_primary=True,
        )
    )
    db_session.flush()

    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            Website(
                project_id=project.id,
                domain="secondary.vn",
                base_url="https://secondary.vn",
                is_primary=True,
            )
        )
        db_session.flush()


@pytest.mark.parametrize(
    ("bad_country", "expected_exc"),
    [
        ("vn", IntegrityError),
        ("V", IntegrityError),
        ("12", IntegrityError),
        ("VNM", DataError),
    ],
)
def test_invalid_target_country_rejected_by_check_constraint(
    db_session: Session,
    bad_country: str,
    expected_exc: type[Exception],
) -> None:
    user = _create_user(db_session, email=f"country_{bad_country}@example.com")
    with pytest.raises(expected_exc), db_session.begin_nested():
        db_session.add(
            Project(
                owner_id=user.id,
                name="Bad Country Project",
                target_country=bad_country,
                target_language="vi",
            )
        )
        db_session.flush()


def test_invalid_default_device_rejected_by_check_constraint(db_session: Session) -> None:
    user = _create_user(db_session, email="device@example.com")
    project = _create_project(db_session, user)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(ProjectSettings(project_id=project.id, default_device="tablet"))
        db_session.flush()


def test_delete_project_cascades_children_and_delete_owner_restricted(
    db_session: Session,
) -> None:
    user = _create_user(db_session, email="cascade@example.com")
    project = _create_project(db_session, user)
    project_id = project.id
    db_session.add_all(
        [
            ProjectSettings(project_id=project_id),
            Website(project_id=project_id, domain="child.vn", base_url="https://child.vn"),
            Competitor(project_id=project_id, domain="rival.vn"),
        ]
    )
    db_session.flush()

    # Owner cannot be deleted while project exists (ON DELETE RESTRICT)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.delete(user)
        db_session.flush()

    # Deleting project cascades to settings, websites, and competitors
    db_session.delete(project)
    db_session.flush()
    assert (
        db_session.scalar(
            select(ProjectSettings).where(ProjectSettings.project_id == project_id)
        )
        is None
    )
    assert db_session.scalar(select(Website).where(Website.project_id == project_id)) is None
    assert (
        db_session.scalar(select(Competitor).where(Competitor.project_id == project_id))
        is None
    )
