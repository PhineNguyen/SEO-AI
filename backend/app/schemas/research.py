"""Pydantic v2 schemas for Research Runs, Seed Keywords, File Imports, Cleaning, and Review 1."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.normalization import normalize_country_code, normalize_language_code


class SeedKeywordInput(BaseModel):
    """Input for a single seed keyword."""

    seed_text: str = Field(min_length=1, max_length=500)
    topic: str | None = Field(default=None, max_length=255)

    @field_validator("seed_text")
    @classmethod
    def strip_seed(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("seed_text must not be blank")
        return cleaned


class SeedKeywordResponse(BaseModel):
    """Persisted seed keyword representation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    seed_text: str
    topic: str | None
    created_at: datetime


class ResearchRunCreate(BaseModel):
    """Payload for creating a new keyword research run under a project."""

    name: str = Field(min_length=1, max_length=255)
    search_context: str | None = None
    country_code: str | None = None
    language_code: str | None = None
    device: Literal["desktop", "mobile"] | None = None
    seed_keywords: list[SeedKeywordInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Research run name must not be blank")
        return cleaned

    @field_validator("country_code")
    @classmethod
    def validate_country(cls, value: str | None) -> str | None:
        return normalize_country_code(value) if value is not None else None

    @field_validator("language_code")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        return normalize_language_code(value) if value is not None else None


class ResearchRunResponse(BaseModel):
    """Summary representation of a research run."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    search_context: str | None
    country_code: str
    language_code: str
    device: str
    status: str
    config_snapshot: dict[str, Any]
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class ResearchRunDetailResponse(ResearchRunResponse):
    """Detailed research run including seed keywords and keyword status counts."""

    seed_keywords: list[SeedKeywordResponse] = Field(default_factory=list)
    keyword_counts: dict[str, int] = Field(default_factory=dict)


class SourceImportResponse(BaseModel):
    """Summary of an uploaded CSV/Excel keyword import."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_run_id: uuid.UUID
    source_id: uuid.UUID
    file_name: str
    file_hash_sha256: str
    column_mapping: dict[str, Any]
    total_rows: int
    imported_rows: int
    error_rows: int
    error_details: list[dict[str, Any]]
    status: str
    created_at: datetime


class KeywordMetricItem(BaseModel):
    """Single latest metric observation with full provenance."""

    metric_type: str
    source_code: str
    numeric_value: float | None
    raw_value: str | None
    unit: str
    currency: str | None
    data_status: str
    collected_at: datetime


class KeywordResponse(BaseModel):
    """Keyword candidate with provenance sources and aggregated metrics."""

    id: uuid.UUID
    research_run_id: uuid.UUID
    original_keyword: str
    normalized_keyword: str
    language_code: str
    keyword_type: str
    cleaning_status: str
    duplicate_of_keyword_id: uuid.UUID | None
    review_status: str
    priority_score: float | None
    priority_tier: str | None
    priority_reasoning: str | None
    is_manual_entry: bool
    sources: list[str] = Field(default_factory=list)
    metrics: list[KeywordMetricItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class KeywordListResponse(BaseModel):
    """Paginated keyword review list."""

    items: list[KeywordResponse]
    total: int
    limit: int
    offset: int


class ManualKeywordCreate(BaseModel):
    """Payload for manually adding a keyword during Review 1."""

    keyword: str = Field(min_length=1, max_length=255)
    keyword_type: Literal[
        "SEED",
        "PRIMARY_CANDIDATE",
        "RELATED",
        "LONG_TAIL",
        "QUESTION",
        "SUPPORTING",
        "VARIATION",
    ] = "PRIMARY_CANDIDATE"

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Keyword must not be blank")
        return cleaned


class KeywordReviewUpdate(BaseModel):
    """Payload for Review 1 edits on a single keyword."""

    review_status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None
    cleaning_status: Literal["ACTIVE", "IRRELEVANT"] | None = None
    keyword_type: Literal[
        "SEED",
        "PRIMARY_CANDIDATE",
        "RELATED",
        "LONG_TAIL",
        "QUESTION",
        "SUPPORTING",
        "VARIATION",
    ] | None = None
    edited_keyword: str | None = Field(default=None, min_length=1, max_length=255)


class BulkKeywordReviewRequest(BaseModel):
    """Payload for bulk Review 1 actions across multiple keywords."""

    keyword_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    review_status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None
    cleaning_status: Literal["ACTIVE", "IRRELEVANT"] | None = None


class BulkKeywordReviewResponse(BaseModel):
    """Result summary of a bulk Review 1 operation."""

    updated_count: int


class CleaningRequest(BaseModel):
    """Optional parameters when triggering KeywordCleaningService."""

    irrelevant_terms: list[str] = Field(default_factory=list)
    near_duplicate_threshold: float = Field(default=0.88, ge=0.5, le=1.0)


class CleaningSummary(BaseModel):
    """Summary counts produced by KeywordCleaningService."""

    research_run_id: uuid.UUID
    total_processed: int
    active_count: int
    duplicate_count: int
    near_duplicate_count: int
    irrelevant_count: int
    invalid_count: int
