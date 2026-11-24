"""REST API endpoints for Sprint 5 (Hybrid Clustering, Review 2, and Prioritization)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.clustering import KeywordCluster
from app.models.research import Keyword
from app.models.user import User
from app.schemas.clustering import (
    ChangePrimaryRequest,
    ClusterKeywordRead,
    ClusterStatusActionRequest,
    KeywordClusterRead,
    MergeClustersRequest,
    MoveKeywordRequest,
    PrioritizationSummaryResponse,
    RenameClusterRequest,
    RunClusteringRequest,
    SplitClusterRequest,
)
from app.services.clustering_service import ClusteringService
from app.services.prioritization_service import PrioritizationService

router = APIRouter(tags=["Clusters & Prioritization"])


def _serialize_cluster(db: Session, cluster: KeywordCluster) -> KeywordClusterRead:
    kw_ids = [m.keyword_id for m in cluster.members]
    kw_map = (
        {
            kw.id: kw
            for kw in db.scalars(select(Keyword).where(Keyword.id.in_(kw_ids))).all()
        }
        if kw_ids
        else {}
    )
    members = [
        ClusterKeywordRead(
            id=m.id,
            cluster_id=m.cluster_id,
            keyword_id=m.keyword_id,
            original_keyword=kw_map[m.keyword_id].original_keyword
            if m.keyword_id in kw_map
            else None,
            normalized_keyword=kw_map[m.keyword_id].normalized_keyword
            if m.keyword_id in kw_map
            else None,
            role=m.role,
            similarity_score=m.similarity_score,
            serp_overlap_score=m.serp_overlap_score,
            semantic_score=m.semantic_score,
            intent_score=m.intent_score,
            is_manual_override=m.is_manual_override,
        )
        for m in cluster.members
    ]
    return KeywordClusterRead(
        id=cluster.id,
        research_run_id=cluster.research_run_id,
        cluster_name=cluster.cluster_name,
        primary_keyword_id=cluster.primary_keyword_id,
        cluster_intent=cluster.cluster_intent,
        confidence=cluster.confidence,
        clustering_reasoning=cluster.clustering_reasoning,
        scoring_breakdown=cluster.scoring_breakdown,
        status=cluster.status,
        origin=cluster.origin,
        version=cluster.version,
        created_at=cluster.created_at,
        updated_at=cluster.updated_at,
        members=members,
    )


@router.post("/research-runs/{run_id}/clusters/run", response_model=list[KeywordClusterRead])
def run_clustering(
    run_id: UUID,
    payload: RunClusteringRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[KeywordClusterRead]:
    clusters = ClusteringService(db).run_clustering(
        run_id,
        current_user.id,
        distance_threshold=payload.distance_threshold,
        include_pending_keywords=payload.include_pending_keywords,
    )
    return [_serialize_cluster(db, c) for c in clusters]


@router.get("/research-runs/{run_id}/clusters", response_model=list[KeywordClusterRead])
def list_clusters(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    active_only: bool = Query(default=True),
) -> list[KeywordClusterRead]:
    clusters = ClusteringService(db).list_clusters(
        run_id, current_user.id, active_only=active_only
    )
    return [_serialize_cluster(db, c) for c in clusters]


@router.get("/clusters/{cluster_id}", response_model=KeywordClusterRead)
def get_cluster(
    cluster_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).get_cluster(cluster_id, current_user.id)
    return _serialize_cluster(db, cluster)


@router.post("/clusters/{cluster_id}/approve", response_model=KeywordClusterRead)
def approve_cluster(
    cluster_id: UUID,
    payload: ClusterStatusActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).approve_cluster(cluster_id, current_user.id, payload.notes)
    return _serialize_cluster(db, cluster)


@router.post("/clusters/{cluster_id}/reject", response_model=KeywordClusterRead)
def reject_cluster(
    cluster_id: UUID,
    payload: ClusterStatusActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).reject_cluster(cluster_id, current_user.id, payload.notes)
    return _serialize_cluster(db, cluster)


@router.patch("/clusters/{cluster_id}/rename", response_model=KeywordClusterRead)
def rename_cluster(
    cluster_id: UUID,
    payload: RenameClusterRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).rename_cluster(
        cluster_id, current_user.id, payload.cluster_name, payload.notes
    )
    return _serialize_cluster(db, cluster)


@router.patch("/clusters/{cluster_id}/primary", response_model=KeywordClusterRead)
def change_primary_keyword(
    cluster_id: UUID,
    payload: ChangePrimaryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).change_primary_keyword(
        cluster_id, current_user.id, payload.primary_keyword_id, payload.notes
    )
    return _serialize_cluster(db, cluster)


@router.post("/clusters/move-keyword", response_model=KeywordClusterRead)
def move_keyword(
    payload: MoveKeywordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).move_keyword(
        payload.keyword_id,
        payload.source_cluster_id,
        payload.target_cluster_id,
        current_user.id,
        payload.notes,
    )
    return _serialize_cluster(db, cluster)


@router.post("/clusters/merge", response_model=KeywordClusterRead)
def merge_clusters(
    payload: MergeClustersRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordClusterRead:
    cluster = ClusteringService(db).merge_clusters(
        payload.source_cluster_ids,
        current_user.id,
        payload.target_cluster_name,
        payload.notes,
    )
    return _serialize_cluster(db, cluster)


@router.post("/clusters/{cluster_id}/split", response_model=list[KeywordClusterRead])
def split_cluster(
    cluster_id: UUID,
    payload: SplitClusterRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[KeywordClusterRead]:
    orig, new_cluster = ClusteringService(db).split_cluster(
        cluster_id,
        payload.keyword_ids_to_extract,
        payload.new_cluster_name,
        current_user.id,
        payload.notes,
    )
    return [_serialize_cluster(db, orig), _serialize_cluster(db, new_cluster)]


@router.post(
    "/research-runs/{run_id}/prioritize",
    response_model=PrioritizationSummaryResponse,
)
def prioritize_keywords(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PrioritizationSummaryResponse:
    count, weights, top_keywords = PrioritizationService(db).prioritize_run(
        run_id, current_user.id
    )
    return PrioritizationSummaryResponse(
        research_run_id=run_id,
        scored_keywords=count,
        weights_used=weights,
        top_keywords=top_keywords,
    )
