"""Data access repository for Sprint 5 clustering and Review 2 audit trails."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.clustering import ClusterKeyword, ClusterReview, KeywordCluster

ACTIVE_CLUSTER_STATUSES = ("ACTIVE", "APPROVED")


class ClusterRepository:
    """Persistence operations for clusters, members, and review audit rows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_run(
        self, research_run_id: UUID, *, active_only: bool = False
    ) -> list[KeywordCluster]:
        stmt = (
            select(KeywordCluster)
            .where(KeywordCluster.research_run_id == research_run_id)
            .options(selectinload(KeywordCluster.members))
            .order_by(KeywordCluster.created_at.asc())
        )
        if active_only:
            stmt = stmt.where(KeywordCluster.status.in_(ACTIVE_CLUSTER_STATUSES))
        return list(self._db.scalars(stmt).all())

    def get_by_id(self, cluster_id: UUID) -> KeywordCluster | None:
        stmt = (
            select(KeywordCluster)
            .where(KeywordCluster.id == cluster_id)
            .options(selectinload(KeywordCluster.members), selectinload(KeywordCluster.reviews))
        )
        return self._db.scalar(stmt)

    def find_active_membership(self, keyword_id: UUID) -> ClusterKeyword | None:
        stmt = (
            select(ClusterKeyword)
            .join(KeywordCluster, ClusterKeyword.cluster_id == KeywordCluster.id)
            .where(
                ClusterKeyword.keyword_id == keyword_id,
                KeywordCluster.status.in_(ACTIVE_CLUSTER_STATUSES),
            )
        )
        return self._db.scalar(stmt)

    def create_cluster(self, cluster: KeywordCluster) -> KeywordCluster:
        self._db.add(cluster)
        self._db.flush()
        return cluster

    def add_member(self, member: ClusterKeyword) -> ClusterKeyword:
        self._db.add(member)
        self._db.flush()
        return member

    def delete_member(self, member: ClusterKeyword) -> None:
        self._db.delete(member)
        self._db.flush()

    def add_review(self, review: ClusterReview) -> ClusterReview:
        self._db.add(review)
        self._db.flush()
        return review

    def list_reviews(self, cluster_id: UUID) -> list[ClusterReview]:
        stmt = (
            select(ClusterReview)
            .where(ClusterReview.cluster_id == cluster_id)
            .order_by(ClusterReview.created_at.asc())
        )
        return list(self._db.scalars(stmt).all())
