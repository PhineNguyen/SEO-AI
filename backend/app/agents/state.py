"""Pointer-based LangGraph state definition for KeywordResearchGraph (TASK-022)."""

from typing import Any, TypedDict


class KeywordResearchState(TypedDict, total=False):
    """Lightweight pointer-based workflow state (large payloads stay in PostgreSQL)."""

    project_id: str
    research_run_id: str
    owner_id: str
    workflow_execution_id: str
    langgraph_thread_id: str

    current_node: str
    status: str

    # Stage counters / pointers
    seed_count: int
    collected_keyword_count: int
    active_keyword_count: int
    serp_snapshot_count: int
    competitor_page_count: int
    intent_classified_count: int
    cluster_count: int
    prioritized_keyword_count: int
    brief_count: int
    validated_brief_count: int

    # HITL review tracking
    last_review_gate: str | None
    last_review_decision: str | None
    last_review_comment: str | None

    # Execution trace
    node_history: list[str]
    errors: list[dict[str, Any]]
