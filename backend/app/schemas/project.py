"""Pydantic v2 schemas for Project, ProjectSettings, Website, and Competitor APIs."""

import math
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalization import (
    normalize_base_url,
    normalize_country_code,
    normalize_domain,
    normalize_language_code,
)

CLUSTERING_WEIGHT_KEYS = {"semantic", "serp_overlap", "intent"}


def _validate_clustering_weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights.keys()) != CLUSTERING_WEIGHT_KEYS:
        raise ValueError(
            f"clustering_weights must contain exact keys {sorted(CLUSTERING_WEIGHT_KEYS)}"
        )
    for key, val in weights.items():
        if not math.isfinite(val) or val < 0.0 or val > 1.0:
            raise ValueError(f"clustering_weights['{key}'] must be between 0.0 and 1.0")
    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError("clustering_weights values must sum to 1.0")
    return weights


def _validate_prioritization_weights(weights: dict[str, float]) -> dict[str, float]:
    for key, val in weights.items():
        if not math.isfinite(val) or val < 0.0:
            raise ValueError(f"prioritization_weights['{key}'] must be non-negative")
    return weights


class ProjectSettingsUpdate(BaseModel):
    """Payload for updating configurable project settings."""

    prioritization_weights: dict[str, float] | None = None
    clustering_weights: dict[str, float] | None = None
    default_serp_provider: str | None = Field(default=None, min_length=1, max_length=50)
    default_device: Literal["desktop", "mobile"] | None = None
    custom_rules: dict[str, Any] | None = None

    @field_validator("prioritization_weights")
    @classmethod
    def check_prioritization_weights(
        cls,
        value: dict[str, float] | None,
    ) -> dict[str, float] | None:
        if value is not None:
            return _validate_prioritization_weights(value)
        return value

    @field_validator("clustering_weights")
    @classmethod
    def check_clustering_weights(
        cls,
        value: dict[str, float] | None,
    ) -> dict[str, float] | None:
        if value is not None:
            return _validate_clustering_weights(value)
        return value


class ProjectSettingsResponse(BaseModel):
    """Project settings representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    prioritization_weights: dict[str, Any]
    clustering_weights: dict[str, float]
    default_serp_provider: str
    default_device: str
    custom_rules: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WebsiteCreate(BaseModel):
    """Payload for attaching a website to a project."""

    domain: str
    base_url: str
    gsc_property_uri: str | None = None
    is_primary: bool = False

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return normalize_domain(value)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_base_url(value)

    @field_validator("gsc_property_uri")
    @classmethod
    def clean_gsc_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class WebsiteUpdate(BaseModel):
    """Payload for updating a project website."""

    domain: str | None = None
    base_url: str | None = None
    gsc_property_uri: str | None = None
    is_primary: bool | None = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str | None) -> str | None:
        return normalize_domain(value) if value is not None else None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        return normalize_base_url(value) if value is not None else None

    @field_validator("gsc_property_uri")
    @classmethod
    def clean_gsc_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class WebsiteResponse(BaseModel):
    """Website representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    domain: str
    base_url: str
    gsc_property_uri: str | None
    is_primary: bool
    created_at: datetime
    updated_at: datetime


class CompetitorCreate(BaseModel):
    """Payload for adding a competitor domain to a project."""

    domain: str
    name: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return normalize_domain(value)


class CompetitorUpdate(BaseModel):
    """Payload for updating a project competitor."""

    domain: str | None = None
    name: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str | None) -> str | None:
        return normalize_domain(value) if value is not None else None


class CompetitorResponse(BaseModel):
    """Competitor representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    domain: str
    name: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProjectCreate(BaseModel):
    """Payload for creating a new SEO research project."""

    name: str = Field(min_length=1, max_length=255)
    niche: str | None = Field(default=None, max_length=255)
    target_country: str
    target_language: str
    target_audience: str | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Project name must not be blank")
        return stripped

    @field_validator("target_country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        return normalize_country_code(value)

    @field_validator("target_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_code(value)


class ProjectUpdate(BaseModel):
    """Payload for partially updating a project."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    niche: str | None = Field(default=None, max_length=255)
    target_country: str | None = None
    target_language: str | None = None
    target_audience: str | None = None
    status: Literal["ACTIVE", "ARCHIVED"] | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Project name must not be blank")
        return stripped

    @field_validator("target_country")
    @classmethod
    def validate_country(cls, value: str | None) -> str | None:
        return normalize_country_code(value) if value is not None else None

    @field_validator("target_language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        return normalize_language_code(value) if value is not None else None


class ProjectResponse(BaseModel):
    """Summary project representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    niche: str | None
    target_country: str
    target_language: str
    target_audience: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ProjectDetailResponse(ProjectResponse):
    """Detailed project representation including settings, websites, and competitors."""

    settings: ProjectSettingsResponse | None = None
    websites: list[WebsiteResponse] = Field(default_factory=list)
    competitors: list[CompetitorResponse] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    """Paginated list of projects."""

    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int
