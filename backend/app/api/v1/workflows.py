"""REST API endpoints for LangGraph Workflow Control (Start / Status / Resume / Cancel)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.workflow import (
    WorkflowExecutionRead,
    WorkflowResumeRequest,
    WorkflowStartRequest,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(tags=["Workflow Orchestration"])


@router.post(
    "/research-runs/{run_id}/workflow/start",
    response_model=WorkflowExecutionRead,
    status_code=201,
)
def start_workflow(
    run_id: UUID,
    payload: WorkflowStartRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkflowExecutionRead:
    execution = WorkflowService(db).start_workflow(
        run_id, current_user.id, use_async_worker=payload.use_async_worker
    )
    return WorkflowExecutionRead.model_validate(execution)


@router.get(
    "/research-runs/{run_id}/workflows",
    response_model=list[WorkflowExecutionRead],
)
def list_workflows(
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[WorkflowExecutionRead]:
    items = WorkflowService(db).list_workflows_for_run(run_id, current_user.id)
    return [WorkflowExecutionRead.model_validate(item) for item in items]


@router.get("/workflows/{execution_id}", response_model=WorkflowExecutionRead)
def get_workflow_status(
    execution_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkflowExecutionRead:
    execution = WorkflowService(db).get_workflow(execution_id, current_user.id)
    return WorkflowExecutionRead.model_validate(execution)


@router.post("/workflows/{execution_id}/resume", response_model=WorkflowExecutionRead)
def resume_workflow(
    execution_id: UUID,
    payload: WorkflowResumeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkflowExecutionRead:
    execution = WorkflowService(db).resume_workflow(
        execution_id,
        current_user.id,
        decision=payload.decision,
        comment=payload.comment,
        summary_diff=payload.summary_diff,
        use_async_worker=payload.use_async_worker,
    )
    return WorkflowExecutionRead.model_validate(execution)


@router.post("/workflows/{execution_id}/cancel", response_model=WorkflowExecutionRead)
def cancel_workflow(
    execution_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WorkflowExecutionRead:
    execution = WorkflowService(db).cancel_workflow(execution_id, current_user.id)
    return WorkflowExecutionRead.model_validate(execution)
