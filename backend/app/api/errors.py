"""Consistent JSON error envelope and global FastAPI exception handlers."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.logging import get_logger

logger = get_logger(__name__)


def _extract_request_id(request: Request) -> str | None:
    """Retrieve request_id from request state or structlog contextvars."""
    req_id = getattr(request.state, "request_id", None)
    if req_id:
        return str(req_id)
    ctx_id = structlog.contextvars.get_contextvars().get("request_id")
    return str(ctx_id) if ctx_id else None


def _error_payload(
    *,
    code: str,
    message: str,
    request_id: str | None,
    details: Any = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Register validation, HTTP, and unhandled exception handlers on FastAPI app."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = _extract_request_id(request)
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details=jsonable_encoder(exc.errors()),
                request_id=request_id,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        request_id = _extract_request_id(request)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
                details=None,
                request_id=request_id,
            ),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_id = _extract_request_id(request)
        logger.exception(
            "unhandled_exception",
            error_type=type(exc).__name__,
            path=request.url.path,
            method=request.method,
        )
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="Internal server error",
                details=None,
                request_id=request_id,
            ),
        )
