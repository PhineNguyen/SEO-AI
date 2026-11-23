# PROJECT STATUS – AI Keyword Research & Content Planning Agent

**Cập nhật lần cuối**: 2026-11-24
**Sprint hiện tại**: Sprint 1 – Foundation & Database (**Hoàn thành 5/5 Tasks**; sẵn sàng chuyển sang Sprint 2)
**Trạng thái tổng quan**: Đã hoàn tất toàn bộ **Sprint 1** (`TASK-001` → `TASK-005`: Repo & Docs, Docker Compose + FastAPI/Celery, SQLAlchemy 2.x + Alembic `001`, JWT Auth + Fernet, Project Management CRUD APIs); sẵn sàng chuyển sang **Sprint 2 (`TASK-006`)**.

---

## 1. Tổng hợp tiến độ Tasks (32 Tasks / 8 Sprints)

| Trạng thái | Số lượng | Chi tiết |
| :--- | :---: | :--- |
| **Completed** | 5 | `TASK-001`, `TASK-002`, `TASK-003`, `TASK-004`, `TASK-005` |
| **In Progress** | 0 | — |
| **Pending** | 27 | `TASK-006` → `TASK-032` |
| **Blocked** | 0 | — |

---

## 2. Chi tiết theo trạng thái

### Completed
| Task ID | Tên Task | Bằng chứng hoàn thành |
| :--- | :--- | :--- |
| `TASK-001` | Initialize Repository, Project Structure & Documentation Baseline | Cây thư mục `backend/`, `frontend/`, `docs/`, manifest cấu hình (`.gitignore`, `.env.example`, `pyproject.toml`, `requirements*.txt`, `frontend/package.json`), tài liệu nền tảng và test `backend/tests/test_project_structure.py` chạy pass `100%`. |
| `TASK-002` | Docker Compose, FastAPI App Bootstrap, Config & Structured Logging | `config.py`, `logging.py` (structlog + redaction), `middleware.py`, `errors.py`, `health_service.py`, `health.py`, `main.py`, `celery_app.py`, `Dockerfile`, `docker-compose.yml`. Kiểm thử: `ruff check` 0 lỗi, `pytest` **26/26 passed**, `docker compose ps` cả 4 container `healthy`, `GET /ready` trả 200 (`database: ok`, `redis: ok`), `celery inspect ping` trả `pong`. |
| `TASK-003` | SQLAlchemy 2.x Setup, Alembic & Core Migration (`001`) | `database/base.py`, `database/session.py`, 7 ORM models (`users`, `oauth_credentials`, `projects`, `websites`, `project_settings`, `competitors`, `data_sources`), Alembic `0001_init_core` + seed 7 nguồn dữ liệu, Docker service `migrate`. Kiểm thử: `ruff` 0 lỗi, `pytest` **41/41 passed** (11 PostgreSQL integration tests thực thi thật không skip), `alembic check` (`No new upgrade operations detected.`), `\dt` đủ 8 bảng, `data_sources` đủ 7 dòng. |
| `TASK-004` | Authentication (JWT) & Token Encryption Utility | `utils/security.py` (bcrypt, PyJWT, Fernet `TokenEncryptor`), `repositories/user_repository.py`, `schemas/auth.py`, `services/auth_service.py`, `api/deps.py` (`get_current_user`, `get_current_active_admin`), `api/v1/auth.py` (`/register`, `/login`, `/me`). Kiểm thử: `ruff` 0 lỗi, `pytest` **56/56 passed** (unit + PostgreSQL API integration tests) và kiểm chứng live endpoint trên Docker. |
| `TASK-005` | Project Management CRUD APIs | `utils/normalization.py` (domain, URL, country, language), `schemas/project.py`, `repositories/project_repository.py`, `services/project_service.py` (ownership isolation + atomic primary website switch), `api/v1/projects.py` (`/api/v1/projects/*`). Kiểm thử: `ruff` 0 lỗi, `pytest` **75/75 passed** và kiểm chứng live Docker endpoint. |

### In Progress
- Hiện không có task nào đang chạy dở (đã hoàn tất Sprint 1; chờ xác nhận bắt đầu Sprint 2 – `TASK-006`).

### Pending (Nhóm gần nhất – Sprint 2: Data Connectors)
- `TASK-006`: `BaseDataProvider`, Provenance Schemas & HTTP Resilience Layer
- `TASK-007`: DataForSEO Connector (SERP + Optional Keywords Data + Mock Provider)
- `TASK-008`: Semrush Connector (API v4 + CSV/Excel Import + Mock Provider)
- `TASK-009`: Google Search Console Connector (OAuth 2.0 + Search Analytics)
- `TASK-010`: Spineditor CSV/Excel Import Connector
- `TASK-011` → `TASK-032`: Xem chi tiết trong [TASKS.md](./TASKS.md).

### Blocked
- Không có.

---

## 3. Known Issues & Environment Notes

| Mức độ | Mô tả | Cách xử lý |
| :--- | :--- | :--- |
| **Info** | Máy phát triển cục bộ đang cài `Python 3.13.15`, trong khi một số thư viện ML/NLP ổn định nhất trên `Python 3.12`. | `backend/Dockerfile` đã cố định `python:3.12-slim` và build chạy ổn định; `.venv` cục bộ trên Python 3.13 cũng đã cài và chạy đủ `requirements-dev.txt`. |
| **Info** | Terminal sandbox trên Windows chặn loopback TCP socketpair của `asyncio` (gây treo Starlette `TestClient`) và chặn quyền pipe của Docker Engine. | Chạy `pytest` (có `TestClient`/`asyncio`) và các lệnh `docker compose` ở môi trường ngoài sandbox; không ảnh hưởng tới CI hoặc Docker runtime. |

---

## 4. Ma trận trạng thái tích hợp & Credentials (Rule 4)

| Thành phần | Trạng thái kỹ thuật | Trạng thái kiểm thử | Ghi chú |
| :--- | :--- | :--- | :--- |
| Repository Structure & Docs Baseline | **Implemented** | **Tested** (`pytest`) | Hoàn thành ở `TASK-001` |
| FastAPI / Docker / Postgres / Redis / Celery | **Implemented** | **Tested** (`pytest` + live Docker) | Hoàn thành ở `TASK-002` |
| PostgreSQL ORM & Alembic (migration `001`) | **Implemented** | **Tested** (`pytest` + `alembic check` + live Docker) | Hoàn thành ở `TASK-003` (7 bảng lõi + seed `data_sources`) |
| JWT Auth & Fernet Token Encryption | **Implemented** | **Tested** (`pytest` + live Docker) | Hoàn thành ở `TASK-004` (`/api/v1/auth/{register,login,me}`) |
| Project Management CRUD APIs | **Implemented** | **Tested** (`pytest` + live Docker) | Hoàn thành ở `TASK-005` (`/api/v1/projects/*`) |
| DataForSEO SERP & Keyword API | **Pending External Credentials** | **Not Implemented** | Triển khai tại `TASK-007` (kèm Mock Provider) |
| Semrush Connector (API v4 + CSV Import) | **Pending External Credentials** (API) | **Not Implemented** | Triển khai tại `TASK-008` (CSV Import không cần API key) |
| Google Search Console Connector (OAuth) | **Pending External Credentials** | **Not Implemented** | Triển khai tại `TASK-009` |
| Spineditor CSV/Excel Import | **Not Implemented** | **Not Implemented** | Triển khai tại `TASK-010` (cần file mẫu thực tế để verify cột) |
| OpenAI API (LLM & Embeddings) | **Pending External Credentials** | **Not Implemented** | Triển khai tại `TASK-017`, `TASK-019`, `TASK-025` |
| Google Sheets Export (OAuth) | **Pending External Credentials** | **Not Implemented** | Triển khai tại `TASK-029` |

---

## 5. Đồng bộ tài liệu (Section 19)

| Tài liệu | Trạng thái | Ghi chú |
| :--- | :--- | :--- |
| `README.md` | **Implemented** | Đồng bộ với `TASK-001` |
| `PROJECT_STATUS.md` | **Implemented** | Cập nhật sau `TASK-001` |
| `TASKS.md` | **Implemented** | Backlog 8 Sprints / 32 Tasks |
| `CHANGELOG.md` | **Implemented** | Ghi nhận `TASK-001` |
| `docs/ARCHITECTURE.md` | **Implemented** | Kiến trúc Modular Monolith & 5 quyết định đã chốt |
| `docs/DATABASE.md` | **Implemented** | ERD & đặc tả 6 nhóm bảng + kế hoạch migration |
| `docs/PRD.md` | **Not Implemented** | Bổ sung/tổng hợp khi hoàn thiện specs chi tiết |
| `docs/SRS.md` | **Not Implemented** | Bổ sung song song Sprint 2–3 |
| `docs/API_SPEC.md` | **Implemented** | Đã khởi tạo cho Ops, Auth (`/api/v1/auth/*`) và Projects (`/api/v1/projects/*`) ở `TASK-005` |
| `docs/WORKFLOW.md` | **Not Implemented** | Cập nhật tại Sprint 6 (`TASK-022`, `TASK-023`) |
| `docs/TEST_PLAN.md` | **Not Implemented** | Cập nhật tại Sprint 4 & Sprint 8 (`TASK-018`, `TASK-032`) |
