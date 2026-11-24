"""Unit tests for the 15-node KeywordResearchGraph and its 3 mandatory HITL interrupts."""

from app.agents.checkpointer import create_memory_checkpointer
from app.agents.keyword_research_graph import GRAPH_NODE_NAMES, build_keyword_research_graph
from langgraph.types import Command


def test_graph_has_15_nodes_and_pauses_at_all_3_mandatory_interrupts() -> None:
    assert len(GRAPH_NODE_NAMES) == 15
    checkpointer = create_memory_checkpointer()
    graph = build_keyword_research_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "unit-thread-1"}}

    # Start -> pauses at Review 1
    graph.invoke({"research_run_id": "run-1", "node_history": []}, config=config)
    s1 = graph.get_state(config)
    assert s1.tasks[0].interrupts[0].value["gate"] == "REVIEW_1_KEYWORDS"

    # Resume Review 1 (APPROVE) -> pauses at Review 2
    graph.invoke(Command(resume={"decision": "APPROVE"}), config=config)
    s2 = graph.get_state(config)
    assert s2.tasks[0].interrupts[0].value["gate"] == "REVIEW_2_CLUSTERS"

    # Resume Review 2 (REGENERATE) -> loops back to cluster_keywords and pauses at Review 2 again
    graph.invoke(Command(resume={"decision": "REGENERATE"}), config=config)
    s2_retry = graph.get_state(config)
    assert s2_retry.tasks[0].interrupts[0].value["gate"] == "REVIEW_2_CLUSTERS"

    # Resume Review 2 (APPROVE) -> pauses at Review 3
    graph.invoke(Command(resume={"decision": "APPROVE"}), config=config)
    s3 = graph.get_state(config)
    assert s3.tasks[0].interrupts[0].value["gate"] == "REVIEW_3_BRIEFS"

    # Resume Review 3 (APPROVE) -> completes all 15 nodes
    final_state = graph.invoke(Command(resume={"decision": "APPROVE"}), config=config)
    assert final_state["current_node"] == "finalize_export_ready"
    for node_name in GRAPH_NODE_NAMES:
        assert node_name in final_state["node_history"]


def test_graph_reject_at_review_1_stops_execution() -> None:
    graph = build_keyword_research_graph(checkpointer=create_memory_checkpointer())
    config = {"configurable": {"thread_id": "unit-thread-reject"}}
    graph.invoke({"research_run_id": "run-2", "node_history": []}, config=config)

    final_state = graph.invoke(Command(resume={"decision": "REJECT"}), config=config)
    assert final_state["status"] == "CANCELLED"
    assert "collect_serp_snapshots" not in final_state["node_history"]
