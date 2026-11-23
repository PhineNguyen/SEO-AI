# DEVELOPMENT BACKLOG – TASKS.md

**Quy ước trạng thái**: `Completed` | `In Progress` | `Pending` | `Blocked`

---

## Sprint 1 (Epic 1): Foundation, Database & Project Management

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-001** | Initialize Repository, Project Structure & Documentation Baseline | Cấu trúc `backend/`, `frontend/`, `docs/`, `.gitignore`, `.editorconfig`, `.env.example`, `pyproject.toml`, `requirements*.txt`, `frontend/package.json`, bộ docs nền tảng, test kiểm tra cấu trúc. | None | Cấu trúc khớp Section 15; không lộ secrets; `unittest` pass 100%; tài liệu đồng bộ. | **Completed** |
| **TASK-002** | Docker Compose, FastAPI App Bootstrap, Config & Structured Logging | `Dockerfile` (Python 3.12), `docker-compose.yml` (Postgres 16, Redis 7, Backend, Celery), `config.py`, structlog JSON logging, `/health` & `/ready`. | TASK-001 | `docker compose up` chạy thành công; `/health` trả 200; pytest setup pass. | **Completed** |
| **TASK-003** | SQLAlchemy 2.x Setup, Alembic & Core Migration (`001`) | Base model (UUID + TIMESTAMPTZ), session management, Alembic config, migration `001` (`users`, `oauth_credentials`, `projects`, `websites`, `project_settings`, `competitors`, `data_sources`) + seed `data_sources`. | TASK-002 | `alembic upgrade head` & `downgrade base` sạch; DB integration test pass. | **Completed** |
| **TASK-004** | Authentication (JWT) & Token Encryption Utility | Register/Login, JWT access token dependency, `Fernet` encrypt/decrypt helper cho OAuth tokens. | TASK-003 | Protected route trả 401 khi thiếu token; unit test encrypt/decrypt pass. | **Completed** |
| **TASK-005** | Project Management CRUD APIs | Repository + Service + Routes `/api/v1/projects/...` (Projects, Websites, Settings, Competitors). | TASK-004 | Full CRUD + validation (country/language/domain) + API tests pass. | **Completed** |

---

## Sprint 2 (Epic 2): Data Connectors & File Import Layer

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-006** | `BaseDataProvider`, Provenance Schemas & HTTP Resilience Layer | Interface `BaseDataProvider`, DTO có `data_status`/`unit`/`collected_at`, retry + exponential backoff, timeout, rate-limit tracker. | TASK-003 | Unit tests pass cho retry, timeout, rate limit và phân biệt `NOT_AVAILABLE` vs `0`. | Pending |
| **TASK-007** | DataForSEO Connector (SERP + Optional Keywords Data + Mock Provider) | `DataForSeoSerpConnector` (Top 10 Organic + SERP Features + location/language/device), tùy chọn Keywords Data API, `MockDataForSeoProvider`. | TASK-006 | Mock tests pass 100%; smoke test thật (nếu có credentials) trả đúng schema. | Pending |
| **TASK-008** | Semrush Connector (API v4 + CSV/Excel Import + Mock Provider) | `SemrushApiConnector` (v4 metrics & related keywords, quota handling) + `SemrushFileImporter` (CSV/XLSX). | TASK-006 | Parse CSV thực tế & mock API response ra đúng provenance schema. | Pending |
| **TASK-009** | Google Search Console Connector (OAuth 2.0 + Search Analytics) | OAuth 2.0 auth/callback flow, lưu encrypted token, query `searchAnalytics` có pagination `startRow`. | TASK-004, TASK-006 | Mocked Google API tests pass; chỉ truy cập property đã verify quyền. | Pending |
| **TASK-010** | Spineditor CSV/Excel Import Connector | Parser CSV/XLSX linh hoạt, xử lý UTF-8/tiếng Việt, validate metrics, ghi vết `source_imports`. | TASK-006 | Import file mẫu thành công, thống kê `imported_rows`/`error_rows`, bảo toàn raw data. | Pending |

---

## Sprint 3 (Epic 3): Keyword Research & Cleaning Engine

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-011** | Migration `002` & Research Run / Seed Keyword Management | Migration `002` (`research_runs`, `seed_keywords`, `source_imports`, `keywords`, `keyword_sources`, `keyword_metrics`, `keyword_tags`), CRUD APIs. | TASK-005 | Tạo Research Run snapshot cấu hình project và lưu lịch sử độc lập. | Pending |
| **TASK-012** | Keyword Discovery & Multi-source Data Collection Service | Điều phối thu thập đa nguồn với fault-isolation (1 nguồn lỗi không mất dữ liệu nguồn khác). | TASK-007, TASK-008, TASK-009, TASK-010, TASK-011 | Integration test chứng minh lỗi cục bộ không làm mất dữ liệu từ nguồn khác. | Pending |
| **TASK-013** | Keyword Cleaning & Normalization Service | Chuẩn hóa Unicode/tiếng Việt, exact duplicate (`duplicate_of_keyword_id`), near-duplicate (`pg_trgm`), không xóa keyword chỉ vì volume thấp. | TASK-012 | Tests xác minh 100% dữ liệu gốc khôi phục được; không điền `0` cho thiếu dữ liệu. | Pending |
| **TASK-014** | Keyword Metrics Aggregation & Review 1 APIs | API xem keyword kèm metrics đa nguồn, filter/sort, Approve/Reject/Edit/Add/Mark Irrelevant. | TASK-013 | API tests pass; mọi chỉnh sửa lưu vết đầy đủ. | Pending |

---

## Sprint 4 (Epic 4): SERP Analysis, Competitor Headings & Search Intent

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-015** | Migration `003` & SERP Collection Service | Migration `003` (`serp_snapshots`, `serp_results`, `competitor_pages`, `competitor_headings`, `keyword_intents`), URL normalization. | TASK-007, TASK-013 | Lưu SERP snapshot append-only gắn country/language/device/collected_at. | Pending |
| **TASK-016** | Safe Competitor Heading Fetcher (SSRF-Protected) | Fetch HTML Top 10 URLs, chặn private/loopback/metadata IP (kể cả sau redirect), timeout 10s, limit 2MB, parse H1–H3. | TASK-015 | Security tests chặn `127.0.0.1`, `169.254.169.254`, `localhost`, internal DNS. | Pending |
| **TASK-017** | Evidence-based Search Intent Classification Service | Prompt chống injection, OpenAI Structured Outputs, validator kiểm tra SERP evidence, lưu `model_version` & `prompt_version`. | TASK-016 | Schema & anti-hallucination validator tests pass. | Pending |
| **TASK-018** | Golden Dataset v1 & Intent Evaluation Harness | Bộ 50–100 keyword gán nhãn thủ công (VI + EN) + script đo Accuracy/Precision/Recall/F1. | TASK-017 | Xuất báo cáo metrics thực nghiệm có thể tái lập. | Pending |

---

## Sprint 5 (Epic 5): Hybrid Keyword Clustering & Prioritization

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-019** | Migration `004` & Hybrid Clustering Engine | Migration `004`, `BaseEmbeddingProvider` (OpenAI + Sentence Transformers), Semantic + SERP Overlap + Intent (`0.3/0.5/0.2`), LLM naming/reasoning. | TASK-017 | Unit/integration tests & Golden Dataset F1 evaluation pass. | Pending |
| **TASK-020** | Clustering Manual Review APIs (Review 2) | Merge, Split, Move Keyword, Change Primary, Rename, Reject + ghi `cluster_reviews` giữ AI baseline. | TASK-019 | Không có keyword nằm trong 2 active clusters; audit trail đầy đủ. | Pending |
| **TASK-021** | Configurable Keyword Prioritization Service | Chấm điểm theo trọng số trong `project_settings` + giải thích lý do ưu tiên; xử lý an toàn khi metric là `NULL`. | TASK-019 | Đổi trọng số làm thay đổi ranking đúng kỳ vọng; có explanation cho mỗi keyword. | Pending |

---

## Sprint 6 (Epic 6): LangGraph AI Agent & Human-in-the-Loop Orchestration

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-022** | Migration `005`, LangGraph State & Postgres Checkpointer Setup | Migration `005` (`workflow_executions`, `workflow_checkpoints`, `review_decisions`), pointer-based state, PostgresSaver. | TASK-011 | Checkpoint lưu xuống Postgres và khôi phục được sau restart process. | Pending |
| **TASK-023** | Build `KeywordResearchGraph` (15 Nodes + 3 Mandatory Interrupts) | 15 nodes đầy đủ + conditional edges + 3 điểm `interrupt()` (Keywords, Clusters, Briefs). | TASK-014, TASK-020, TASK-021, TASK-022 | LangGraph E2E test (mocked externals) dừng & resume chính xác theo `thread_id`. | Pending |
| **TASK-024** | Celery Workers & Workflow Control APIs | Celery tasks chạy/resume graph bất đồng bộ; REST API Start / Status / Resume / Cancel. | TASK-023 | Integration test Start → Wait Review 1 → Approve → Resume chạy mượt qua Celery. | Pending |

---

## Sprint 7 (Epic 7): Content Brief Generation & Review

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-025** | Migration `006` & Evidence-based Content Brief Service | Migration `006` (`content_briefs`, `brief_keywords`, `brief_sections`, `brief_faqs`, `brief_reviews`, `export_jobs`), đủ 17 thành phần Brief. | TASK-021 | Structured output hợp lệ; không bịa word-count/keyword-density như chuẩn Google. | Pending |
| **TASK-026** | Content Brief Validator (Anti-Hallucination & Coverage Check) | Kiểm tra keyword thuộc cluster, competitor URLs có trong `serp_results`, bounded regeneration (tối đa 2 lần). | TASK-025 | Test mô phỏng LLM bịa URL/keyword bị chặn và xử lý đúng. | Pending |
| **TASK-027** | Content Brief Review & Regeneration APIs (Review 3) | Edit Title/Meta/Headings/Angle/FAQ/Primary Keyword, Approve, Request Regeneration (version mới, giữ AI baseline). | TASK-026 | API & versioning tests pass; không mất dữ liệu AI gốc. | Pending |

---

## Sprint 8 (Epic 8): Export Services, React Dashboard, E2E & Deployment

| Task ID | Tên Task | Subtasks chính | Dependency | Acceptance Criteria | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TASK-028** | Excel Export Service (OpenPyXL – 7 Sheets) | Xuất `.xlsx` đủ 7 sheets (Overview, All Keywords, SERP Analysis, Search Intent, Keyword Clusters, Content Brief, Data Sources) + formatting/filters/hyperlinks. | TASK-025 | Automated test kiểm tra đủ 7 sheets, headers, data integrity, mở sạch trên Excel. | Pending |
| **TASK-029** | Google Sheets Export Service (OAuth + Batch Update) | Google Sheets API dùng OAuth token đã mã hóa, tạo Spreadsheet + 7 Worksheets, tracking `export_jobs`. | TASK-004, TASK-028 | Mocked integration tests pass; báo lỗi rõ khi thiếu quyền OAuth. | Pending |
| **TASK-030** | Frontend Setup & Core Pages (MUI + Vite) | React + TS + MUI (`@mui/x-data-grid`), Auth UI, Project/Settings CRUD, Research Run launcher, CSV upload, workflow status. | TASK-005, TASK-024 | `npm run build` sạch; luồng Project → Research Run hoạt động E2E. | Pending |
| **TASK-031** | Frontend Human-in-the-Loop Review UIs (Review 1, 2, 3 & Export) | Keyword Review DataGrid, Clustering Review (Merge/Split/Move), Content Brief Editor & Review, Export buttons. | TASK-030, TASK-027, TASK-028 | Hoàn thành đủ 3 vòng HITL trên UI và tải được Excel. | Pending |
| **TASK-032** | E2E Testing, Security Review, Production Docker & Final Docs | E2E test (gồm kịch bản restart giữa chừng), audit bảo mật (OWASP/SSRF/Prompt Injection), hoàn tất bộ docs Section 19. | TASK-029, TASK-031 | Toàn bộ 18 tiêu chí Section 18 đạt và có bằng chứng kiểm thử. | Pending |

---

## Future Improvements (Out of Scope V1 – Ghi nhận theo Rule 8)
- Technical SEO Site Audit & Crawl Diagnostics
- Backlink Profile & Referring Domains Analysis
- Scheduled Daily/Weekly Rank Tracking
- Full AI Article Drafting & CMS Auto-Publishing (WordPress / Webflow)
- Multi-tenant Organization Billing & Usage Quotas
