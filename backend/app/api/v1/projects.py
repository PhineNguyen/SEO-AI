"""Project Management API v1 endpoints: Projects, Settings, Websites, and Competitors."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.project import Competitor, Project, ProjectSettings, Website
from app.models.user import User
from app.schemas.project import (
    CompetitorCreate,
    CompetitorResponse,
    CompetitorUpdate,
    ProjectCreate,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectSettingsResponse,
    ProjectSettingsUpdate,
    ProjectUpdate,
    WebsiteCreate,
    WebsiteResponse,
    WebsiteUpdate,
)
from app.services.project_service import (
    CompetitorNotFoundError,
    DuplicateResourceError,
    ProjectNotFoundError,
    ProjectService,
    WebsiteNotFoundError,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post(
    "",
    response_model=ProjectDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new SEO research project",
)
def create_project(
    payload: ProjectCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Project:
    """Create a project and initialize its default ProjectSettings."""
    service = ProjectService(db)
    try:
        return service.create_project(current_user, payload)
    except DuplicateResourceError as exc:
        raise _conflict(exc) from exc


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List projects owned by the current user",
)
def list_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status_filter: Annotated[
        Literal["ACTIVE", "ARCHIVED"] | None,
        Query(alias="status"),
    ] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    """Return paginated projects with optional status and search filters."""
    service = ProjectService(db)
    items, total = service.list_projects(
        current_user,
        status=status_filter,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Get project details including settings, websites, and competitors",
)
def get_project(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Project:
    """Return full details for a single authorized project."""
    service = ProjectService(db)
    try:
        return service.get_project(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update a project",
)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Project:
    """Partially update an authorized project."""
    service = ProjectService(db)
    try:
        return service.update_project(project_id, current_user, payload)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
def delete_project(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Delete an authorized project and all cascaded child records."""
    service = ProjectService(db)
    try:
        service.delete_project(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/settings",
    response_model=ProjectSettingsResponse,
    summary="Get project settings",
)
def get_project_settings(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProjectSettings:
    """Return configurable weights and defaults for a project."""
    service = ProjectService(db)
    try:
        return service.get_settings(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc


@router.put(
    "/{project_id}/settings",
    response_model=ProjectSettingsResponse,
    summary="Update project settings",
)
def update_project_settings(
    project_id: uuid.UUID,
    payload: ProjectSettingsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProjectSettings:
    """Update configurable prioritization/clustering weights and SERP defaults."""
    service = ProjectService(db)
    try:
        return service.update_settings(project_id, current_user, payload)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/{project_id}/websites",
    response_model=list[WebsiteResponse],
    summary="List project websites",
)
def list_websites(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Website]:
    """List websites linked to a project."""
    service = ProjectService(db)
    try:
        return service.list_websites(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/{project_id}/websites",
    response_model=WebsiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a website to a project",
)
def add_website(
    project_id: uuid.UUID,
    payload: WebsiteCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Website:
    """Attach a normalized website domain to a project."""
    service = ProjectService(db)
    try:
        return service.add_website(project_id, current_user, payload)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _conflict(exc) from exc


@router.patch(
    "/{project_id}/websites/{website_id}",
    response_model=WebsiteResponse,
    summary="Update a project website",
)
def update_website(
    project_id: uuid.UUID,
    website_id: uuid.UUID,
    payload: WebsiteUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Website:
    """Update a website or promote it to primary."""
    service = ProjectService(db)
    try:
        return service.update_website(project_id, website_id, current_user, payload)
    except (ProjectNotFoundError, WebsiteNotFoundError) as exc:
        raise _not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/{project_id}/websites/{website_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project website",
)
def delete_website(
    project_id: uuid.UUID,
    website_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Remove a website from a project."""
    service = ProjectService(db)
    try:
        service.delete_website(project_id, website_id, current_user)
    except (ProjectNotFoundError, WebsiteNotFoundError) as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project_id}/competitors",
    response_model=list[CompetitorResponse],
    summary="List project competitors",
)
def list_competitors(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Competitor]:
    """List competitor domains tracked by a project."""
    service = ProjectService(db)
    try:
        return service.list_competitors(project_id, current_user)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/{project_id}/competitors",
    response_model=CompetitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a competitor to a project",
)
def add_competitor(
    project_id: uuid.UUID,
    payload: CompetitorCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Competitor:
    """Add a normalized competitor domain to a project."""
    service = ProjectService(db)
    try:
        return service.add_competitor(project_id, current_user, payload)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _conflict(exc) from exc


@router.patch(
    "/{project_id}/competitors/{competitor_id}",
    response_model=CompetitorResponse,
    summary="Update a project competitor",
)
def update_competitor(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    payload: CompetitorUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Competitor:
    """Update competitor details."""
    service = ProjectService(db)
    try:
        return service.update_competitor(project_id, competitor_id, current_user, payload)
    except (ProjectNotFoundError, CompetitorNotFoundError) as exc:
        raise _not_found(exc) from exc
    except DuplicateResourceError as exc:
        raise _conflict(exc) from exc


@router.delete(
    "/{project_id}/competitors/{competitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project competitor",
)
def delete_competitor(
    project_id: uuid.UUID,
    competitor_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """Remove a competitor from a project."""
    service = ProjectService(db)
    try:
        service.delete_competitor(project_id, competitor_id, current_user)
    except (ProjectNotFoundError, CompetitorNotFoundError) as exc:
        raise _not_found(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
