"""Unit tests for Sprint 5 Hybrid Clustering similarity, F1 evaluation, and Prioritization."""

from app.connectors.embeddings import DeterministicHashEmbeddingProvider
from app.services.clustering_service import (
    compute_hybrid_similarity_matrix,
    compute_serp_overlap,
    evaluate_clustering_f1,
)
from app.services.prioritization_service import compute_priority_for_keyword


def test_hybrid_similarity_combines_serp_overlap_semantic_and_intent() -> None:
    embedder = DeterministicHashEmbeddingProvider()
    texts = [
        "phan mem crm tot nhat",
        "top phan mem crm cho doanh nghiep",
        "cach nau pho bo ha noi",
    ]
    embeddings = embedder.embed_texts(texts)
    serp_sets = [
        {"https://a.com/crm", "https://b.com/crm", "https://c.com/crm"},
        {"https://a.com/crm", "https://b.com/crm", "https://d.com/crm"},
        {"https://food.com/pho", "https://cook.com/pho"},
    ]
    intents = ["Commercial", "Commercial", "Informational"]

    hybrid, _, serp_mat, _ = compute_hybrid_similarity_matrix(embeddings, serp_sets, intents)
    assert compute_serp_overlap(serp_sets[0], serp_sets[1]) == 0.5
    assert serp_mat[0, 1] == 0.5
    assert hybrid[0, 1] > hybrid[0, 2] + 0.3


def test_evaluate_clustering_f1_perfect_and_partial() -> None:
    perfect = evaluate_clustering_f1(["crm", "crm", "pho", "pho"], [0, 0, 1, 1])
    assert perfect["pairwise_f1"] == 1.0

    partial = evaluate_clustering_f1(["crm", "crm", "pho", "pho"], [0, 0, 0, 1])
    assert 0.0 < partial["pairwise_f1"] < 1.0


def test_prioritization_handles_null_metrics_without_treating_as_zero() -> None:
    score_missing_kd, tier, reasoning = compute_priority_for_keyword(
        search_volume=5000,
        keyword_difficulty=None,
        cpc=None,
        primary_intent="Transactional",
    )
    assert float(score_missing_kd) >= 70.0
    assert tier == "P1"
    assert "NOT_AVAILABLE" in reasoning
    assert "not treated as 0" in reasoning

    # Changing weights shifts ranking
    score_vol_heavy, _, _ = compute_priority_for_keyword(
        search_volume=10000,
        keyword_difficulty=85,
        cpc=1.0,
        primary_intent="Informational",
        weights={"search_volume": 0.85, "keyword_difficulty": 0.05, "intent_value": 0.05, "cpc": 0.05},
    )
    score_kd_heavy, _, _ = compute_priority_for_keyword(
        search_volume=10000,
        keyword_difficulty=85,
        cpc=1.0,
        primary_intent="Informational",
        weights={"search_volume": 0.05, "keyword_difficulty": 0.85, "intent_value": 0.05, "cpc": 0.05},
    )
    assert score_vol_heavy > score_kd_heavy
