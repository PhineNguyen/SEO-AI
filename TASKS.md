# DEVELOPMENT BACKLOG – TASKS.md

**Status Legend**: `Completed` | `In Progress` | `Pending` | `Blocked`

---

## Sprint 1 (Epic 1): Foundation, Database & Project Management

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-001** | Initialize Repository, Project Structure & Documentation Baseline | Modular layout (`backend/`, `frontend/`, `docs/`), `.gitignore`, `.editorconfig`, `.env.example`, `pyproject.toml`, `requirements*.txt`, `frontend/package.json`, baseline docs, structure test. | None | Matches Section 15 layout; no leaked secrets; structure tests pass 100%; docs synced. | **Completed** |
| **TASK-002** | Docker Compose, FastAPI App Bootstrap, Config & Structured Logging | `Dockerfile` (Python 3.12), `docker-compose.yml` (Postgres 16, Redis 7, Backend, Celery), `config.py`, structlog JSON/console logging, `/health` & `/ready`. | TASK-001 | `docker compose up` succeeds; `/health` & `/ready` return 200; pytest passes. | **Completed** |
| **TASK-003** | SQLAlchemy 2.x Setup, Alembic & Core Migration (`001`) | Base model (UUID + TIMESTAMPTZ), session management, Alembic config, migration `001` (`users`, `oauth_credentials`, `projects`, `websites`, `project_settings`, `competitors`, `data_sources`) + seed `data_sources`. | TASK-002 | `alembic upgrade head`, `check`, and `downgrade base` pass cleanly; DB integration tests pass. | **Completed** |
| **TASK-004** | Authentication (JWT) & Token Encryption Utility | Register/Login/Me, JWT Bearer dependency, `Fernet` encrypt/decrypt utility for OAuth tokens. | TASK-003 | Protected routes return 401 without token; encrypt/decrypt & auth API tests pass. | **Completed** |
| **TASK-005** | Project Management CRUD APIs | Repository + Service + Routes `/api/v1/projects/...` (Projects, Websites, Settings, Competitors). | TASK-004 | Full CRUD + domain/country/language validation + ownership isolation + API tests pass. | **Completed** |

---

## Sprint 2 (Epic 2): Data Connectors & File Import Layer

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-006** | `BaseDataProvider`, Provenance Schemas & HTTP Resilience Layer | `BaseDataProvider` interface, DTOs with `data_status`/`unit`/`collected_at`, retry with exponential backoff, timeout, rate limiter & quota tracker. | TASK-003 | Unit tests pass for retry, timeout, rate limiting, and `NOT_AVAILABLE` vs `0` enforcement. | **Completed** |
| **TASK-007** | DataForSEO Connector (SERP + Optional Keywords Data + Mock Provider) | `DataForSeoSerpConnector` (Top 10 Organic + SERP Features + location/language/device), optional Keywords Data API, `MockDataForSeoProvider`. | TASK-006 | Mock tests pass 100%; live smoke test (when credentials provided) returns valid schema. | **Completed** |
| **TASK-008** | Semrush Connector (API v4 + CSV/Excel Import + Mock Provider) | `SemrushApiConnector` (v4 metrics & related keywords, quota handling) + `SemrushFileImporter` (CSV/XLSX). | TASK-006 | CSV import & mocked API responses map cleanly to provenance DTOs. | **Completed** |
| **TASK-009** | Google Search Console Connector (OAuth 2.0 + Search Analytics) | OAuth 2.0 auth/callback flow, encrypted token persistence, paginated `searchAnalytics` queries (`startRow`). | TASK-004, TASK-006 | Mocked Google API tests pass; access restricted to verified properties only. | **Completed** |
| **TASK-010** | Spineditor CSV/Excel Import Connector | Flexible CSV/XLSX parser, Vietnamese UTF-8 handling, metric validation, `source_imports` tracking. | TASK-006 | Sample file imports cleanly, reports `imported_rows`/`error_rows`, preserves raw data. | **Completed** |

---

## Sprint 3 (Epic 3): Keyword Research & Cleaning Engine

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-011** | Migration `002` & Research Run / Seed Keyword Management | Migration `002` (`research_runs`, `seed_keywords`, `source_imports`, `keywords`, `keyword_sources`, `keyword_metrics`, `keyword_tags`), CRUD APIs. | TASK-005 | Creates Research Run with config snapshot and isolated historical runs. | **Completed** |
| **TASK-012** | Keyword Discovery & Multi-source Data Collection Service | Orchestrate multi-source collection with fault isolation (one failing source never loses other sources' data). | TASK-007, TASK-008, TASK-009, TASK-010, TASK-011 | Integration test proves partial provider failure preserves all other collected records. | **Completed** |
| **TASK-013** | Keyword Cleaning & Normalization Service | Unicode/Vietnamese normalization, exact duplicates (`duplicate_of_keyword_id`), near-duplicates (`pg_trgm`), never drop keywords solely for low volume. | TASK-012 | Tests verify 100% original data recoverability; never replaces `NULL` with `0`. | **Completed** |
| **TASK-014** | Keyword Metrics Aggregation & Review 1 APIs | View keywords with multi-source metrics, filter/sort, Approve/Reject/Edit/Add/Mark Irrelevant. | TASK-013 | API tests pass; all user review changes persisted cleanly. | **Completed** |

---

## Sprint 4 (Epic 4): SERP Analysis, Competitor Headings & Search Intent

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-015** | Migration `003` & SERP Collection Service | Migration `003` (`serp_snapshots`, `serp_results`, `competitor_pages`, `competitor_headings`, `keyword_intents`), URL normalization. | TASK-007, TASK-013 | Append-only SERP snapshots tagged with country/language/device/collected_at. | **Completed** |
| **TASK-016** | Safe Competitor Heading Fetcher (SSRF-Protected) | Fetch HTML for Top 10 URLs, block private/loopback/metadata IPs (including redirects), 10s timeout, 2MB cap, parse H1–H3. | TASK-015 | Security tests block `127.0.0.1`, `169.254.169.254`, `localhost`, and internal DNS. | **Completed** |
| **TASK-017** | Evidence-based Search Intent Classification Service | Prompt-injection-hardened prompt, OpenAI Structured Outputs, SERP evidence validator, store `model_version` & `prompt_version`. | TASK-016 | Schema & anti-hallucination validator tests pass. | **Completed** |
| **TASK-018** | Golden Dataset v1 & Intent Evaluation Harness | 50–100 manually labeled keywords (VI + EN) + reproducible Accuracy/Precision/Recall/F1 report script. | TASK-017 | Generates reproducible baseline evaluation metrics. | **Completed** |

---

## Sprint 5 (Epic 5): Hybrid Keyword Clustering & Prioritization

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-019** | Migration `004` & Hybrid Clustering Engine | Migration `004`, `BaseEmbeddingProvider` (OpenAI + Sentence Transformers), Semantic + SERP Overlap + Intent (`0.3/0.5/0.2`), LLM naming/reasoning. | TASK-017 | Unit/integration tests & Golden Dataset F1 evaluation pass. | **Completed** |
| **TASK-020** | Clustering Manual Review APIs (Review 2) | Merge, Split, Move Keyword, Change Primary, Rename, Reject + `cluster_reviews` audit preserving AI baseline. | TASK-019 | No keyword belongs to 2 active clusters; complete audit trail recorded. | **Completed** |
| **TASK-021** | Configurable Keyword Prioritization Service | Weighted scoring from `project_settings` + per-keyword reasoning; safe handling of `NULL` metrics. | TASK-019 | Changing weights shifts ranking as expected; every score includes an explanation. | **Completed** |

---

## Sprint 6 (Epic 6): LangGraph AI Agent & Human-in-the-Loop Orchestration

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-022** | Migration `005`, LangGraph State & Postgres Checkpointer Setup | Migration `005` (`workflow_executions`, `workflow_checkpoints`, `review_decisions`), pointer-based state, `PostgresSaver`. | TASK-011 | Checkpoints persist in PostgreSQL and survive process restarts. | **Completed** |
| **TASK-023** | Build `KeywordResearchGraph` (15 Nodes + 3 Mandatory Interrupts) | All 15 nodes + conditional routing + 3 `interrupt()` gates (Keywords, Clusters, Briefs). | TASK-014, TASK-020, TASK-021, TASK-022 | Mocked E2E LangGraph tests pause & resume accurately by `thread_id`. | **Completed** |
| **TASK-024** | Celery Workers & Workflow Control APIs | Async Celery start/resume tasks; REST API Start / Status / Resume / Cancel. | TASK-023 | Integration test verifies Start → Wait Review 1 → Approve → Resume via Celery. | **Completed** |

---

## Sprint 7 (Epic 7): Content Brief Generation & Review

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-025** | Migration `006` & Evidence-based Content Brief Service | Migration `006` (`content_briefs`, `brief_keywords`, `brief_sections`, `brief_faqs`, `brief_reviews`, `export_jobs`), all 17 brief sections. | TASK-021 | Valid structured output; never invents minimum word-count or keyword-density rules. | **Completed** |
| **TASK-026** | Content Brief Validator (Anti-Hallucination & Coverage Check) | Verify all referenced keywords belong to cluster and competitor URLs exist in `serp_results`; bounded regeneration (max 2 retries). | TASK-025 | Simulated LLM hallucination of URLs/keywords is caught and handled. | **Completed** |
| **TASK-027** | Content Brief Review & Regeneration APIs (Review 3) | Edit Title/Meta/Headings/Angle/FAQ/Primary Keyword, Approve, Request Regeneration (versioned, preserves AI baseline). | TASK-026 | Versioning & review audit tests pass without losing original AI output. | **Completed** |

---

## Sprint 8 (Epic 8): Export Services, React Dashboard, E2E & Deployment

| Task ID | Task Name | Key Subtasks | Dependency | Acceptance Criteria | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-028** | Excel Export Service (OpenPyXL – 7 Sheets) | Export `.xlsx` with 7 sheets (Overview, All Keywords, SERP Analysis, Search Intent, Keyword Clusters, Content Brief, Data Sources) + styling/filters/hyperlinks. | TASK-025 | Automated test verifies all 7 sheets, headers, and data integrity. | **Completed** |
| **TASK-029** | Google Sheets Export Service (OAuth + Batch Update) | Google Sheets API using encrypted OAuth tokens, create Spreadsheet + 7 Worksheets, track `export_jobs`. | TASK-004, TASK-028 | Mocked integration tests pass; clear error handling when OAuth permission is absent. | **Completed** |
| **TASK-030** | Frontend Setup & Core Pages (MUI + Vite) | React + TS + MUI (`@mui/x-data-grid`), Auth UI, Project/Settings CRUD, Research Run launcher, CSV upload, workflow status. | TASK-005, TASK-024 | Clean `npm run build`; Project → Research Run flow works E2E. | **Completed** |
| **TASK-031** | Frontend Human-in-the-Loop Review UIs (Review 1, 2, 3 & Export) | Keyword Review DataGrid, Clustering Review (Merge/Split/Move), Content Brief Editor & Review, Export controls. | TASK-030, TASK-027, TASK-028 | All 3 HITL loops complete in UI and Excel download succeeds. | **Completed** |
| **TASK-032** | E2E Testing, Security Review, Production Docker & Final Docs | Full E2E test (including mid-run server restart & resume), OWASP/SSRF/Prompt Injection audit, complete Section 19 docs. | TASK-029, TASK-031 | All 18 V1 acceptance criteria in Section 18 verified with test evidence. | **Completed** |

---

## Future Improvements (Out of Scope V1 – Rule 8)
- Technical SEO Site Audit & Crawl Diagnostics
- Backlink Profile & Referring Domains Analysis
- Scheduled Daily/Weekly Rank Tracking
- Full AI Article Drafting & CMS Auto-Publishing (WordPress / Webflow)
- Multi-tenant Organization Billing & Usage Quotas
