# API SPECIFICATION – AI Keyword Research & Content Planning Agent

**Base URL (Local Dev)**: `http://localhost:8000`
**API v1 Prefix**: `/api/v1`
**Authentication**: JWT Bearer Token (`Authorization: Bearer <access_token>`)
**Request Tracing**: Supports `X-Request-ID` header (validated & echoed back, or auto-generated UUID4 hex).

---

## 1. Error Envelope Convention

All HTTP (`4xx`), Validation (`422`), and Server (`500`) errors return a consistent JSON envelope:

```json
{
  "error": {
    "code": "HTTP_401",
    "message": "Missing authentication token",
    "details": null,
    "request_id": "748f16df8d5d4b17990da5cff6f69398"
  }
}
```

---

## 2. Operational Endpoints (Unversioned)

| Method | Path | Auth | Description | Status Codes |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public | Liveness check (no external DB/Redis I/O) | `200` |
| `GET` | `/ready` | Public | Readiness check (`SELECT 1` PostgreSQL + `PING` Redis) | `200`, `503` |

---

## 3. Authentication Endpoints (`/api/v1/auth`)

| Method | Path | Auth | Description | Status Codes |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Public | Register a new member account (normalizes email to lowercase) | `201`, `409`, `422` |
| `POST` | `/api/v1/auth/login` | Public | Authenticate with email/password and receive a JWT Bearer token | `200`, `401`, `403`, `422` |
| `GET` | `/api/v1/auth/me` | Bearer JWT | Retrieve the authenticated user's profile | `200`, `401` |

---

## 4. Project Management Endpoints (`/api/v1/projects`)

All endpoints below require `Authorization: Bearer <token>` and enforce owner-scoped authorization (`owner_id == current_user.id`, or `role == "admin"`).

### Projects
| Method | Path | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/projects` | Create a new project and auto-initialize default `ProjectSettings` | `201`, `401`, `409`, `422` |
| `GET` | `/api/v1/projects` | List projects (`?status=ACTIVE\|ARCHIVED&search=...&limit=20&offset=0`) | `200`, `401`, `422` |
| `GET` | `/api/v1/projects/{project_id}` | Get full project detail including `settings`, `websites`, and `competitors` | `200`, `401`, `404` |
| `PATCH` | `/api/v1/projects/{project_id}` | Partially update project metadata or `status` (`ACTIVE`/`ARCHIVED`) | `200`, `401`, `404`, `409`, `422` |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete a project (cascades settings, websites, competitors) | `204`, `401`, `404` |

### Project Settings
| Method | Path | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/projects/{project_id}/settings` | Get configurable clustering/prioritization weights and SERP defaults | `200`, `401`, `404` |
| `PUT` | `/api/v1/projects/{project_id}/settings` | Update `clustering_weights` (must sum to 1.0), `prioritization_weights`, `default_device`, `default_serp_provider`, `custom_rules` | `200`, `401`, `404`, `422` |

### Project Websites
| Method | Path | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/projects/{project_id}/websites` | List websites linked to a project | `200`, `401`, `404` |
| `POST` | `/api/v1/projects/{project_id}/websites` | Add website (normalizes `domain` & `base_url`; `is_primary=true` atomically demotes prior primary) | `201`, `401`, `404`, `409`, `422` |
| `PATCH` | `/api/v1/projects/{project_id}/websites/{website_id}` | Update website details or promote to primary | `200`, `401`, `404`, `409`, `422` |
| `DELETE` | `/api/v1/projects/{project_id}/websites/{website_id}` | Remove a website from the project | `204`, `401`, `404` |

### Project Competitors
| Method | Path | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/projects/{project_id}/competitors` | List competitor domains tracked in a project | `200`, `401`, `404` |
| `POST` | `/api/v1/projects/{project_id}/competitors` | Add competitor (normalizes `domain`) | `201`, `401`, `404`, `409`, `422` |
| `PATCH` | `/api/v1/projects/{project_id}/competitors/{competitor_id}` | Update competitor details | `200`, `401`, `404`, `409`, `422` |
| `DELETE` | `/api/v1/projects/{project_id}/competitors/{competitor_id}` | Remove a competitor from the project | `204`, `401`, `404` |

---

## 5. Keyword Research, File Imports & Review 1 (`/api/v1/research-runs`, `/api/v1/keywords`)

| Method | Path | Description | Status Codes |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/projects/{project_id}/research-runs` | Create a Research Run snapshotting project settings and saving seed keywords | `201`, `401`, `404`, `422` |
| `GET` | `/api/v1/projects/{project_id}/research-runs` | List historical Research Runs for a project | `200`, `401`, `404` |
| `GET` | `/api/v1/research-runs/{run_id}` | Get Research Run details, seed keywords, and cleaning status counts | `200`, `401`, `404` |
| `POST` | `/api/v1/research-runs/{run_id}/imports` | Upload CSV/XLSX file (`multipart/form-data`: `source_code=gkp_csv\|spineditor_import\|semrush_csv`, `file`) | `201`, `401`, `404`, `413`, `422` |
| `POST` | `/api/v1/research-runs/{run_id}/clean` | Execute non-destructive keyword cleaning & deduplication | `200`, `401`, `404` |
| `GET` | `/api/v1/research-runs/{run_id}/keywords` | List keywords with latest aggregated metrics (`?cleaning_status=&review_status=&search=&limit=50&offset=0`) | `200`, `401`, `404` |
| `POST` | `/api/v1/research-runs/{run_id}/keywords` | Manually add an approved active keyword | `201`, `401`, `404`, `409`, `422` |
| `PATCH` | `/api/v1/keywords/{keyword_id}` | Review 1: Approve, reject, edit text, or mark irrelevant (preserves `original_keyword`) | `200`, `401`, `404`, `409`, `422` |
| `POST` | `/api/v1/research-runs/{run_id}/keywords/bulk-review` | Review 1: Bulk update `review_status` / `cleaning_status` | `200`, `401`, `404`, `422` |
