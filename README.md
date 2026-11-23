# AI Keyword Research & Content Planning Agent

Hệ thống **AI Agent chuyên biệt cho SEO Keyword Research & Content Planning** theo hướng **Data-driven**, **Evidence-based** và **Human-in-the-loop**.

> Dự án tập trung sâu vào chất lượng nghiên cứu từ khóa, phân tích SERP, phân loại Search Intent có bằng chứng, Keyword Clustering đa tín hiệu và Content Brief chuẩn SEO Content — không mở rộng sang Technical SEO Audit, Backlink Analysis hay Rank Tracking trong V1.

---

## 5 Nguyên tắc cốt lõi

1. **Data-driven**: Mọi số liệu SEO đến từ nguồn dữ liệu thực tế có provenance rõ ràng; phân biệt `NULL` (`NOT_AVAILABLE` / `NOT_COLLECTED` / `SOURCE_ERROR`) với giá trị `0`.
2. **Evidence-based**: AI không được hallucinate metrics hay URL; mọi phân loại Intent, Cluster và Content Brief phải trích dẫn SERP evidence từ DB.
3. **Human-in-the-loop**: 3 điểm kiểm duyệt bắt buộc (Keyword List, Keyword Clusters, Content Brief), lưu vết thay đổi và không ghi đè mất baseline của AI.
4. **Modular Architecture**: Modular Monolith tách rõ tầng, dễ bảo trì, kiểm thử và thay thế nhà cung cấp dữ liệu.
5. **Accuracy over Features**: Đánh giá Intent và Clustering định lượng trên Golden Dataset được SEO Specialist duyệt thủ công.

---

## Quyết định kiến trúc đã thống nhất cho V1

| Hạng mục | Lựa chọn đã chốt |
| :--- | :--- |
| **Kiến trúc tổng thể** | Modular Monolith (FastAPI + Celery + LangGraph + PostgreSQL + Redis) |
| **SERP Provider chính** | **DataForSEO** (kèm tùy chọn DataForSEO Keywords Data API) |
| **Nguồn Keyword Metrics giai đoạn đầu** | **Semrush** (CSV/Excel Import + `SemrushConnector` API v4 sẵn sàng kèm Mock) + **Spineditor** (CSV/Excel Import) + **Google Search Console** (OAuth 2.0 cho property sở hữu) + DataForSEO Keyword API (tùy chọn) |
| **Frontend UI** | **React + TypeScript + Vite + Material UI (MUI)** (`@mui/x-data-grid`) |
| **Embedding cho Clustering** | `BaseEmbeddingProvider`: mặc định V1 dùng **OpenAI `text-embedding-3-small`**, chuyển đổi sang **Sentence Transformers local** qua biến môi trường `EMBEDDING_PROVIDER` |
| **Authentication & Security** | **JWT Auth (email/password)** từ Sprint 1 + mã hóa đối xứng **Fernet** cho Google OAuth tokens |

---

## Cấu trúc thư mục dự án

```text
d:\SEO-AI\
├── backend/
│   ├── alembic/versions/        # Database migrations (Sprint 1+)
│   ├── app/
│   │   ├── api/v1/              # FastAPI REST endpoints
│   │   ├── agents/              # LangGraph KeywordResearchGraph, nodes, prompts
│   │   ├── connectors/          # BaseDataProvider, DataForSEO, Semrush, GSC, Spineditor Import
│   │   ├── services/            # Business services (cleaning, clustering, intent, brief, export)
│   │   ├── models/              # SQLAlchemy 2.x ORM models
│   │   ├── schemas/             # Pydantic v2 DTOs & Structured Output schemas
│   │   ├── repositories/        # Data access layer
│   │   ├── database/            # PostgreSQL engine, session, base
│   │   ├── workers/             # Celery app & async workflow tasks
│   │   └── utils/               # Security (JWT, Fernet, SSRF guard), normalization
│   ├── tests/                   # Unit, integration, API, security & Golden Dataset tests
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── requirements-ml.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── features/            # projects, research, keyword-review, clustering-review, content-brief
│   │   └── services/            # Typed API clients
│   └── package.json
├── docs/
│   ├── ARCHITECTURE.md
│   └── DATABASE.md
├── .env.example
├── .editorconfig
├── .gitignore
├── PROJECT_STATUS.md
├── TASKS.md
├── CHANGELOG.md
└── README.md
```

---

## Yêu cầu môi trường & Chuẩn bị

- **Python**: `3.12` (Docker runtime cố định Python 3.12 để đảm bảo tương thích thư viện ML/NLP).
- **Node.js**: `20+` (hiện có `v24.20.0`).
- **Docker & Docker Compose**: Dùng để chạy PostgreSQL 16, Redis 7, Backend và Celery Worker.
- **Cấu hình biến môi trường**: Sao chép `.env.example` thành `.env` khi cần tùy chỉnh biến môi trường (tuyệt đối không commit `.env`).

---

## Chạy local

### 1. Chạy toàn bộ stack bằng Docker Compose (Khuyến nghị)
```powershell
# (Tùy chọn) Sao chép file env mẫu
Copy-Item .env.example .env

# Build và khởi động PostgreSQL, Redis, FastAPI Backend và Celery Worker
docker compose up -d --build

# Kiểm tra trạng thái container
docker compose ps
```

Các endpoint đang hoạt động khi stack chạy:
- **Liveness**: `http://localhost:8000/health`
- **Readiness (Postgres + Redis)**: `http://localhost:8000/ready`
- **Swagger UI (chế độ dev)**: `http://localhost:8000/docs`

Để dừng cụm container:
```powershell
docker compose down
```

### 2. Quản lý Database Migrations (Alembic)
Service `migrate` trong `docker-compose.yml` tự động chạy `alembic upgrade head` mỗi khi khởi động stack. Khi cần thao tác thủ công:
```powershell
# Kiểm tra revision hiện tại và đối chiếu drift giữa ORM models với migration
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check

# Hoặc chạy trực tiếp trên máy cục bộ (khi Postgres đang mở cổng 5432)
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 3. Chạy kiểm thử backend trên máy cục bộ (Virtualenv)
```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check app tests
```

---

## Lộ trình phát triển (8 Sprints)

- **Sprint 1**: Foundation, Database, JWT Auth & Project Management (`TASK-001` – `TASK-005`)
- **Sprint 2**: Data Connectors & File Import (`TASK-006` – `TASK-010`)
- **Sprint 3**: Keyword Research & Cleaning Engine (`TASK-011` – `TASK-014`)
- **Sprint 4**: SERP Analysis, Competitor Headings & Search Intent (`TASK-015` – `TASK-018`)
- **Sprint 5**: Hybrid Keyword Clustering & Prioritization (`TASK-019` – `TASK-021`)
- **Sprint 6**: LangGraph AI Agent & Human-in-the-Loop Orchestration (`TASK-022` – `TASK-024`)
- **Sprint 7**: Content Brief Generation & Review (`TASK-025` – `TASK-027`)
- **Sprint 8**: Export (Excel / Google Sheets), React Dashboard, E2E & Deployment (`TASK-028` – `TASK-032`)

---

## Tài liệu dự án

- [PROJECT_STATUS.md](./PROJECT_STATUS.md) – Trạng thái Sprint, tiến độ task và ma trận tích hợp
- [TASKS.md](./TASKS.md) – Backlog chi tiết 8 Sprints / 32 Tasks
- [CHANGELOG.md](./CHANGELOG.md) – Lịch sử thay đổi dự án
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) – Kiến trúc Modular Monolith & thiết kế bảo mật/AI
- [docs/DATABASE.md](./docs/DATABASE.md) – ERD, đặc tả bảng PostgreSQL và kế hoạch Alembic migrations
