# CHANGELOG

All notable changes to the **AI Keyword Research & Content Planning Agent** project are documented in this file following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **TASK-006**: Built standardized Data Provenance DTOs (`backend/app/schemas/provenance.py`: `DataStatus`, `MetricType`, `MetricRecord`, `KeywordIdeaRecord`, `SerpResultRecord`, `SerpSnapshotRecord`, `ProviderErrorRecord`, `ProviderResult`) strictly separating `NOT_AVAILABLE`/`NULL` from legitimate `0` values.
- **TASK-006**: Implemented typed connector exceptions (`backend/app/connectors/exceptions.py`), HTTP resilience layer (`backend/app/connectors/http_client.py`: `RateLimiter`, `RetryConfig`, `QuotaTracker`, `ResilientHttpClient`), and unified `BaseDataProvider` interface (`backend/app/connectors/base.py`), plus 9 unit tests (`backend/tests/test_provenance_and_resilience.py`).
- **TASK-005**: Implemented domain, base URL, country, and language normalization (`backend/app/utils/normalization.py`), validation schemas (`backend/app/schemas/project.py`), `ProjectRepository`, `ProjectService` (ownership isolation + atomic primary website switching), and all `/api/v1/projects/*` CRUD endpoints (`backend/app/api/v1/projects.py`).
- **TASK-005**: Initialized `docs/API_SPEC.md` and added 19 unit & PostgreSQL integration tests (`test_normalization.py`, `tests/integration/test_projects_api.py`).
- **TASK-004**: Implemented `backend/app/utils/security.py` (bcrypt password hashing, PyJWT access tokens, and Fernet `TokenEncryptor` for OAuth tokens).
- **TASK-004**: Implemented `UserRepository`, `schemas/auth.py`, `AuthService`, `get_current_user` / `get_current_active_admin` dependencies (`backend/app/api/deps.py`), and `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` (`backend/app/api/v1/auth.py`).
- **TASK-004**: Forwarded `exc.headers` in `http_exception_handler` (`backend/app/api/errors.py`) to preserve `WWW-Authenticate: Bearer` on 401 responses, plus 15 security & auth API tests.
- **TASK-003**: Set up synchronous SQLAlchemy 2.x foundation (`backend/app/database/base.py`, `backend/app/database/session.py` with `get_db`, naming conventions, UUID PK & TIMESTAMPTZ mixins).
- **TASK-003**: Implemented 7 core ORM models (`User`, `OAuthCredential`, `Project`, `Website`, `ProjectSettings`, `Competitor`, `DataSource`) under `backend/app/models/`.
- **TASK-003**: Configured Alembic (`backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`) and created migration `0001_init_core` installing `pg_trgm`, 7 core tables, and seeding 7 `data_sources` rows.
- **TASK-003**: Added one-shot `migrate` service running `alembic upgrade head` before `backend` and `worker` in `docker-compose.yml`, plus 15 metadata & PostgreSQL integration tests.
- **TASK-002**: Built application configuration `backend/app/config.py` (Pydantic Settings v2, `SecretStr`, `NoDecode` for `CORS_ORIGINS`, production safety guards).
- **TASK-002**: Configured structured logging `backend/app/utils/logging.py` (structlog JSON/Console + automatic sensitive-field redaction) and `X-Request-ID` tracing middleware (`backend/app/api/middleware.py`).
- **TASK-002**: Implemented global JSON error envelope (`backend/app/api/errors.py`), operational endpoints `GET /health` & `GET /ready` (`backend/app/api/health.py`, `backend/app/services/health_service.py`, `backend/app/schemas/health.py`), FastAPI app factory (`backend/app/main.py`), and v1 router registry (`backend/app/api/v1/router.py`).
- **TASK-002**: Configured Celery app & diagnostic task `system.ping` (`backend/app/workers/celery_app.py`), `backend/Dockerfile` (Python 3.12 non-root), `backend/.dockerignore`, and `docker-compose.yml` (PostgreSQL 16, Redis 7, Backend, Celery Worker with healthchecks).
- **TASK-001**: Initialized Modular Monolith repository layout (`backend/app/*`, `backend/tests/`, `backend/alembic/versions/`, `frontend/src/*`), root config templates (`.gitignore`, `.editorconfig`, `.env.example`, `pyproject.toml`, `requirements*.txt`, `frontend/package.json`), baseline docs, and `backend/tests/test_project_structure.py`.
