"""15-node LangGraph KeywordResearchGraph with 3 mandatory HITL interrupt gates (TASK-023)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.state import KeywordResearchState

GRAPH_NODE_NAMES: tuple[str, ...] = (
    "load_context",
    "expand_seeds",
    "collect_keyword_metrics",
    "clean_and_normalize",
    "review_1_keywords",
    "collect_serp_snapshots",
    "fetch_competitor_headings",
    "classify_search_intent",
    "cluster_keywords",
    "review_2_clusters",
    "prioritize_keywords",
    "generate_content_briefs",
    "validate_content_briefs",
    "review_3_briefs",
    "finalize_export_ready",
)

NodeHandler = Callable[[KeywordResearchState], dict[str, Any]]


def _append_history(state: KeywordResearchState, node_name: str) -> list[str]:
    return [*list(state.get("node_history", [])), node_name]


def _make_work_node(
    node_name: str,
    handler: NodeHandler | None = None,
) -> NodeHandler:
    def _node(state: KeywordResearchState) -> dict[str, Any]:
        updates: dict[str, Any] = {
            "current_node": node_name,
            "status": "RUNNING",
            "node_history": _append_history(state, node_name),
        }
        if handler is not None:
            result = handler(state)
            if isinstance(result, dict):
                updates.update(result)
        return updates

    return _node


def _make_review_node(node_name: str, gate_name: str, waiting_status: str) -> NodeHandler:
    def _review_node(state: KeywordResearchState) -> dict[str, Any]:
        payload = {
            "gate": gate_name,
            "waiting_status": waiting_status,
            "research_run_id": state.get("research_run_id"),
            "current_node": node_name,
        }
        resume_value = interrupt(payload)
        if isinstance(resume_value, dict):
            decision = str(resume_value.get("decision", "APPROVE")).upper()
            comment = resume_value.get("comment")
        else:
            decision = str(resume_value or "APPROVE").upper()
            comment = None
        return {
            "current_node": node_name,
            "status": "CANCELLED" if decision == "REJECT" else "RUNNING",
            "last_review_gate": gate_name,
            "last_review_decision": decision,
            "last_review_comment": comment,
            "node_history": _append_history(state, node_name),
        }

    return _review_node


def _route_after_review_1(state: KeywordResearchState) -> str:
    if state.get("last_review_decision") == "REJECT":
        return END
    return "collect_serp_snapshots"


def _route_after_review_2(state: KeywordResearchState) -> str:
    decision = state.get("last_review_decision")
    if decision == "REJECT":
        return END
    if decision == "REGENERATE":
        return "cluster_keywords"
    return "prioritize_keywords"


def _route_after_review_3(state: KeywordResearchState) -> str:
    decision = state.get("last_review_decision")
    if decision == "REJECT":
        return END
    if decision == "REGENERATE":
        return "generate_content_briefs"
    return "finalize_export_ready"


def build_keyword_research_graph(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    node_handlers: dict[str, NodeHandler] | None = None,
):
    """Build and compile the 15-node KeywordResearchGraph with 3 mandatory HITL interrupts."""
    handlers = node_handlers or {}
    builder: StateGraph = StateGraph(KeywordResearchState)

    # 12 work nodes
    work_nodes = [
        "load_context",
        "expand_seeds",
        "collect_keyword_metrics",
        "clean_and_normalize",
        "collect_serp_snapshots",
        "fetch_competitor_headings",
        "classify_search_intent",
        "cluster_keywords",
        "prioritize_keywords",
        "generate_content_briefs",
        "validate_content_briefs",
        "finalize_export_ready",
    ]
    for name in work_nodes:
        builder.add_node(name, _make_work_node(name, handlers.get(name)))

    # 3 mandatory HITL interrupt nodes
    builder.add_node(
        "review_1_keywords",
        _make_review_node("review_1_keywords", "REVIEW_1_KEYWORDS", "WAITING_REVIEW_1"),
    )
    builder.add_node(
        "review_2_clusters",
        _make_review_node("review_2_clusters", "REVIEW_2_CLUSTERS", "WAITING_REVIEW_2"),
    )
    builder.add_node(
        "review_3_briefs",
        _make_review_node("review_3_briefs", "REVIEW_3_BRIEFS", "WAITING_REVIEW_3"),
    )

    # Linear + conditional edges
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "expand_seeds")
    builder.add_edge("expand_seeds", "collect_keyword_metrics")
    builder.add_edge("collect_keyword_metrics", "clean_and_normalize")
    builder.add_edge("clean_and_normalize", "review_1_keywords")

    builder.add_conditional_edges(
        "review_1_keywords",
        _route_after_review_1,
        {"collect_serp_snapshots": "collect_serp_snapshots", END: END},
    )

    builder.add_edge("collect_serp_snapshots", "fetch_competitor_headings")
    builder.add_edge("fetch_competitor_headings", "classify_search_intent")
    builder.add_edge("classify_search_intent", "cluster_keywords")
    builder.add_edge("cluster_keywords", "review_2_clusters")

    builder.add_conditional_edges(
        "review_2_clusters",
        _route_after_review_2,
        {
            "prioritize_keywords": "prioritize_keywords",
            "cluster_keywords": "cluster_keywords",
            END: END,
        },
    )

    builder.add_edge("prioritize_keywords", "generate_content_briefs")
    builder.add_edge("generate_content_briefs", "validate_content_briefs")
    builder.add_edge("validate_content_briefs", "review_3_briefs")

    builder.add_conditional_edges(
        "review_3_briefs",
        _route_after_review_3,
        {
            "finalize_export_ready": "finalize_export_ready",
            "generate_content_briefs": "generate_content_briefs",
            END: END,
        },
    )

    builder.add_edge("finalize_export_ready", END)

    return builder.compile(checkpointer=checkpointer)
