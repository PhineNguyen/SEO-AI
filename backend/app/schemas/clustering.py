"""Pydantic v2 schemas for Hybrid Keyword Clustering, Review 2, and Prioritization."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RunClusteringRequest(BaseModel):
    distance_threshold: float = Field(default=0.45, ge=0.05, le=0.95)
    include_pending_keywords: bool = True


class ClusterKeywordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cluster_id: UUID
    keyword_id: UUID
    original_keyword: str | None = None
    normalized_keyword: str | None = None
    role: str
    similarity_score: Decimal | None = None
    serp_overlap_score: Decimal | None = None
    semantic_score: Decimal | None = None
    intent_score: Decimal | None = None
    is_manual_override: bool


class ClusterReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cluster_id: UUID
    action: str
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    reviewer_id: UUID
    notes: str | None = None
    created_at: datetime


class KeywordClusterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    research_run_id: UUID
    cluster_name: str
    primary_keyword_id: UUID | None = None
    cluster_intent: str | None = None
    confidence: Decimal | None = None
    clustering_reasoning: str
    scoring_breakdown: dict[str, Any]
    status: str
    origin: str
    version: int
    created_at: datetime
    updated_at: datetime
    members: list[ClusterKeywordRead] = Field(default_factory=list)


class ClusterStatusActionRequest(BaseModel):
    notes: str | None = None


class RenameClusterRequest(BaseModel):
    cluster_name: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class ChangePrimaryRequest(BaseModel):
    primary_keyword_id: UUID
    notes: str | None = None


class MoveKeywordRequest(BaseModel):
    keyword_id: UUID
    source_cluster_id: UUID
    target_cluster_id: UUID
    notes: str | None = None


class MergeClustersRequest(BaseModel):
    source_cluster_ids: list[UUID] = Field(min_length=2)
    target_cluster_name: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class SplitClusterRequest(BaseModel):
    keyword_ids_to_extract: list[UUID] = Field(min_length=1)
    new_cluster_name: str = Field(min_length=1, max_length=255)
    notes: str | None = None


class PrioritizationSummaryResponse(BaseModel):
    research_run_id: UUID
    scored_keywords: int
    weights_used: dict[str, float]
    top_keywords: list[dict[str, Any]]
