# CHANGELOG

Tất cả các thay đổi đáng chú ý của dự án **AI Keyword Research & Content Planning Agent** sẽ được ghi lại tại đây theo chuẩn [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **TASK-005**: Triển khai chuẩn hóa domain, base URL, country và language (`backend/app/utils/normalization.py`), schemas validation (`backend/app/schemas/project.py`), `ProjectRepository`, `ProjectService` (ownership isolation + atomic primary website switch) và toàn bộ `/api/v1/projects/*` CRUD APIs (`backend/app/api/v1/projects.py`).
- **TASK-005**: Khởi tạo tài liệu `docs/API_SPEC.md` và bổ sung 19 unit & PostgreSQL integration tests mới (`test_normalization.py`, `tests/integration/test_projects_api.py`).
- **TASK-004**: Triển khai `backend/app/utils/security.py` (hash/verify mật khẩu bcrypt, tạo/giải mã JWT access token, và `TokenEncryptor` bằng Fernet cho OAuth tokens).
- **TASK-004**: Triển khai `UserRepository`, `schemas/auth.py`, `AuthService`, dependencies `get_current_user` / `get_current_active_admin` (`backend/app/api/deps.py`), và các endpoint `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` (`backend/app/api/v1/auth.py`).
- **TASK-004**: Bổ sung truyền `exc.headers` trong `http_exception_handler` (`backend/app/api/errors.py`) để giữ header `WWW-Authenticate: Bearer` trên phản hồi 401, cùng 15 unit & integration tests mới (`test_security.py`, `tests/integration/test_auth_api.py`).
- **TASK-003**: Xây dựng nền tảng SQLAlchemy 2.x synchronous (`backend/app/database/base.py`, `backend/app/database/session.py` với `get_db`, naming convention, UUID PK & TIMESTAMPTZ mixins).
- **TASK-003**: Triển khai 7 ORM models lõi (`User`, `OAuthCredential`, `Project`, `Website`, `ProjectSettings`, `Competitor`, `DataSource`) trong `backend/app/models/`.
- **TASK-003**: Cấu hình Alembic (`backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`) và tạo migration `0001_init_core` cài đặt `pg_trgm`, 7 bảng lõi và seed 7 dòng `data_sources`.
- **TASK-003**: Bổ sung service `migrate` chạy `alembic upgrade head` tự động trước `backend` và `worker` trong `docker-compose.yml`, cùng 15 tests mới (`test_models_metadata.py`, `tests/integration/test_migrations.py`, `tests/integration/test_db_constraints.py`).
- **TASK-002**: Xây dựng cấu hình ứng dụng `backend/app/config.py` (Pydantic Settings v2, `SecretStr`, `NoDecode` cho `CORS_ORIGINS`, production safety validator).
- **TASK-002**: Thiết lập structured logging `backend/app/utils/logging.py` (structlog JSON/Console + redaction tự động trường nhạy cảm) và middleware `X-Request-ID` (`backend/app/api/middleware.py`).
- **TASK-002**: Triển khai global error envelope (`backend/app/api/errors.py`), operational endpoints `GET /health` & `GET /ready` (`backend/app/api/health.py`, `backend/app/services/health_service.py`, `backend/app/schemas/health.py`), FastAPI factory (`backend/app/main.py`) và API v1 router registry (`backend/app/api/v1/router.py`).
- **TASK-002**: Cấu hình Celery app & diagnostic task `system.ping` (`backend/app/workers/celery_app.py`), `backend/Dockerfile` (Python 3.12 non-root), `backend/.dockerignore`, và `docker-compose.yml` (PostgreSQL 16, Redis 7, Backend, Celery Worker với healthchecks).
- **TASK-002**: Bổ sung bộ test `conftest.py`, `test_config.py`, `test_health.py`, `test_logging.py`, `test_celery_app.py` (26/26 passed).
- **TASK-001**: Khởi tạo cấu trúc repository chuẩn Modular Monolith cho backend (`backend/app/*`, `backend/tests/`, `backend/alembic/versions/`) và frontend (`frontend/src/*`).
- **TASK-001**: Thiết lập cấu hình gốc `.gitignore`, `.editorconfig`, `.env.example`, `backend/pyproject.toml`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/requirements-ml.txt`, và `frontend/package.json` (React + TypeScript + Vite + Material UI).
- **TASK-001**: Khởi tạo bộ tài liệu nền tảng: `README.md`, `PROJECT_STATUS.md`, `TASKS.md`, `CHANGELOG.md`, `docs/ARCHITECTURE.md`, và `docs/DATABASE.md`.
- **TASK-001**: Thêm kiểm thử tự động `backend/tests/test_project_structure.py` xác minh tính toàn vẹn của package tree, cấu hình `.env.example`, `.gitignore`, `frontend/package.json` và tài liệu.
