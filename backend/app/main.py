"""FastAPI application factory and ASGI entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_router
from app.config import Settings, get_settings
from app.utils.logging import configure_logging, get_logger

__version__ = "0.1.0"
logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    resolved_settings = settings or get_settings()
    configure_logging(
        log_level=resolved_settings.LOG_LEVEL,
        json_logs=resolved_settings.use_json_logs,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application_startup",
            service=resolved_settings.APP_NAME,
            environment=resolved_settings.APP_ENV,
            version=resolved_settings.APP_VERSION,
        )
        yield
        logger.info(
            "application_shutdown",
            service=resolved_settings.APP_NAME,
            environment=resolved_settings.APP_ENV,
        )

    docs_url = None if resolved_settings.is_production else "/docs"
    redoc_url = None if resolved_settings.is_production else "/redoc"
    openapi_url = None if resolved_settings.is_production else "/openapi.json"

    application = FastAPI(
        title=resolved_settings.APP_NAME,
        version=resolved_settings.APP_VERSION,
        debug=resolved_settings.APP_DEBUG,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestContextMiddleware)

    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(api_router, prefix=resolved_settings.API_V1_PREFIX)

    return application


app = create_app()
