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


from pydantic import BaseModel, Field  # noqa: E402


class GoogleSuggestRequest(BaseModel):
    """Payload for free Google Autocomplete keyword discovery."""

    seed_keyword: str = Field(min_length=1, max_length=200)
    expand_modifiers: bool = True
    max_keywords: int = Field(default=40, ge=5, le=100)


class RunAllPipelineRequest(BaseModel):
    """Payload for 1-Click Auto Pipeline (Discover -> Clean -> Intent -> Cluster -> Briefs)."""

    seed_keyword: str | None = Field(default=None, max_length=200)
    expand_modifiers: bool = True
    max_keywords: int = Field(default=40, ge=5, le=100)
    distance_threshold: float = Field(default=0.45, ge=0.05, le=0.95)


@router.post(
    "/research-runs/{run_id}/discover-suggest",
    summary="Discover real keyword ideas from free Google Autocomplete",
)
def discover_google_suggest(
    run_id: uuid.UUID,
    payload: GoogleSuggestRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Fetch real Google Autocomplete suggestions for a seed keyword (no API key required)."""
    from app.services.auto_pipeline_service import AutoPipelineService

    return AutoPipelineService(db).discover_google_suggest(
        run_id,
        current_user,
        seed_keyword=payload.seed_keyword,
        expand_modifiers=payload.expand_modifiers,
        max_keywords=payload.max_keywords,
    )


@router.post(
    "/research-runs/{run_id}/run-all",
    summary="1-Click Auto Pipeline: Discover -> Clean -> Intent -> Cluster -> Prioritize -> Briefs",
)
def run_all_pipeline(
    run_id: uuid.UUID,
    payload: RunAllPipelineRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object]:
    """Execute the full keyword research and content brief pipeline in a single click."""
    from app.services.auto_pipeline_service import AutoPipelineService

    return AutoPipelineService(db).run_all_pipeline(
        run_id,
        current_user,
        seed_keyword=payload.seed_keyword,
        expand_modifiers=payload.expand_modifiers,
        max_keywords=payload.max_keywords,
        distance_threshold=payload.distance_threshold,
    )


@router.delete(
    "/research-runs/{run_id}/keywords",
    summary="Clear all keywords, clusters, and briefs in a research run",
)
def clear_research_run_keywords(
    run_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, int]:
    """Delete all keywords (and dependent clusters, briefs, SERP snapshots) for a fresh start."""
    from sqlalchemy import delete

    from app.models.brief import ContentBrief
    from app.models.clustering import KeywordCluster
    from app.models.research import Keyword
    from app.models.serp import SerpSnapshot

    service = KeywordService(db)
    try:
        run = service._authorize_run(run_id, current_user)
    except (ResearchRunNotFoundError, ProjectNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.execute(delete(ContentBrief).where(ContentBrief.research_run_id == run.id))
    db.execute(delete(KeywordCluster).where(KeywordCluster.research_run_id == run.id))
    db.execute(delete(SerpSnapshot).where(SerpSnapshot.research_run_id == run.id))
    res = db.execute(delete(Keyword).where(Keyword.research_run_id == run.id))
    db.commit()
    return {"deleted_keywords": int(res.rowcount or 0)}
