"""Pydantic response schemas for operational liveness and readiness endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness response schema for GET /health."""

    status: Literal["ok"]
    service: str
    environment: str
    version: str


class DependencyCheck(BaseModel):
    """Health status of a single backing dependency."""

    status: Literal["ok", "error"]
    latency_ms: float
    error: str | None = None


class ReadinessChecks(BaseModel):
    """Map of readiness dependency checks."""

    database: DependencyCheck
    redis: DependencyCheck


class ReadinessResponse(BaseModel):
    """Readiness response schema for GET /ready."""

    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks
