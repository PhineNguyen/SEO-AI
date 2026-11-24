"""Research Run, File Import (GKP/Spineditor/Semrush), and Cleaning API v1 endpoints."""

import json
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.research import ResearchRun, SourceImport
from app.models.user import User
from app.schemas.research import (
    CleaningRequest,
    CleaningSummary,
    ResearchRunCreate,
    ResearchRunDetailResponse,
    ResearchRunResponse,
    SeedKeywordResponse,
    SourceImportResponse,
)
from app.services.keyword_service import (
    KeywordService,
    ResearchRunNotFoundError,
    UnsupportedImportSourceError,
)
from app.services.project_service import ProjectNotFoundError

router = APIRouter(tags=["research"])

MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/projects/{project_id}/research-runs",
    response_model=ResearchRunDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new keyword research run under a project",
)
def create_research_run(
    project_id: uuid.UUID,
    payload: ResearchRunCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ResearchRunDetailResponse:
    """Create a Research Run snapshotting project settings and persisting seed keywords."""
    service = KeywordService(db)
    try:
        run = service.create_research_run(project_id, current_user, payload)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    counts = service.repo.get_keyword_counts(run.id)
    return ResearchRunDetailResponse(
        **ResearchRunResponse.model_validate(run).model_dump(),
        seed_keywords=[SeedKeywordResponse.model_validate(s) for s in run.seed_keywords],
        keyword_counts=counts,
    )


@router.get(
    "/projects/{project_id}/research-runs",
    response_model=list[ResearchRunResponse],
    summary="List research runs for a project",
)
def list_research_runs(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ResearchRun]:
    """List historical research runs for an authorized project."""
    service = KeywordService(db)
    try:
        return service.list_research_runs(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/research-runs/{run_id}",
    response_model=ResearchRunDetailResponse,
    summary="Get research run detail with seeds and keyword status counts",
)
def get_research_run(
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ResearchRunDetailResponse:
    """Return research run metadata, seed keywords, and cleaning status counts."""
    service = KeywordService(db)
    try:
        run, counts = service.get_research_run_detail(run_id, current_user)
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ResearchRunDetailResponse(
        **ResearchRunResponse.model_validate(run).model_dump(),
        seed_keywords=[SeedKeywordResponse.model_validate(s) for s in run.seed_keywords],
        keyword_counts=counts,
    )


@router.post(
    "/research-runs/{run_id}/imports",
    response_model=SourceImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a Google Keyword Planner, Spineditor, or Semrush CSV/XLSX export",
)
def import_keyword_file(
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    source_code: Annotated[
        Literal["gkp_csv", "spineditor_import", "semrush_csv"],
        Form(),
    ],
    file: Annotated[UploadFile, File()],
    column_mapping_json: Annotated[str | None, Form()] = None,
) -> SourceImport:
    """Parse and persist uploaded CSV/XLSX keywords with full data provenance."""
    content = file.file.read(MAX_IMPORT_FILE_BYTES + 1)
    if len(content) > MAX_IMPORT_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Import file exceeds 10 MB size limit",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Uploaded file is empty",
        )

    parsed_mapping: dict[str, str] | None = None
    if column_mapping_json:
        try:
            raw_map = json.loads(column_mapping_json)
            if not isinstance(raw_map, dict):
                raise ValueError("column_mapping_json must be a JSON object")
            parsed_mapping = {str(k): str(v) for k, v in raw_map.items()}
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid column_mapping_json: {exc}",
            ) from exc

    service = KeywordService(db)
    try:
        return service.import_keyword_file(
            run_id,
            current_user,
            source_code=source_code,
            file_name=file.filename or "upload.csv",
            content=content,
            column_mapping=parsed_mapping,
        )
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedImportSourceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/research-runs/{run_id}/clean",
    response_model=CleaningSummary,
    summary="Run non-destructive keyword normalization and deduplication",
)
def clean_research_run(
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    payload: CleaningRequest | None = None,
) -> CleaningSummary:
    """Clean and deduplicate keywords while preserving all original rows and metrics."""
    service = KeywordService(db)
    try:
        return service.run_cleaning(run_id, current_user, payload or CleaningRequest())
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
