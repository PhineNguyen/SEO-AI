"""Operational liveness (/health) and readiness (/ready) endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services import health_service

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health_check(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Return process liveness metadata without external I/O."""
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        environment=settings.APP_ENV,
        version=settings.APP_VERSION,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse, "description": "Dependency unavailable"}},
    summary="Readiness check",
)
def readiness_check(settings: Annotated[Settings, Depends(get_settings)]) -> JSONResponse:
    """Verify PostgreSQL and Redis connectivity before accepting traffic."""
    is_ready, checks = health_service.run_readiness_checks(settings)
    payload = ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,  # type: ignore[arg-type]
    )
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content=payload.model_dump(),
    )
