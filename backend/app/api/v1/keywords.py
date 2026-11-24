"""Keyword Listing, Metrics Aggregation, and Review 1 API v1 endpoints."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.research import (
    BulkKeywordReviewRequest,
    BulkKeywordReviewResponse,
    KeywordListResponse,
    KeywordResponse,
    KeywordReviewUpdate,
    ManualKeywordCreate,
)
from app.services.keyword_service import (
    KeywordNotFoundError,
    KeywordService,
    ResearchRunNotFoundError,
)
from app.services.project_service import DuplicateResourceError, ProjectNotFoundError

router = APIRouter(tags=["keywords"])


@router.get(
    "/research-runs/{run_id}/keywords",
    response_model=KeywordListResponse,
    summary="List keywords with aggregated multi-source metrics and Review 1 filters",
)
def list_keywords(
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cleaning_status: Annotated[
        Literal["RAW", "ACTIVE", "DUPLICATE", "NEAR_DUPLICATE", "IRRELEVANT", "INVALID"] | None,
        Query(),
    ] = None,
    review_status: Annotated[
        Literal["PENDING", "APPROVED", "REJECTED"] | None,
        Query(),
    ] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KeywordListResponse:
    """Return paginated keywords with latest metrics per (metric_type, source_code)."""
    service = KeywordService(db)
    try:
        items, total = service.list_keywords(
            run_id,
            current_user,
            cleaning_status=cleaning_status,
            review_status=review_status,
            search=search,
            limit=limit,
            offset=offset,
        )
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return KeywordListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/research-runs/{run_id}/keywords",
    response_model=KeywordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add an approved keyword to a research run",
)
def add_manual_keyword(
    run_id: uuid.UUID,
    payload: ManualKeywordCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordResponse:
    """Add a manual keyword candidate traced to the 'manual' data source."""
    service = KeywordService(db)
    try:
        return service.add_manual_keyword(run_id, current_user, payload)
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/keywords/{keyword_id}",
    response_model=KeywordResponse,
    summary="Review 1: Approve, reject, edit, or mark a keyword irrelevant",
)
def review_keyword(
    keyword_id: uuid.UUID,
    payload: KeywordReviewUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> KeywordResponse:
    """Apply Review 1 changes while preserving original_keyword."""
    service = KeywordService(db)
    try:
        return service.review_keyword(keyword_id, current_user, payload)
    except (KeywordNotFoundError, ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/research-runs/{run_id}/keywords/bulk-review",
    response_model=BulkKeywordReviewResponse,
    summary="Review 1: Bulk approve, reject, or mark keywords irrelevant",
)
def bulk_review_keywords(
    run_id: uuid.UUID,
    payload: BulkKeywordReviewRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> BulkKeywordReviewResponse:
    """Apply Review 1 status updates across a batch of keywords."""
    service = KeywordService(db)
    try:
        updated = service.bulk_review_keywords(run_id, current_user, payload)
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return BulkKeywordReviewResponse(updated_count=updated)
