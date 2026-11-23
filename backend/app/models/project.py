"""Project management ORM models: Project, Website, ProjectSettings, Competitor."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User

DEFAULT_CLUSTERING_WEIGHTS: dict[str, float] = {
    "semantic": 0.3,
    "serp_overlap": 0.5,
    "intent": 0.2,
}


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """SEO keyword research project targeting a country, language, and niche."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "name"),
        CheckConstraint("target_country ~ '^[A-Z]{2}$'", name="target_country_iso2"),
        CheckConstraint(
            "target_language ~ '^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$'",
            name="target_language_bcp47",
        ),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="status_allowed"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_country: Mapped[str] = mapped_column(String(2), nullable=False)
    target_language: Mapped[str] = mapped_column(String(10), nullable=False)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        server_default=text("'ACTIVE'"),
    )

    owner: Mapped["User"] = relationship(back_populates="projects")
    websites: Mapped[list["Website"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    settings: Mapped["ProjectSettings | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    competitors: Mapped[list["Competitor"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Website(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Website domain and optional GSC property linked to a research project."""

    __tablename__ = "websites"
    __table_args__ = (
        UniqueConstraint("project_id", "domain"),
        Index(
            "uq_websites_one_primary_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    gsc_property_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    project: Mapped["Project"] = relationship(back_populates="websites")


class ProjectSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurable prioritization weights, clustering weights, and SERP defaults."""

    __tablename__ = "project_settings"
    __table_args__ = (
        CheckConstraint(
            "default_device IN ('desktop', 'mobile')",
            name="default_device_allowed",
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    prioritization_weights: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    clustering_weights: Mapped[dict[str, float]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: dict(DEFAULT_CLUSTERING_WEIGHTS),
        server_default=text(
            "'{\"semantic\": 0.3, \"serp_overlap\": 0.5, \"intent\": 0.2}'::jsonb"
        ),
    )
    default_serp_provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="dataforseo",
        server_default=text("'dataforseo'"),
    )
    default_device: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="desktop",
        server_default=text("'desktop'"),
    )
    custom_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    project: Mapped["Project"] = relationship(back_populates="settings")


class Competitor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Competitor domain tracked within a research project."""

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("project_id", "domain"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(253), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="competitors")
