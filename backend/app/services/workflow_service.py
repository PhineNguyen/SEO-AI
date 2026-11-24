"""Workflow orchestration service connecting LangGraph + PostgresSaver + Domain Services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.agents.checkpointer import open_postgres_checkpointer
from app.agents.keyword_research_graph import build_keyword_research_graph
from app.agents.state import KeywordResearchState
from app.models.project import Project
from app.models.research import Keyword, ResearchRun
from app.models.workflow import ReviewDecision, WorkflowCheckpoint, WorkflowExecution

WAITING_STATUS_TO_GATE: dict[str, str] = {
    "WAITING_REVIEW_1": "REVIEW_1_KEYWORDS",
    "WAITING_REVIEW_2": "REVIEW_2_CLUSTERS",
    "WAITING_REVIEW_3": "REVIEW_3_BRIEFS",
}


class WorkflowService:
    """Starts, inspects, resumes, and cancels durable LangGraph workflow executions."""

    def __init__(self, db: Session, database_url: str | None = None) -> None:
        self._db = db
        if database_url:
            self._database_url = database_url
        else:
            bind = db.get_bind()
            engine = getattr(bind, "engine", bind)
            self._database_url = engine.url.render_as_string(hide_password=False)

    def _get_owned_run(self, research_run_id: UUID, owner_id: UUID) -> ResearchRun:
        run = self._db.scalar(
            select(ResearchRun)
            .join(Project, ResearchRun.project_id == Project.id)
            .where(ResearchRun.id == research_run_id, Project.owner_id == owner_id)
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found"
            )
        return run

    def _get_owned_execution(self, execution_id: UUID, owner_id: UUID) -> WorkflowExecution:
        execution = self._db.scalar(
            select(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .options(
                selectinload(WorkflowExecution.checkpoints),
                selectinload(WorkflowExecution.decisions),
            )
        )
        if not execution:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Workflow execution not found"
            )
        self._get_owned_run(execution.research_run_id, owner_id)
        return execution

    def _build_default_handlers(self, run: ResearchRun, owner_id: UUID) -> dict[str, Any]:
        """Connect LangGraph nodes to real domain services in a fault-tolerant manner."""

        def _load_context(state: KeywordResearchState) -> dict[str, Any]:
            kw_count = len(
                list(
                    self._db.scalars(
                        select(Keyword.id).where(Keyword.research_run_id == run.id)
                    ).all()
                )
            )
            return {"collected_keyword_count": kw_count}

        def _clean(state: KeywordResearchState) -> dict[str, Any]:
            from app.models.user import User
            from app.schemas.research import CleaningRequest
            from app.services.keyword_service import KeywordService

            owner = self._db.scalar(select(User).where(User.id == owner_id))
            if not owner:
                return {"active_keyword_count": 0}
            summary = KeywordService(self._db).run_cleaning(run.id, owner, CleaningRequest())
            return {"active_keyword_count": summary.active_count}

        def _cluster(state: KeywordResearchState) -> dict[str, Any]:
            from app.services.clustering_service import ClusteringService

            clusters = ClusteringService(self._db).run_clustering(run.id, owner_id)
            return {"cluster_count": len(clusters)}

        def _prioritize(state: KeywordResearchState) -> dict[str, Any]:
            from app.services.prioritization_service import PrioritizationService

            count, _, _ = PrioritizationService(self._db).prioritize_run(run.id, owner_id)
            return {"prioritized_keyword_count": count}

        def _generate_briefs(state: KeywordResearchState) -> dict[str, Any]:
            try:
                from app.services.brief_service import ContentBriefService

                briefs = ContentBriefService(self._db).generate_briefs_for_run(run.id, owner_id)
                return {"brief_count": len(briefs), "validated_brief_count": len(briefs)}
            except ImportError:
                return {"brief_count": 0, "validated_brief_count": 0}

        return {
            "load_context": _load_context,
            "clean_and_normalize": _clean,
            "cluster_keywords": _cluster,
            "prioritize_keywords": _prioritize,
            "generate_content_briefs": _generate_briefs,
        }

    def _sync_state_from_graph(
        self,
        execution: WorkflowExecution,
        graph: Any,
        config: dict[str, Any],
    ) -> WorkflowExecution:
        snapshot = graph.get_state(config)
        values: dict[str, Any] = dict(snapshot.values or {})
        history = list(values.get("node_history", []))
        last_node = history[-1] if history else values.get("current_node")

        # Check if graph is paused at an interrupt() gate
        interrupt_payload: dict[str, Any] | None = None
        for task in snapshot.tasks:
            if getattr(task, "interrupts", None):
                interrupt_payload = dict(task.interrupts[0].value)
                break

        if interrupt_payload is not None:
            execution.status = str(interrupt_payload.get("waiting_status", "WAITING_REVIEW_1"))
            execution.current_node = str(interrupt_payload.get("current_node", last_node or ""))
            self._db.add(
                WorkflowCheckpoint(
                    workflow_execution_id=execution.id,
                    node_name=execution.current_node or "interrupt",
                    checkpoint_key=f"{execution.langgraph_thread_id}:{execution.status}",
                    status="PAUSED_FOR_REVIEW",
                    metrics_summary={
                        "gate": interrupt_payload.get("gate"),
                        "node_history_len": len(history),
                    },
                )
            )
        elif values.get("status") == "CANCELLED" or values.get("last_review_decision") == "REJECT":
            execution.status = "CANCELLED"
            execution.current_node = last_node
            execution.completed_at = datetime.now(UTC)
        else:
            execution.status = "COMPLETED"
            execution.current_node = last_node or "finalize_export_ready"
            execution.completed_at = datetime.now(UTC)
            self._db.add(
                WorkflowCheckpoint(
                    workflow_execution_id=execution.id,
                    node_name=execution.current_node,
                    checkpoint_key=f"{execution.langgraph_thread_id}:COMPLETED",
                    status="COMPLETED",
                    metrics_summary={"node_history": history},
                )
            )

        self._db.commit()
        return self._get_owned_execution(execution.id, UUID(values["owner_id"]))

    def start_workflow(
        self,
        research_run_id: UUID,
        owner_id: UUID,
        *,
        use_async_worker: bool = False,
    ) -> WorkflowExecution:
        run = self._get_owned_run(research_run_id, owner_id)
        thread_id = f"run-{run.id}-{uuid4().hex[:12]}"
        execution = WorkflowExecution(
            research_run_id=run.id,
            langgraph_thread_id=thread_id,
            status="RUNNING",
            current_node="load_context",
        )
        self._db.add(execution)
        self._db.commit()

        if use_async_worker:
            from app.workers.workflow_tasks import start_research_workflow_task

            async_res = start_research_workflow_task.delay(str(execution.id), str(owner_id))
            execution.celery_task_id = async_res.id
            self._db.commit()
            return self._get_owned_execution(execution.id, owner_id)

        return self.execute_start_sync(execution.id, owner_id)

    def execute_start_sync(self, execution_id: UUID, owner_id: UUID) -> WorkflowExecution:
        execution = self._get_owned_execution(execution_id, owner_id)
        run = self._get_owned_run(execution.research_run_id, owner_id)
        initial_state: KeywordResearchState = {
            "project_id": str(run.project_id),
            "research_run_id": str(run.id),
            "owner_id": str(owner_id),
            "workflow_execution_id": str(execution.id),
            "langgraph_thread_id": execution.langgraph_thread_id,
            "status": "RUNNING",
            "node_history": [],
            "errors": [],
        }
        config = {"configurable": {"thread_id": execution.langgraph_thread_id}}
        try:
            with open_postgres_checkpointer(self._database_url) as checkpointer:
                graph = build_keyword_research_graph(
                    checkpointer=checkpointer,
                    node_handlers=self._build_default_handlers(run, owner_id),
                )
                graph.invoke(initial_state, config=config)
                return self._sync_state_from_graph(execution, graph, config)
        except Exception as exc:
            execution.status = "FAILED"
            execution.error_message = str(exc)
            self._db.commit()
            raise

    def resume_workflow(
        self,
        execution_id: UUID,
        reviewer_id: UUID,
        *,
        decision: str,
        comment: str | None = None,
        summary_diff: dict[str, Any] | None = None,
        use_async_worker: bool = False,
    ) -> WorkflowExecution:
        execution = self._get_owned_execution(execution_id, reviewer_id)
        if execution.status not in WAITING_STATUS_TO_GATE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workflow is in status '{execution.status}' and cannot be resumed",
            )
        gate = WAITING_STATUS_TO_GATE[execution.status]
        self._db.add(
            ReviewDecision(
                workflow_execution_id=execution.id,
                review_gate=gate,
                decision=decision,
                summary_diff=summary_diff or {},
                reviewer_id=reviewer_id,
                comment=comment,
            )
        )
        execution.status = "RUNNING"
        self._db.commit()

        if use_async_worker:
            from app.workers.workflow_tasks import resume_research_workflow_task

            async_res = resume_research_workflow_task.delay(
                str(execution.id), str(reviewer_id), decision, comment
            )
            execution.celery_task_id = async_res.id
            self._db.commit()
            return self._get_owned_execution(execution.id, reviewer_id)

        return self.execute_resume_sync(execution.id, reviewer_id, decision, comment)

    def execute_resume_sync(
        self,
        execution_id: UUID,
        reviewer_id: UUID,
        decision: str,
        comment: str | None = None,
    ) -> WorkflowExecution:
        execution = self._get_owned_execution(execution_id, reviewer_id)
        run = self._get_owned_run(execution.research_run_id, reviewer_id)
        config = {"configurable": {"thread_id": execution.langgraph_thread_id}}
        try:
            with open_postgres_checkpointer(self._database_url) as checkpointer:
                graph = build_keyword_research_graph(
                    checkpointer=checkpointer,
                    node_handlers=self._build_default_handlers(run, reviewer_id),
                )
                graph.invoke(
                    Command(resume={"decision": decision, "comment": comment}),
                    config=config,
                )
                return self._sync_state_from_graph(execution, graph, config)
        except Exception as exc:
            execution.status = "FAILED"
            execution.error_message = str(exc)
            self._db.commit()
            raise

    def get_workflow(self, execution_id: UUID, owner_id: UUID) -> WorkflowExecution:
        return self._get_owned_execution(execution_id, owner_id)

    def list_workflows_for_run(
        self, research_run_id: UUID, owner_id: UUID
    ) -> list[WorkflowExecution]:
        self._get_owned_run(research_run_id, owner_id)
        return list(
            self._db.scalars(
                select(WorkflowExecution)
                .where(WorkflowExecution.research_run_id == research_run_id)
                .options(
                    selectinload(WorkflowExecution.checkpoints),
                    selectinload(WorkflowExecution.decisions),
                )
                .order_by(WorkflowExecution.started_at.desc())
            ).all()
        )

    def cancel_workflow(self, execution_id: UUID, owner_id: UUID) -> WorkflowExecution:
        execution = self._get_owned_execution(execution_id, owner_id)
        if execution.status in ("COMPLETED", "CANCELLED"):
            return execution
        execution.status = "CANCELLED"
        execution.completed_at = datetime.now(UTC)
        self._db.commit()
        return self._get_owned_execution(execution.id, owner_id)
