"""PostgreSQL checkpointer helper for durable LangGraph HITL workflows (TASK-022)."""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver


def to_psycopg_conninfo(database_url: str) -> str:
    """Convert SQLAlchemy postgresql+psycopg:// URL to standard libpq postgresql:// conninfo."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    return database_url


_INITIALIZED_CONNINFOS: set[str] = set()


@contextmanager
def open_postgres_checkpointer(
    database_url: str, *, run_setup: bool | None = None
) -> Iterator[PostgresSaver]:
    """Open a PostgresSaver checkpointer, running DDL setup once per database URL."""
    conninfo = to_psycopg_conninfo(database_url)
    with PostgresSaver.from_conn_string(conninfo) as saver:
        should_setup = run_setup if run_setup is not None else (conninfo not in _INITIALIZED_CONNINFOS)
        if should_setup:
            saver.setup()
            _INITIALIZED_CONNINFOS.add(conninfo)
        yield saver


def create_memory_checkpointer() -> MemorySaver:
    """Create an in-memory checkpointer for isolated unit tests."""
    return MemorySaver()
