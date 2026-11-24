# AI Keyword Research & Content Planning Agent

A specialized **AI Agent for SEO Keyword Research & Content Planning**, built around **Data-driven**, **Evidence-based**, and **Human-in-the-loop** principles.

> This project focuses deeply on keyword research accuracy, SERP analysis, evidence-backed Search Intent classification, multi-signal Keyword Clustering, and SEO Content Brief generation — intentionally excluding Technical SEO Audits, Backlink Analysis, and Rank Tracking in V1.

---

## Core Principles

1. **Data-driven**: Every SEO metric comes from real data sources with full provenance; missing values (`NULL` with `NOT_AVAILABLE` / `NOT_COLLECTED` / `SOURCE_ERROR`) are strictly separated from `0`.
2. **Evidence-based**: AI never hallucinates metrics or URLs; every Search Intent classification, cluster, and Content Brief must reference real SERP evidence persisted in the database.
3. **Human-in-the-loop**: Three mandatory review checkpoints (Keyword List, Keyword Clusters, Content Brief) with full audit trails that preserve the original AI baseline.
4. **Modular Architecture**: A clean Modular Monolith with clear layer boundaries, easy to test, maintain, and swap data providers.
5. **Accuracy over Features**: Intent classification and clustering quality are evaluated quantitatively against a manually curated Golden Dataset.

---

## Confirmed V1 Architecture Decisions

| Area | Selected Approach |
| :--- | :--- |
| **Overall Architecture** | Modular Monolith (FastAPI + Celery + LangGraph + PostgreSQL + Redis) |
| **Primary SERP Provider** | **DataForSEO** (with optional DataForSEO Keywords Data API) |
| **Initial Keyword Metrics Sources** | **Semrush** (CSV/Excel Import + ready-to-use `SemrushConnector` API v4 with Mock) + **Spineditor** (CSV/Excel Import) + **Google Search Console** (OAuth 2.0 for verified properties) + optional DataForSEO Keyword API |
| **Frontend UI** | **React + TypeScript + Vite + Material UI (MUI)** (`@mui/x-data-grid`) |
| **Clustering Embeddings** | `BaseEmbeddingProvider`: V1 defaults to **OpenAI `text-embedding-3-small`**, switchable to local **Sentence Transformers** via `EMBEDDING_PROVIDER` |
| **Authentication & Security** | **JWT Auth (email/password)** from Sprint 1 + symmetric **Fernet** encryption for stored Google OAuth tokens |

---

## Repository Structure

```text
SEO-AI/
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
│   │   └── utils/               # Security (JWT, Fernet, SSRF guard), normalization, logging
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
│   ├── DATABASE.md
│   └── API_SPEC.md
├── .env.example
├── .editorconfig
├── .gitignore
├── docker-compose.yml
├── PROJECT_STATUS.md
├── TASKS.md
├── CHANGELOG.md
└── README.md
```

---

## Prerequisites

- **Python**: `3.12` (Docker runtime pins Python 3.12 for optimal ML/NLP wheel compatibility).
- **Node.js**: `20+`.
- **Docker & Docker Compose**: Runs PostgreSQL 16, Redis 7, Alembic `migrate`, FastAPI Backend, and Celery Worker.
- **Environment Variables**: Copy `.env.example` to `.env` for local overrides (never commit `.env`).

---

## Running Locally

### 1. Run the full stack with Docker Compose (Recommended)
```powershell
# (Optional) Copy environment template
Copy-Item .env.example .env

# Build and start PostgreSQL, Redis, Alembic migrate, FastAPI Backend, and Celery Worker
docker compose up -d --build

# Check container health
docker compose ps -a
```

Active endpoints once running:
- **Liveness**: `http://localhost:8000/health`
- **Readiness (Postgres + Redis)**: `http://localhost:8000/ready`
- **Swagger UI (dev mode)**: `http://localhost:8000/docs`

Stop the stack:
```powershell
docker compose down
```

### 2. Database Migrations (Alembic)
The `migrate` service in `docker-compose.yml` automatically runs `alembic upgrade head` on startup. For manual operations:
```powershell
# Check current revision and verify zero drift between ORM models and migrations
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check

# Or run locally against Postgres on localhost:5432
Set-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 3. Run Backend Tests Locally (Virtualenv)
```powershell
python -m venv backend/.venv
backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check app tests alembic
```

---

## Development Roadmap (8 Sprints)

- **Sprint 1**: Foundation, Database, JWT Auth & Project Management (`TASK-001` – `TASK-005`) — **Completed**
- **Sprint 2**: Data Connectors & File Import (`TASK-006` – `TASK-010`) — **In Progress**
- **Sprint 3**: Keyword Research & Cleaning Engine (`TASK-011` – `TASK-014`)
- **Sprint 4**: SERP Analysis, Competitor Headings & Search Intent (`TASK-015` – `TASK-018`)
- **Sprint 5**: Hybrid Keyword Clustering & Prioritization (`TASK-019` – `TASK-021`)
- **Sprint 6**: LangGraph AI Agent & Human-in-the-Loop Orchestration (`TASK-022` – `TASK-024`)
- **Sprint 7**: Content Brief Generation & Review (`TASK-025` – `TASK-027`)
- **Sprint 8**: Export (Excel / Google Sheets), React Dashboard, E2E & Deployment (`TASK-028` – `TASK-032`)

---

## Documentation

- [PROJECT_STATUS.md](./PROJECT_STATUS.md) – Sprint status, task progress, and integration readiness matrix
- [TASKS.md](./TASKS.md) – Full 8-Sprint / 32-Task development backlog
- [CHANGELOG.md](./CHANGELOG.md) – Project changelog
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) – Modular Monolith architecture, AI orchestration, and security controls
- [docs/DATABASE.md](./docs/DATABASE.md) – ERD, PostgreSQL table specifications, and Alembic migration plan
- [docs/API_SPEC.md](./docs/API_SPEC.md) – REST API specification for Ops, Auth, and Project Management endpoints
