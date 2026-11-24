"""Celery background tasks for starting and resuming LangGraph workflows (TASK-024)."""

from uuid import UUID

from app.database.session import SessionLocal
from app.services.workflow_service import WorkflowService
from app.workers.celery_app import celery_app


@celery_app.task(name="workflow.start_research_workflow")
def start_research_workflow_task(execution_id: str, owner_id: str) -> dict[str, str]:
    """Run LangGraph workflow from START until the first mandatory HITL interrupt."""
    with SessionLocal() as db:
        execution = WorkflowService(db).execute_start_sync(UUID(execution_id), UUID(owner_id))
        return {"execution_id": str(execution.id), "status": execution.status}


@celery_app.task(name="workflow.resume_research_workflow")
def resume_research_workflow_task(
    execution_id: str,
    reviewer_id: str,
    decision: str,
    comment: str | None = None,
) -> dict[str, str]:
    """Resume a paused LangGraph workflow from its PostgreSQL checkpoint."""
    with SessionLocal() as db:
        execution = WorkflowService(db).execute_resume_sync(
            UUID(execution_id), UUID(reviewer_id), decision, comment
        )
        return {"execution_id": str(execution.id), "status": execution.status}
