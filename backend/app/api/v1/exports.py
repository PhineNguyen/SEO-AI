"""REST API endpoints for Sprint 8 Excel & Google Sheets Exports (TASK-028, TASK-029)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.brief import ExportJobRead
from app.services.export_service import ExportService

router = APIRouter(tags=["Exports"])


@router.post("/research-runs/{run_id}/exports/excel")
def export_excel(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    job, xlsx_bytes = ExportService(db).export_excel(run_id, current_user.id)
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="research_run_{run_id}.xlsx"',
            "X-Export-Job-Id": str(job.id),
        },
    )


@router.post(
    "/research-runs/{run_id}/exports/google-sheets",
    response_model=ExportJobRead,
    status_code=201,
)
def export_google_sheets(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ExportJobRead:
    job = ExportService(db).export_google_sheets(run_id, current_user.id)
    return ExportJobRead.model_validate(job)


@router.get(
    "/research-runs/{run_id}/exports",
    response_model=list[ExportJobRead],
)
def list_exports(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ExportJobRead]:
    jobs = ExportService(db).list_export_jobs(run_id, current_user.id)
    return [ExportJobRead.model_validate(j) for j in jobs]
