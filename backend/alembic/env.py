"""Alembic migration environment configured for SQLAlchemy 2.x and structlog."""

from alembic import context
from app import models  # noqa: F401
from app.config import get_settings
from app.database.base import Base
from app.utils.logging import configure_logging
from sqlalchemy import NullPool, create_engine

config = context.config
target_metadata = Base.metadata


def _resolve_database_url() -> str:
    """Resolve database URL from Alembic config override or application Settings."""
    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url:
        return configured_url
    settings = get_settings()
    configure_logging(log_level=settings.LOG_LEVEL, json_logs=settings.use_json_logs)
    return settings.DATABASE_URL


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode without creating a DB connection."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using a NullPool synchronous engine."""
    url = _resolve_database_url()
    connectable = create_engine(url, poolclass=NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
