# API SPECIFICATION – AI Keyword Research & Content Planning Agent

**Base URL (Local Dev)**: `http://localhost:8000`
**API v1 Prefix**: `/api/v1`
**Authentication**: JWT Bearer Token (`Authorization: Bearer <access_token>`)
**Request Tracing**: Hỗ trợ header `X-Request-ID` (echo lại hoặc tự sinh UUID4 hex).

---

## 1. Quy ước Error Envelope

Toàn bộ lỗi HTTP (`4xx`), Validation (`422`), và Server (`500`) trả về định dạng thống nhất:

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

| Method | Path | Auth | Mô tả | Status Codes |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/health` | Public | Liveness check (không gọi DB/Redis) | `200` |
| `GET` | `/ready` | Public | Readiness check (`SELECT 1` PostgreSQL + `PING` Redis) | `200`, `503` |

---

## 3. Authentication Endpoints (`/api/v1/auth`)

| Method | Path | Auth | Mô tả | Status Codes |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/register` | Public | Đăng ký tài khoản (`role="member"`, chuẩn hóa email lowercase) | `201`, `409`, `422` |
| `POST` | `/api/v1/auth/login` | Public | Đăng nhập bằng email/password và nhận JWT Bearer token | `200`, `401`, `403`, `422` |
| `GET` | `/api/v1/auth/me` | Bearer JWT | Lấy thông tin người dùng hiện tại | `200`, `401` |

---

## 4. Project Management Endpoints (`/api/v1/projects`)

Toàn bộ endpoints dưới đây yêu cầu `Authorization: Bearer <token>` và áp dụng phân quyền theo chủ sở hữu (`owner_id == current_user.id`, hoặc `role == "admin"`).

### Projects
| Method | Path | Mô tả | Status Codes |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/projects` | Tạo project mới và tự động khởi tạo `ProjectSettings` mặc định | `201`, `401`, `409`, `422` |
| `GET` | `/api/v1/projects` | Liệt kê projects (`?status=ACTIVE\|ARCHIVED&search=...&limit=20&offset=0`) | `200`, `401`, `422` |
| `GET` | `/api/v1/projects/{project_id}` | Xem chi tiết project kèm `settings`, `websites`, `competitors` | `200`, `401`, `404` |
| `PATCH` | `/api/v1/projects/{project_id}` | Cập nhật một phần thông tin project hoặc đổi `status` (`ACTIVE`/`ARCHIVED`) | `200`, `401`, `404`, `409`, `422` |
| `DELETE` | `/api/v1/projects/{project_id}` | Xóa project (cascade xóa settings, websites, competitors) | `204`, `401`, `404` |

### Project Settings
| Method | Path | Mô tả | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/projects/{project_id}/settings` | Lấy cấu hình trọng số clustering/prioritization và SERP defaults | `200`, `401`, `404` |
| `PUT` | `/api/v1/projects/{project_id}/settings` | Cập nhật `clustering_weights` (tổng = 1.0), `prioritization_weights`, `default_device`, `default_serp_provider`, `custom_rules` | `200`, `401`, `404`, `422` |

### Project Websites
| Method | Path | Mô tả | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/projects/{project_id}/websites` | Liệt kê website của project | `200`, `401`, `404` |
| `POST` | `/api/v1/projects/{project_id}/websites` | Thêm website (tự chuẩn hóa `domain` & `base_url`; nếu `is_primary=true` tự động hạ primary cũ) | `201`, `401`, `404`, `409`, `422` |
| `PATCH` | `/api/v1/projects/{project_id}/websites/{website_id}` | Cập nhật website hoặc đổi `is_primary=true` | `200`, `401`, `404`, `409`, `422` |
| `DELETE` | `/api/v1/projects/{project_id}/websites/{website_id}` | Xóa website khỏi project | `204`, `401`, `404` |

### Project Competitors
| Method | Path | Mô tả | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/projects/{project_id}/competitors` | Liệt kê đối thủ cạnh tranh của project | `200`, `401`, `404` |
| `POST` | `/api/v1/projects/{project_id}/competitors` | Thêm đối thủ (tự chuẩn hóa `domain`) | `201`, `401`, `404`, `409`, `422` |
| `PATCH` | `/api/v1/projects/{project_id}/competitors/{competitor_id}` | Cập nhật thông tin đối thủ | `200`, `401`, `404`, `409`, `422` |
| `DELETE` | `/api/v1/projects/{project_id}/competitors/{competitor_id}` | Xóa đối thủ khỏi project | `204`, `401`, `404` |
