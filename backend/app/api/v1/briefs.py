"""REST API endpoints for Sprint 7 Content Brief Generation & Review 3 (TASK-025..027)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.brief import BriefActionRequest, BriefEditRequest, ContentBriefRead
from app.services.brief_service import ContentBriefService

router = APIRouter(tags=["Content Briefs"])


@router.post(
    "/research-runs/{run_id}/briefs/generate",
    response_model=list[ContentBriefRead],
    status_code=201,
)
def generate_briefs(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ContentBriefRead]:
    briefs = ContentBriefService(db).generate_briefs_for_run(run_id, current_user.id)
    return [ContentBriefRead.model_validate(b) for b in briefs]


@router.get("/research-runs/{run_id}/briefs", response_model=list[ContentBriefRead])
def list_briefs(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    current_only: bool = Query(default=True),
) -> list[ContentBriefRead]:
    briefs = ContentBriefService(db).list_briefs(
        run_id, current_user.id, current_only=current_only
    )
    return [ContentBriefRead.model_validate(b) for b in briefs]


@router.get("/briefs/{brief_id}", response_model=ContentBriefRead)
def get_brief(
    brief_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ContentBriefRead:
    brief = ContentBriefService(db).get_brief(brief_id, current_user.id)
    return ContentBriefRead.model_validate(brief)


@router.patch("/briefs/{brief_id}", response_model=ContentBriefRead)
def edit_brief(
    brief_id: UUID,
    payload: BriefEditRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ContentBriefRead:
    brief = ContentBriefService(db).edit_brief_versioned(brief_id, current_user.id, payload)
    return ContentBriefRead.model_validate(brief)


@router.post("/briefs/{brief_id}/approve", response_model=ContentBriefRead)
def approve_brief(
    brief_id: UUID,
    payload: BriefActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ContentBriefRead:
    brief = ContentBriefService(db).approve_brief(
        brief_id, current_user.id, payload.feedback_notes
    )
    return ContentBriefRead.model_validate(brief)


@router.post("/briefs/{brief_id}/regenerate", response_model=ContentBriefRead)
def regenerate_brief(
    brief_id: UUID,
    payload: BriefActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ContentBriefRead:
    brief = ContentBriefService(db).regenerate_brief(
        brief_id, current_user.id, payload.feedback_notes
    )
    return ContentBriefRead.model_validate(brief)
