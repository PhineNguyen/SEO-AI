"""Hybrid Keyword Clustering Engine & Review 2 Manual Override Service (TASK-019, TASK-020)."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
from fastapi import HTTPException, status
from sklearn.cluster import AgglomerativeClustering
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.embeddings import BaseEmbeddingProvider, create_embedding_provider
from app.models.clustering import ClusterKeyword, ClusterReview, KeywordCluster
from app.models.project import DEFAULT_CLUSTERING_WEIGHTS, Project, ProjectSettings
from app.models.research import Keyword, KeywordMetric, ResearchRun
from app.models.serp import KeywordIntent, SerpResult, SerpSnapshot
from app.repositories.cluster_repository import ACTIVE_CLUSTER_STATUSES, ClusterRepository


def compute_serp_overlap(urls_a: set[str], urls_b: set[str]) -> float:
    """Compute Jaccard overlap between two sets of normalized Top-10 SERP URLs."""
    if not urls_a and not urls_b:
        return 0.0
    union = urls_a | urls_b
    if not union:
        return 0.0
    return len(urls_a & urls_b) / len(union)


def compute_intent_compatibility(intent_a: str | None, intent_b: str | None) -> float:
    """Return intent compatibility score in [0, 1]."""
    if not intent_a or not intent_b:
        return 0.5
    norm_a = intent_a.strip().title()
    norm_b = intent_b.strip().title()
    if norm_a == norm_b:
        return 1.0
    compatible_pairs = {
        frozenset(("Commercial", "Transactional")),
        frozenset(("Informational", "Commercial")),
    }
    if frozenset((norm_a, norm_b)) in compatible_pairs:
        return 0.4
    return 0.0


def compute_hybrid_similarity_matrix(
    embeddings: list[list[float]],
    serp_url_sets: list[set[str]],
    intents: list[str | None],
    weights: dict[str, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build hybrid similarity matrix combining semantic, SERP overlap, and intent signals."""
    w = weights or DEFAULT_CLUSTERING_WEIGHTS
    w_sem = float(w.get("semantic", 0.3))
    w_serp = float(w.get("serp_overlap", 0.5))
    w_intent = float(w.get("intent", 0.2))

    n = len(embeddings)
    if n == 0:
        empty = np.zeros((0, 0), dtype=float)
        return empty, empty, empty, empty

    emb_arr = np.array(embeddings, dtype=float)
    norms = np.linalg.norm(emb_arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normed = emb_arr / norms
    sem_matrix = np.clip((normed @ normed.T + 1.0) / 2.0, 0.0, 1.0)
    np.fill_diagonal(sem_matrix, 1.0)

    serp_matrix = np.zeros((n, n), dtype=float)
    intent_matrix = np.zeros((n, n), dtype=float)
    for i in range(n):
        serp_matrix[i, i] = 1.0
        intent_matrix[i, i] = 1.0
        for j in range(i + 1, n):
            overlap = compute_serp_overlap(serp_url_sets[i], serp_url_sets[j])
            serp_matrix[i, j] = serp_matrix[j, i] = overlap
            ic = compute_intent_compatibility(intents[i], intents[j])
            intent_matrix[i, j] = intent_matrix[j, i] = ic

    # If neither keyword has SERP URLs, redistribute SERP weight proportionally to semantic + intent
    hybrid = np.zeros((n, n), dtype=float)
    for i in range(n):
        hybrid[i, i] = 1.0
        for j in range(i + 1, n):
            has_serp = bool(serp_url_sets[i] or serp_url_sets[j])
            if has_serp:
                score = (
                    w_sem * sem_matrix[i, j]
                    + w_serp * serp_matrix[i, j]
                    + w_intent * intent_matrix[i, j]
                )
            else:
                denom = w_sem + w_intent
                score = (
                    (w_sem * sem_matrix[i, j] + w_intent * intent_matrix[i, j]) / denom
                    if denom > 0
                    else sem_matrix[i, j]
                )
            hybrid[i, j] = hybrid[j, i] = float(np.clip(score, 0.0, 1.0))

    return hybrid, sem_matrix, serp_matrix, intent_matrix


def evaluate_clustering_f1(
    true_labels: list[str], pred_labels: list[int | str]
) -> dict[str, float]:
    """Compute pairwise Precision, Recall, and F1 for clustering quality evaluation."""
    if len(true_labels) != len(pred_labels) or len(true_labels) < 2:
        return {"pairwise_precision": 0.0, "pairwise_recall": 0.0, "pairwise_f1": 0.0}

    tp = fp = fn = 0
    n = len(true_labels)
    for i in range(n):
        for j in range(i + 1, n):
            same_true = true_labels[i] == true_labels[j]
            same_pred = pred_labels[i] == pred_labels[j]
            if same_true and same_pred:
                tp += 1
            elif not same_true and same_pred:
                fp += 1
            elif same_true and not same_pred:
                fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return {
        "pairwise_precision": round(precision, 4),
        "pairwise_recall": round(recall, 4),
        "pairwise_f1": round(f1, 4),
    }


def _cluster_snapshot(cluster: KeywordCluster) -> dict[str, Any]:
    return {
        "cluster_id": str(cluster.id),
        "cluster_name": cluster.cluster_name,
        "primary_keyword_id": str(cluster.primary_keyword_id)
        if cluster.primary_keyword_id
        else None,
        "status": cluster.status,
        "origin": cluster.origin,
        "version": cluster.version,
        "member_keyword_ids": sorted(str(m.keyword_id) for m in cluster.members),
    }


class ClusteringService:
    """Runs hybrid clustering and handles Review 2 human edits with full audit trail."""

    def __init__(
        self,
        db: Session,
        embedding_provider: BaseEmbeddingProvider | None = None,
    ) -> None:
        self._db = db
        self._repo = ClusterRepository(db)
        self._embedder = embedding_provider or create_embedding_provider(get_settings())

    def _get_owned_run(self, research_run_id: UUID, owner_id: UUID) -> ResearchRun:
        run = self._db.scalar(
            select(ResearchRun)
            .join(Project, ResearchRun.project_id == Project.id)
            .where(ResearchRun.id == research_run_id, Project.owner_id == owner_id)
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found"
            )
        return run

    def _get_owned_cluster(self, cluster_id: UUID, owner_id: UUID) -> KeywordCluster:
        cluster = self._repo.get_by_id(cluster_id)
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Keyword cluster not found"
            )
        self._get_owned_run(cluster.research_run_id, owner_id)
        return cluster

    def run_clustering(
        self,
        research_run_id: UUID,
        owner_id: UUID,
        *,
        distance_threshold: float = 0.45,
        include_pending_keywords: bool = True,
    ) -> list[KeywordCluster]:
        """Cluster eligible keywords for a research run using Semantic + SERP Overlap + Intent."""
        run = self._get_owned_run(research_run_id, owner_id)
        settings_row = self._db.scalar(
            select(ProjectSettings).where(ProjectSettings.project_id == run.project_id)
        )
        weights = (
            dict(settings_row.clustering_weights)
            if settings_row and settings_row.clustering_weights
            else dict(DEFAULT_CLUSTERING_WEIGHTS)
        )

        # Mark existing active AI clusters as REPLACED/REJECTED? Better: retire prior ACTIVE clusters
        existing_active = self._repo.list_by_run(research_run_id, active_only=True)
        for old_cluster in existing_active:
            old_cluster.status = "REJECTED"
        self._db.flush()

        allowed_reviews = ("APPROVED", "PENDING") if include_pending_keywords else ("APPROVED",)
        keywords = list(
            self._db.scalars(
                select(Keyword)
                .where(
                    Keyword.research_run_id == research_run_id,
                    Keyword.cleaning_status.in_(("ACTIVE", "RAW")),
                    Keyword.review_status.in_(allowed_reviews),
                )
                .order_by(Keyword.created_at.asc())
            ).all()
        )
        if not keywords:
            return []

        kw_ids = [kw.id for kw in keywords]

        # Fetch latest SERP normalized URLs per keyword
        serp_urls_by_kw: dict[UUID, set[str]] = defaultdict(set)
        snapshots = list(
            self._db.scalars(
                select(SerpSnapshot)
                .where(
                    SerpSnapshot.research_run_id == research_run_id,
                    SerpSnapshot.keyword_id.in_(kw_ids),
                )
                .order_by(SerpSnapshot.collected_at.desc())
            ).all()
        )
        latest_snap_by_kw: dict[UUID, UUID] = {}
        for snap in snapshots:
            if snap.keyword_id not in latest_snap_by_kw:
                latest_snap_by_kw[snap.keyword_id] = snap.id
        if latest_snap_by_kw:
            snap_to_kw = {sid: kid for kid, sid in latest_snap_by_kw.items()}
            results = list(
                self._db.scalars(
                    select(SerpResult).where(
                        SerpResult.serp_snapshot_id.in_(list(latest_snap_by_kw.values()))
                    )
                ).all()
            )
            for res in results:
                serp_urls_by_kw[snap_to_kw[res.serp_snapshot_id]].add(res.normalized_url)

        # Fetch current intent per keyword
        intent_by_kw: dict[UUID, str | None] = {}
        intents_rows = list(
            self._db.scalars(
                select(KeywordIntent).where(
                    KeywordIntent.keyword_id.in_(kw_ids),
                    KeywordIntent.is_current.is_(True),
                )
            ).all()
        )
        for row in intents_rows:
            intent_by_kw[row.keyword_id] = row.primary_intent.strip().title()

        # Fetch latest search volume per keyword for primary selection
        volume_by_kw: dict[UUID, float] = {}
        vol_rows = list(
            self._db.scalars(
                select(KeywordMetric)
                .where(
                    KeywordMetric.keyword_id.in_(kw_ids),
                    KeywordMetric.metric_type == "SEARCH_VOLUME",
                    KeywordMetric.data_status == "AVAILABLE",
                )
                .order_by(KeywordMetric.collected_at.desc())
            ).all()
        )
        for vrow in vol_rows:
            if vrow.keyword_id not in volume_by_kw and vrow.numeric_value is not None:
                volume_by_kw[vrow.keyword_id] = float(vrow.numeric_value)

        texts = [kw.normalized_keyword or kw.original_keyword for kw in keywords]
        embeddings = self._embedder.embed_texts(texts)
        serp_sets = [serp_urls_by_kw[kw.id] for kw in keywords]
        intent_list = [intent_by_kw.get(kw.id) for kw in keywords]

        hybrid, sem_mat, serp_mat, intent_mat = compute_hybrid_similarity_matrix(
            embeddings, serp_sets, intent_list, weights=weights
        )

        if len(keywords) == 1:
            labels = [0]
        else:
            distance_matrix = np.clip(1.0 - hybrid, 0.0, 1.0)
            model = AgglomerativeClustering(
                n_clusters=None,
                metric="precomputed",
                linkage="average",
                distance_threshold=distance_threshold,
            )
            labels = [int(lbl) for lbl in model.fit_predict(distance_matrix)]

        groups: dict[int, list[int]] = defaultdict(list)
        for idx, lbl in enumerate(labels):
            groups[lbl].append(idx)

        created_clusters: list[KeywordCluster] = []
        for group_indices in groups.values():
            # Select primary keyword: highest search_volume, tie-break shortest text
            primary_idx = max(
                group_indices,
                key=lambda i: (
                    volume_by_kw.get(keywords[i].id, -1.0),
                    -len(keywords[i].normalized_keyword),
                ),
            )
            primary_kw = keywords[primary_idx]

            group_intents = [intent_list[i] for i in group_indices if intent_list[i]]
            cluster_intent = (
                Counter(group_intents).most_common(1)[0][0] if group_intents else None
            )

            if len(group_indices) > 1:
                pair_hybrid = [
                    hybrid[i, j]
                    for a, i in enumerate(group_indices)
                    for j in group_indices[a + 1 :]
                ]
                pair_sem = [
                    sem_mat[i, j]
                    for a, i in enumerate(group_indices)
                    for j in group_indices[a + 1 :]
                ]
                pair_serp = [
                    serp_mat[i, j]
                    for a, i in enumerate(group_indices)
                    for j in group_indices[a + 1 :]
                ]
                avg_hybrid = float(np.mean(pair_hybrid))
                avg_sem = float(np.mean(pair_sem))
                avg_serp = float(np.mean(pair_serp))
            else:
                avg_hybrid = avg_sem = avg_serp = 1.0

            reasoning = (
                f"Grouped {len(group_indices)} keyword(s) around '{primary_kw.original_keyword}' "
                f"using hybrid similarity (avg={avg_hybrid:.2f}, semantic={avg_sem:.2f}, "
                f"serp_overlap={avg_serp:.2f}, provider={self._embedder.provider_name})."
            )
            cluster = KeywordCluster(
                research_run_id=research_run_id,
                cluster_name=primary_kw.original_keyword.title(),
                primary_keyword_id=primary_kw.id,
                cluster_intent=cluster_intent,
                confidence=Decimal(f"{min(max(avg_hybrid, 0.0), 1.0):.3f}"),
                clustering_reasoning=reasoning,
                scoring_breakdown={
                    "weights": weights,
                    "avg_hybrid_similarity": round(avg_hybrid, 4),
                    "avg_semantic_similarity": round(avg_sem, 4),
                    "avg_serp_overlap": round(avg_serp, 4),
                    "embedding_provider": self._embedder.provider_name,
                },
                status="ACTIVE",
                origin="AI",
                version=1,
            )
            self._repo.create_cluster(cluster)

            for idx in group_indices:
                kw = keywords[idx]
                role = "PRIMARY" if idx == primary_idx else "SECONDARY"
                sim_val = float(hybrid[idx, primary_idx])
                sem_val = float(sem_mat[idx, primary_idx])
                serp_val = float(serp_mat[idx, primary_idx])
                int_val = float(intent_mat[idx, primary_idx])
                self._repo.add_member(
                    ClusterKeyword(
                        cluster_id=cluster.id,
                        keyword_id=kw.id,
                        role=role,
                        similarity_score=Decimal(f"{sim_val:.4f}"),
                        serp_overlap_score=Decimal(f"{serp_val:.4f}"),
                        semantic_score=Decimal(f"{sem_val:.4f}"),
                        intent_score=Decimal(f"{int_val:.4f}"),
                        is_manual_override=False,
                    )
                )
            created_clusters.append(cluster)

        self._db.commit()
        return self._repo.list_by_run(research_run_id, active_only=True)

    def list_clusters(
        self, research_run_id: UUID, owner_id: UUID, *, active_only: bool = True
    ) -> list[KeywordCluster]:
        self._get_owned_run(research_run_id, owner_id)
        return self._repo.list_by_run(research_run_id, active_only=active_only)

    def get_cluster(self, cluster_id: UUID, owner_id: UUID) -> KeywordCluster:
        return self._get_owned_cluster(cluster_id, owner_id)

    def approve_cluster(
        self, cluster_id: UUID, reviewer_id: UUID, notes: str | None = None
    ) -> KeywordCluster:
        cluster = self._get_owned_cluster(cluster_id, reviewer_id)
        before = _cluster_snapshot(cluster)
        cluster.status = "APPROVED"
        cluster.version += 1
        self._repo.add_review(
            ClusterReview(
                cluster_id=cluster.id,
                action="APPROVE",
                before_snapshot=before,
                after_snapshot=_cluster_snapshot(cluster),
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return self._repo.get_by_id(cluster.id)  # type: ignore[return-value]

    def reject_cluster(
        self, cluster_id: UUID, reviewer_id: UUID, notes: str | None = None
    ) -> KeywordCluster:
        cluster = self._get_owned_cluster(cluster_id, reviewer_id)
        before = _cluster_snapshot(cluster)
        cluster.status = "REJECTED"
        cluster.version += 1
        self._repo.add_review(
            ClusterReview(
                cluster_id=cluster.id,
                action="REJECT",
                before_snapshot=before,
                after_snapshot=_cluster_snapshot(cluster),
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return self._repo.get_by_id(cluster.id)  # type: ignore[return-value]

    def rename_cluster(
        self, cluster_id: UUID, reviewer_id: UUID, new_name: str, notes: str | None = None
    ) -> KeywordCluster:
        cluster = self._get_owned_cluster(cluster_id, reviewer_id)
        before = _cluster_snapshot(cluster)
        cluster.cluster_name = new_name.strip()
        cluster.origin = "HUMAN"
        cluster.version += 1
        self._repo.add_review(
            ClusterReview(
                cluster_id=cluster.id,
                action="RENAME",
                before_snapshot=before,
                after_snapshot=_cluster_snapshot(cluster),
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return self._repo.get_by_id(cluster.id)  # type: ignore[return-value]

    def change_primary_keyword(
        self,
        cluster_id: UUID,
        reviewer_id: UUID,
        primary_keyword_id: UUID,
        notes: str | None = None,
    ) -> KeywordCluster:
        cluster = self._get_owned_cluster(cluster_id, reviewer_id)
        member_ids = {m.keyword_id for m in cluster.members}
        if primary_keyword_id not in member_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Primary keyword must belong to the cluster",
            )
        before = _cluster_snapshot(cluster)
        cluster.primary_keyword_id = primary_keyword_id
        cluster.origin = "HUMAN"
        cluster.version += 1
        for m in cluster.members:
            m.role = "PRIMARY" if m.keyword_id == primary_keyword_id else "SECONDARY"
            m.is_manual_override = True
        self._repo.add_review(
            ClusterReview(
                cluster_id=cluster.id,
                action="CHANGE_PRIMARY",
                before_snapshot=before,
                after_snapshot=_cluster_snapshot(cluster),
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return self._repo.get_by_id(cluster.id)  # type: ignore[return-value]

    def move_keyword(
        self,
        keyword_id: UUID,
        source_cluster_id: UUID,
        target_cluster_id: UUID,
        reviewer_id: UUID,
        notes: str | None = None,
    ) -> KeywordCluster:
        if source_cluster_id == target_cluster_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and target cluster must be different",
            )
        source = self._get_owned_cluster(source_cluster_id, reviewer_id)
        target = self._get_owned_cluster(target_cluster_id, reviewer_id)
        if source.research_run_id != target.research_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Clusters must belong to the same research run",
            )
        if target.status not in ACTIVE_CLUSTER_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target cluster must be ACTIVE or APPROVED",
            )

        member = next((m for m in source.members if m.keyword_id == keyword_id), None)
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Keyword not found in source cluster",
            )

        before_src = _cluster_snapshot(source)
        before_tgt = _cluster_snapshot(target)

        self._repo.delete_member(member)
        self._repo.add_member(
            ClusterKeyword(
                cluster_id=target.id,
                keyword_id=keyword_id,
                role="SECONDARY",
                is_manual_override=True,
            )
        )

        # Re-assign source primary if needed
        remaining = [m for m in source.members if m.keyword_id != keyword_id]
        if source.primary_keyword_id == keyword_id:
            source.primary_keyword_id = remaining[0].keyword_id if remaining else None
            if remaining:
                remaining[0].role = "PRIMARY"
        source.origin = "HUMAN"
        source.version += 1
        target.origin = "HUMAN"
        target.version += 1
        self._db.flush()

        refreshed_src = self._repo.get_by_id(source.id)
        refreshed_tgt = self._repo.get_by_id(target.id)
        self._repo.add_review(
            ClusterReview(
                cluster_id=source.id,
                action="MOVE_KEYWORD",
                before_snapshot=before_src,
                after_snapshot=_cluster_snapshot(refreshed_src),  # type: ignore[arg-type]
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._repo.add_review(
            ClusterReview(
                cluster_id=target.id,
                action="MOVE_KEYWORD",
                before_snapshot=before_tgt,
                after_snapshot=_cluster_snapshot(refreshed_tgt),  # type: ignore[arg-type]
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return self._repo.get_by_id(target.id)  # type: ignore[return-value]

    def merge_clusters(
        self,
        source_cluster_ids: list[UUID],
        reviewer_id: UUID,
        target_cluster_name: str | None = None,
        notes: str | None = None,
    ) -> KeywordCluster:
        unique_ids = list(dict.fromkeys(source_cluster_ids))
        if len(unique_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least 2 distinct clusters are required to merge",
            )
        clusters = [self._get_owned_cluster(cid, reviewer_id) for cid in unique_ids]
        run_ids = {c.research_run_id for c in clusters}
        if len(run_ids) != 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All merged clusters must belong to the same research run",
            )

        first = clusters[0]
        all_kw_ids: list[UUID] = []
        for c in clusters:
            for m in c.members:
                if m.keyword_id not in all_kw_ids:
                    all_kw_ids.append(m.keyword_id)

        merged = KeywordCluster(
            research_run_id=first.research_run_id,
            cluster_name=(target_cluster_name or first.cluster_name).strip(),
            primary_keyword_id=first.primary_keyword_id
            or (all_kw_ids[0] if all_kw_ids else None),
            cluster_intent=first.cluster_intent,
            confidence=first.confidence,
            clustering_reasoning=f"Merged from {len(clusters)} clusters by reviewer.",
            scoring_breakdown={"merged_from": [str(c.id) for c in clusters]},
            status="ACTIVE",
            origin="HUMAN",
            version=1,
        )
        self._repo.create_cluster(merged)
        for kw_id in all_kw_ids:
            self._repo.add_member(
                ClusterKeyword(
                    cluster_id=merged.id,
                    keyword_id=kw_id,
                    role="PRIMARY" if kw_id == merged.primary_keyword_id else "SECONDARY",
                    is_manual_override=True,
                )
            )

        for c in clusters:
            before = _cluster_snapshot(c)
            c.status = "MERGED"
            c.version += 1
            self._repo.add_review(
                ClusterReview(
                    cluster_id=c.id,
                    action="MERGE",
                    before_snapshot=before,
                    after_snapshot={
                        **_cluster_snapshot(c),
                        "merged_into_cluster_id": str(merged.id),
                    },
                    reviewer_id=reviewer_id,
                    notes=notes,
                )
            )

        self._db.flush()
        refreshed_merged = self._repo.get_by_id(merged.id)
        self._repo.add_review(
            ClusterReview(
                cluster_id=merged.id,
                action="MERGE",
                before_snapshot={"source_cluster_ids": [str(c.id) for c in clusters]},
                after_snapshot=_cluster_snapshot(refreshed_merged),  # type: ignore[arg-type]
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return self._repo.get_by_id(merged.id)  # type: ignore[return-value]

    def split_cluster(
        self,
        cluster_id: UUID,
        keyword_ids_to_extract: list[UUID],
        new_cluster_name: str,
        reviewer_id: UUID,
        notes: str | None = None,
    ) -> tuple[KeywordCluster, KeywordCluster]:
        cluster = self._get_owned_cluster(cluster_id, reviewer_id)
        extract_set = set(keyword_ids_to_extract)
        member_map = {m.keyword_id: m for m in cluster.members}
        if not extract_set.issubset(member_map.keys()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All extracted keywords must belong to the source cluster",
            )
        if len(extract_set) == len(member_map):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot extract all keywords from a cluster; leave at least one remaining",
            )

        before = _cluster_snapshot(cluster)
        new_primary = next(iter(keyword_ids_to_extract))
        new_cluster = KeywordCluster(
            research_run_id=cluster.research_run_id,
            cluster_name=new_cluster_name.strip(),
            primary_keyword_id=new_primary,
            cluster_intent=cluster.cluster_intent,
            confidence=cluster.confidence,
            clustering_reasoning=f"Split from cluster '{cluster.cluster_name}' by reviewer.",
            scoring_breakdown={"split_from": str(cluster.id)},
            status="ACTIVE",
            origin="HUMAN",
            version=1,
        )
        self._repo.create_cluster(new_cluster)

        for kw_id in extract_set:
            self._repo.delete_member(member_map[kw_id])
            self._repo.add_member(
                ClusterKeyword(
                    cluster_id=new_cluster.id,
                    keyword_id=kw_id,
                    role="PRIMARY" if kw_id == new_primary else "SECONDARY",
                    is_manual_override=True,
                )
            )

        remaining_ids = [kid for kid in member_map if kid not in extract_set]
        if cluster.primary_keyword_id in extract_set:
            cluster.primary_keyword_id = remaining_ids[0]
            member_map[remaining_ids[0]].role = "PRIMARY"
        cluster.origin = "HUMAN"
        cluster.version += 1
        self._db.flush()

        refreshed_orig = self._repo.get_by_id(cluster.id)
        refreshed_new = self._repo.get_by_id(new_cluster.id)
        self._repo.add_review(
            ClusterReview(
                cluster_id=cluster.id,
                action="SPLIT",
                before_snapshot=before,
                after_snapshot={
                    **_cluster_snapshot(refreshed_orig),  # type: ignore[arg-type]
                    "new_cluster_id": str(new_cluster.id),
                },
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._repo.add_review(
            ClusterReview(
                cluster_id=new_cluster.id,
                action="SPLIT",
                before_snapshot={"split_from_cluster_id": str(cluster.id)},
                after_snapshot=_cluster_snapshot(refreshed_new),  # type: ignore[arg-type]
                reviewer_id=reviewer_id,
                notes=notes,
            )
        )
        self._db.commit()
        return (
            self._repo.get_by_id(cluster.id),  # type: ignore[return-value]
            self._repo.get_by_id(new_cluster.id),  # type: ignore[return-value]
        )
