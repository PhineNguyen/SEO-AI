"""Pydantic v2 schemas for Evidence-based Content Briefs, Review 3, and Export Jobs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BriefSectionInput(BaseModel):
    heading_level: int = Field(default=2, ge=2, le=3)
    heading_text: str = Field(min_length=1, max_length=255)
    section_order: int = Field(default=1, ge=1)
    key_points: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)


class BriefFaqInput(BaseModel):
    question: str = Field(min_length=3)
    answer_guidance: str = ""
    source_evidence: str = ""
    display_order: int = Field(default=1, ge=1)


class ContentBriefDraft(BaseModel):
    """Structured draft produced by an AI or deterministic brief generator."""

    search_intent: str
    target_audience: str
    content_objective: str
    content_angle: str
    suggested_seo_title: str
    meta_description: str
    h1: str
    competitor_insights: list[dict[str, Any]] = Field(default_factory=list)
    important_topics: list[str] = Field(default_factory=list)
    content_recommendations: list[str] = Field(default_factory=list)
    keyword_coverage: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[BriefSectionInput] = Field(default_factory=list)
    faqs: list[BriefFaqInput] = Field(default_factory=list)
    model_version: str = "evidence-brief-v1"
    prompt_version: str = "brief-prompt-v1"


class BriefSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    heading_level: int
    heading_text: str
    section_order: int
    key_points: list[str]
    target_keywords: list[str]


class BriefFaqRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question: str
    answer_guidance: str
    source_evidence: str
    display_order: int


class BriefKeywordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    keyword_id: UUID
    usage_role: str
    placement_hint: str | None = None


class ContentBriefRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    research_run_id: UUID
    cluster_id: UUID
    primary_keyword_id: UUID
    version: int
    is_current: bool
    origin: str
    status: str
    search_intent: str
    target_audience: str
    content_objective: str
    content_angle: str
    suggested_seo_title: str
    meta_description: str
    h1: str
    competitor_insights: list[dict[str, Any]]
    important_topics: list[str]
    content_recommendations: list[str]
    keyword_coverage: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    model_version: str
    prompt_version: str
    created_at: datetime
    updated_at: datetime
    brief_keywords: list[BriefKeywordRead] = Field(default_factory=list)
    sections: list[BriefSectionRead] = Field(default_factory=list)
    faqs: list[BriefFaqRead] = Field(default_factory=list)


class BriefEditRequest(BaseModel):
    suggested_seo_title: str | None = Field(default=None, max_length=255)
    meta_description: str | None = None
    h1: str | None = Field(default=None, max_length=255)
    content_angle: str | None = None
    target_audience: str | None = None
    content_objective: str | None = None
    sections: list[BriefSectionInput] | None = None
    faqs: list[BriefFaqInput] | None = None
    feedback_notes: str | None = None


class BriefActionRequest(BaseModel):
    feedback_notes: str | None = None


class ExportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    research_run_id: UUID
    export_type: str
    status: str
    file_path: str | None = None
    google_spreadsheet_id: str | None = None
    google_spreadsheet_url: str | None = None
    error_message: str | None = None
    created_by: UUID
    created_at: datetime
    completed_at: datetime | None = None
