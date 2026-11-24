"""Pydantic v2 schemas for LangGraph Workflow Control & HITL Resume APIs (TASK-024)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStartRequest(BaseModel):
    use_async_worker: bool = False


class WorkflowResumeRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT", "EDIT_AND_APPROVE", "REGENERATE"] = "APPROVE"
    comment: str | None = None
    summary_diff: dict[str, Any] = Field(default_factory=dict)
    use_async_worker: bool = False


class WorkflowCheckpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_name: str
    checkpoint_key: str
    status: str
    metrics_summary: dict[str, Any]
    created_at: datetime


class ReviewDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    review_gate: str
    decision: str
    summary_diff: dict[str, Any]
    reviewer_id: UUID
    comment: str | None = None
    decided_at: datetime


class WorkflowExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    research_run_id: UUID
    langgraph_thread_id: str
    celery_task_id: str | None = None
    current_node: str | None = None
    status: str
    error_message: str | None = None
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    checkpoints: list[WorkflowCheckpointRead] = Field(default_factory=list)
    decisions: list[ReviewDecisionRead] = Field(default_factory=list)
