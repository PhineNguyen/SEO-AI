"""Standardized Data Provenance DTOs shared across all SEO data connectors."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.utils.normalization import normalize_country_code, normalize_language_code

DeviceType = Literal["desktop", "mobile"]


class DataStatus(StrEnum):
    """Explicit data availability status to prevent confusing missing values with 0."""

    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    NOT_COLLECTED = "NOT_COLLECTED"
    SOURCE_ERROR = "SOURCE_ERROR"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MetricType(StrEnum):
    """Normalized SEO metric types collected across data providers."""

    SEARCH_VOLUME = "SEARCH_VOLUME"
    KEYWORD_DIFFICULTY = "KEYWORD_DIFFICULTY"
    CPC = "CPC"
    COMPETITION = "COMPETITION"
    GSC_IMPRESSIONS = "GSC_IMPRESSIONS"
    GSC_CLICKS = "GSC_CLICKS"
    GSC_CTR = "GSC_CTR"
    GSC_POSITION = "GSC_POSITION"


class KeywordCandidateType(StrEnum):
    """Classification of discovered keyword candidates."""

    SEED = "SEED"
    PRIMARY_CANDIDATE = "PRIMARY_CANDIDATE"
    RELATED = "RELATED"
    LONG_TAIL = "LONG_TAIL"
    QUESTION = "QUESTION"
    SUPPORTING = "SUPPORTING"
    VARIATION = "VARIATION"


class MetricRecord(BaseModel):
    """Single SEO metric observation carrying full provenance metadata."""

    metric_type: MetricType
    source_code: str = Field(min_length=1, max_length=50)
    source_record_id: str | None = None
    numeric_value: float | None = None
    raw_value: str | None = None
    unit: str = Field(min_length=1, max_length=50)
    currency: str | None = Field(default=None, max_length=10)
    country_code: str
    language_code: str
    data_status: DataStatus
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    extra_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("country_code")
    @classmethod
    def validate_country(cls, value: str) -> str:
        return normalize_country_code(value)

    @field_validator("language_code")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_code(value)

    @model_validator(mode="after")
    def validate_value_matches_status(self) -> "MetricRecord":
        if self.data_status == DataStatus.AVAILABLE and self.numeric_value is None:
            raise ValueError("AVAILABLE metric must provide a numeric_value")
        if self.data_status != DataStatus.AVAILABLE and self.numeric_value is not None:
            raise ValueError(
                "Missing or error metric must have numeric_value=None (never substitute 0)"
            )
        return self

    @classmethod
    def available(
        cls,
        *,
        metric_type: MetricType,
        source_code: str,
        numeric_value: float,
        unit: str,
        country_code: str,
        language_code: str,
        raw_value: str | None = None,
        currency: str | None = None,
        source_record_id: str | None = None,
        collected_at: datetime | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> "MetricRecord":
        """Build a MetricRecord with AVAILABLE status and explicit numeric value."""
        return cls(
            metric_type=metric_type,
            source_code=source_code,
            source_record_id=source_record_id,
            numeric_value=numeric_value,
            raw_value=raw_value if raw_value is not None else str(numeric_value),
            unit=unit,
            currency=currency,
            country_code=country_code,
            language_code=language_code,
            data_status=DataStatus.AVAILABLE,
            collected_at=collected_at or datetime.now(UTC),
            extra_metadata=extra_metadata or {},
        )

    @classmethod
    def missing(
        cls,
        *,
        metric_type: MetricType,
        source_code: str,
        unit: str,
        country_code: str,
        language_code: str,
        data_status: DataStatus = DataStatus.NOT_AVAILABLE,
        raw_value: str | None = None,
        currency: str | None = None,
        source_record_id: str | None = None,
        collected_at: datetime | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> "MetricRecord":
        """Build a MetricRecord representing missing/uncollected/errored data."""
        return cls(
            metric_type=metric_type,
            source_code=source_code,
            source_record_id=source_record_id,
            numeric_value=None,
            raw_value=raw_value,
            unit=unit,
            currency=currency,
            country_code=country_code,
            language_code=language_code,
            data_status=data_status,
            collected_at=collected_at or datetime.now(UTC),
            extra_metadata=extra_metadata or {},
        )


class KeywordIdeaRecord(BaseModel):
    """Normalized keyword candidate with associated metrics and provenance."""

    original_keyword: str = Field(min_length=1)
    keyword_type: KeywordCandidateType = KeywordCandidateType.RELATED
    source_code: str = Field(min_length=1, max_length=50)
    source_record_id: str | None = None
    country_code: str
    language_code: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metrics: list[MetricRecord] = Field(default_factory=list)
    source_intent: str | None = None
    serp_features: list[str] = Field(default_factory=list)
    extra_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("original_keyword")
    @classmethod
    def require_non_blank_keyword(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("original_keyword must not be blank")
        return value

    @field_validator("country_code")
    @classmethod
    def validate_country(cls, value: str) -> str:
        return normalize_country_code(value)

    @field_validator("language_code")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_code(value)


class SerpResultRecord(BaseModel):
    """Single organic or special SERP result item."""

    position: int = Field(ge=1)
    url: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    title: str
    snippet: str | None = None
    result_type: Literal[
        "ORGANIC",
        "FEATURED_SNIPPET",
        "VIDEO",
        "FORUM",
        "ECOMMERCE",
        "OTHER",
    ] = "ORGANIC"


class SerpSnapshotRecord(BaseModel):
    """Point-in-time SERP snapshot bound to country, language, device, and timestamp."""

    query_text: str = Field(min_length=1)
    provider_code: str = Field(min_length=1, max_length=50)
    country_code: str
    language_code: str
    location_name: str | None = None
    device: DeviceType = "desktop"
    serp_features: list[str] = Field(default_factory=list)
    results: list[SerpResultRecord] = Field(default_factory=list)
    data_status: DataStatus = DataStatus.AVAILABLE
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("country_code")
    @classmethod
    def validate_country(cls, value: str) -> str:
        return normalize_country_code(value)

    @field_validator("language_code")
    @classmethod
    def validate_language(cls, value: str) -> str:
        return normalize_language_code(value)


class ProviderErrorRecord(BaseModel):
    """Traceable error record returned alongside partial or failed provider runs."""

    provider_code: str
    error_code: str
    message: str
    retryable: bool = False
    http_status: int | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    context: dict[str, Any] = Field(default_factory=dict)


class ProviderResult[T](BaseModel):
    """Fault-isolated container returned by BaseDataProvider methods."""

    provider_code: str
    status: Literal["OK", "PARTIAL", "ERROR"] = "OK"
    items: list[T] = Field(default_factory=list)
    errors: list[ProviderErrorRecord] = Field(default_factory=list)
    quota_used: float | None = None
    quota_remaining: float | None = None
    duration_ms: float = 0.0
