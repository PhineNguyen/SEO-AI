"""Semrush API v4 connector, Semrush CSV/Excel file importer, and Mock provider."""

import hashlib
import io
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.config import Settings
from app.connectors.base import BaseDataProvider
from app.connectors.exceptions import (
    ConnectorError,
    ConnectorQuotaExceededError,
)
from app.connectors.http_client import RateLimiter, ResilientHttpClient, RetryConfig
from app.schemas.provenance import (
    DataStatus,
    KeywordCandidateType,
    KeywordIdeaRecord,
    MetricRecord,
    MetricType,
    ProviderErrorRecord,
    ProviderResult,
)
from app.utils.normalization import normalize_country_code, normalize_language_code

MISSING_VALUE_TOKENS: set[str] = {"", "-", "n/a", "na", "null", "none", "nan"}


def _parse_optional_float(raw: Any) -> tuple[float | None, str | None]:
    """Parse a numeric value from CSV/JSON while strictly preserving missing vs zero."""
    if raw is None:
        return None, None
    if isinstance(raw, float) and pd.isna(raw):
        return None, None
    text = str(raw).strip()
    if text.lower() in MISSING_VALUE_TOKENS:
        return None, text or None
    cleaned = text.replace("%", "").replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned), text
    except ValueError:
        return None, text


class FileImportReport(BaseModel):
    """Structured import summary suitable for persisting to source_imports."""

    source_code: str
    file_name: str
    file_hash_sha256: str
    column_mapping: dict[str, str] = Field(default_factory=dict)
    total_rows: int = 0
    imported_rows: int = 0
    error_rows: int = 0
    error_details: list[dict[str, Any]] = Field(default_factory=list)
    result: ProviderResult[KeywordIdeaRecord]


class SemrushApiConnector(BaseDataProvider):
    """Semrush API v4 connector for keyword metrics and related keyword ideas.

    Requires an active Semrush Business Plan + API Units balance for live calls.
    """

    provider_code = "semrush_api"
    supports_serp = False
    supports_keyword_ideas = True
    supports_keyword_metrics = True

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.semrush.com",
        http_client: ResilientHttpClient | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._http = http_client or ResilientHttpClient(
            provider_code=self.provider_code,
            base_url=base_url.rstrip("/"),
            timeout_seconds=timeout_seconds,
            retry_config=RetryConfig(max_attempts=3, base_delay_seconds=0.5),
            rate_limiter=RateLimiter(requests_per_second=5.0),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "SemrushApiConnector":
        api_key = (
            settings.SEMRUSH_API_KEY.get_secret_value()
            if settings.SEMRUSH_API_KEY is not None
            else None
        )
        return cls(
            api_key=api_key,
            base_url=settings.SEMRUSH_API_BASE_URL,
        )

    def check_credentials(self) -> bool:
        return bool(self._api_key)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        self.require_credentials()
        return {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}

    def _build_keyword_record(
        self,
        payload: dict[str, Any],
        *,
        fallback_keyword: str,
        country_code: str,
        language_code: str,
        keyword_type: KeywordCandidateType,
        collected_at: datetime,
    ) -> KeywordIdeaRecord:
        kw = str(payload.get("keyword") or fallback_keyword)
        metrics: list[MetricRecord] = []

        metric_specs = [
            ("volume", MetricType.SEARCH_VOLUME, "searches/month", None),
            ("keyword_difficulty", MetricType.KEYWORD_DIFFICULTY, "score_0_100", None),
            ("cpc", MetricType.CPC, "USD", "USD"),
            ("competition", MetricType.COMPETITION, "ratio_0_1", None),
        ]
        for json_key, metric_type, unit, currency in metric_specs:
            val, raw = _parse_optional_float(payload.get(json_key))
            if val is not None:
                metrics.append(
                    MetricRecord.available(
                        metric_type=metric_type,
                        source_code=self.provider_code,
                        numeric_value=val,
                        raw_value=raw,
                        unit=unit,
                        currency=currency,
                        country_code=country_code,
                        language_code=language_code,
                        collected_at=collected_at,
                    )
                )
            else:
                metrics.append(
                    MetricRecord.missing(
                        metric_type=metric_type,
                        source_code=self.provider_code,
                        unit=unit,
                        currency=currency,
                        raw_value=raw,
                        country_code=country_code,
                        language_code=language_code,
                        collected_at=collected_at,
                    )
                )

        serp_features = payload.get("serp_features") or []
        if isinstance(serp_features, str):
            serp_features = [f.strip() for f in serp_features.split(",") if f.strip()]

        return KeywordIdeaRecord(
            original_keyword=kw,
            keyword_type=keyword_type,
            source_code=self.provider_code,
            country_code=country_code,
            language_code=language_code,
            collected_at=collected_at,
            metrics=metrics,
            source_intent=payload.get("intent"),
            serp_features=list(serp_features),
        )

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Fetch Semrush API v4 keyword overview metrics with per-keyword fault isolation."""
        start = time.perf_counter()
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        items: list[KeywordIdeaRecord] = []
        errors: list[ProviderErrorRecord] = []
        collected_at = datetime.now(UTC)

        for keyword in keywords:
            try:
                response = self._http.get(
                    "/apis/v4/keywords/v1/metrics",
                    params={"keyword": keyword, "country": cc.lower()},
                    headers=self._headers(),
                    units=20.0,
                )
                data = response.json()
                if isinstance(data, dict) and data.get("error_code") == "QUOTA_EXCEEDED":
                    raise ConnectorQuotaExceededError(
                        self.provider_code,
                        str(data.get("message") or "Semrush API units exhausted"),
                    )
                items.append(
                    self._build_keyword_record(
                        data if isinstance(data, dict) else {},
                        fallback_keyword=keyword,
                        country_code=cc,
                        language_code=lc,
                        keyword_type=KeywordCandidateType.PRIMARY_CANDIDATE,
                        collected_at=collected_at,
                    )
                )
            except ConnectorQuotaExceededError as exc:
                errors.append(exc.to_error_record(context={"keyword": keyword}))
                break
            except ConnectorError as exc:
                errors.append(exc.to_error_record(context={"keyword": keyword}))

        status = "OK" if not errors else ("PARTIAL" if items else "ERROR")
        return ProviderResult(
            provider_code=self.provider_code,
            status=status,
            items=items,
            errors=errors,
            quota_used=self._http.quota.units_consumed,
            duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
        )

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Fetch related keyword ideas from Semrush API v4."""
        start = time.perf_counter()
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)

        try:
            response = self._http.get(
                "/apis/v4/keywords/v1/ideas/related",
                params={"keyword": seed_keyword, "country": cc.lower(), "limit": limit},
                headers=self._headers(),
                units=float(limit),
            )
            body = response.json()
        except ConnectorError as exc:
            return ProviderResult(
                provider_code=self.provider_code,
                status="ERROR",
                items=[],
                errors=[exc.to_error_record(context={"seed_keyword": seed_keyword})],
                duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            )

        collected_at = datetime.now(UTC)
        raw_items = body.get("data", []) if isinstance(body, dict) else []
        records = [
            self._build_keyword_record(
                item,
                fallback_keyword=str(item.get("keyword") or ""),
                country_code=cc,
                language_code=lc,
                keyword_type=KeywordCandidateType.RELATED,
                collected_at=collected_at,
            )
            for item in raw_items[:limit]
            if isinstance(item, dict) and str(item.get("keyword") or "").strip()
        ]

        return ProviderResult(
            provider_code=self.provider_code,
            status="OK",
            items=records,
            quota_used=self._http.quota.units_consumed,
            duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
        )

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return self.get_related_keywords(
            seed_keyword,
            country_code=country_code,
            language_code=language_code,
            limit=limit,
        )


class SemrushFileImporter:
    """Parser for Semrush Keyword Magic Tool / Keyword Overview CSV & XLSX exports."""

    source_code = "semrush_csv"

    COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
        "keyword": ("keyword", "phrase", "keywords"),
        "volume": ("volume", "search volume", "search_volume"),
        "kd": ("keyword difficulty", "kd", "kd %", "keyword_difficulty"),
        "cpc": ("cpc (usd)", "cpc", "cpc(usd)"),
        "competition": ("competitive density", "competition", "com."),
        "intent": ("intent", "search intent"),
        "serp_features": ("serp features", "serp_features"),
    }

    def _detect_columns(
        self,
        headers: list[str],
        override_mapping: dict[str, str] | None = None,
    ) -> dict[str, str]:
        normalized_headers = {h.strip().lower(): h for h in headers}
        mapping: dict[str, str] = {}
        for canonical, aliases in self.COLUMN_ALIASES.items():
            if override_mapping and canonical in override_mapping:
                mapping[canonical] = override_mapping[canonical]
                continue
            for alias in aliases:
                if alias in normalized_headers:
                    mapping[canonical] = normalized_headers[alias]
                    break
        return mapping

    def import_bytes(
        self,
        content: bytes,
        *,
        file_name: str,
        country_code: str,
        language_code: str,
        column_mapping: dict[str, str] | None = None,
    ) -> FileImportReport:
        """Parse a Semrush CSV or XLSX export into provenance-annotated KeywordIdeaRecords."""
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        file_hash = hashlib.sha256(content).hexdigest()
        lower_name = file_name.lower()

        if lower_name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(content), dtype=object)
        else:
            decoded = content.decode("utf-8-sig")
            df = pd.read_csv(io.StringIO(decoded), dtype=object)

        mapping = self._detect_columns(list(df.columns), column_mapping)
        if "keyword" not in mapping:
            err = ProviderErrorRecord(
                provider_code=self.source_code,
                error_code="MISSING_KEYWORD_COLUMN",
                message="Required 'Keyword' column was not found in Semrush export",
            )
            return FileImportReport(
                source_code=self.source_code,
                file_name=file_name,
                file_hash_sha256=file_hash,
                column_mapping=mapping,
                total_rows=len(df),
                imported_rows=0,
                error_rows=len(df),
                error_details=[{"row": 0, "error": err.message}],
                result=ProviderResult(
                    provider_code=self.source_code,
                    status="ERROR",
                    items=[],
                    errors=[err],
                ),
            )

        collected_at = datetime.now(UTC)
        items: list[KeywordIdeaRecord] = []
        error_details: list[dict[str, Any]] = []

        for idx, row in df.iterrows():
            row_number = int(idx) + 2  # 1-based Excel row accounting for header
            raw_kw = row.get(mapping["keyword"])
            kw_str = "" if raw_kw is None or (isinstance(raw_kw, float) and pd.isna(raw_kw)) else str(raw_kw)
            if not kw_str.strip():
                error_details.append({"row": row_number, "error": "Empty keyword"})
                continue

            metrics: list[MetricRecord] = []
            metric_cols = [
                ("volume", MetricType.SEARCH_VOLUME, "searches/month", None),
                ("kd", MetricType.KEYWORD_DIFFICULTY, "score_0_100", None),
                ("cpc", MetricType.CPC, "USD", "USD"),
                ("competition", MetricType.COMPETITION, "ratio_0_1", None),
            ]
            for key, metric_type, unit, currency in metric_cols:
                col_name = mapping.get(key)
                if not col_name:
                    metrics.append(
                        MetricRecord.missing(
                            metric_type=metric_type,
                            source_code=self.source_code,
                            unit=unit,
                            currency=currency,
                            country_code=cc,
                            language_code=lc,
                            data_status=DataStatus.NOT_COLLECTED,
                            collected_at=collected_at,
                        )
                    )
                    continue
                val, raw_val = _parse_optional_float(row.get(col_name))
                if val is not None:
                    metrics.append(
                        MetricRecord.available(
                            metric_type=metric_type,
                            source_code=self.source_code,
                            numeric_value=val,
                            raw_value=raw_val,
                            unit=unit,
                            currency=currency,
                            country_code=cc,
                            language_code=lc,
                            source_record_id=f"{file_name}:row:{row_number}",
                            collected_at=collected_at,
                        )
                    )
                else:
                    metrics.append(
                        MetricRecord.missing(
                            metric_type=metric_type,
                            source_code=self.source_code,
                            unit=unit,
                            currency=currency,
                            raw_value=raw_val,
                            country_code=cc,
                            language_code=lc,
                            data_status=DataStatus.NOT_AVAILABLE,
                            source_record_id=f"{file_name}:row:{row_number}",
                            collected_at=collected_at,
                        )
                    )

            intent_val = None
            if "intent" in mapping:
                raw_intent = row.get(mapping["intent"])
                if raw_intent is not None and not (isinstance(raw_intent, float) and pd.isna(raw_intent)):
                    cleaned_intent = str(raw_intent).strip()
                    if cleaned_intent.lower() not in MISSING_VALUE_TOKENS:
                        intent_val = cleaned_intent

            serp_features: list[str] = []
            if "serp_features" in mapping:
                raw_sf = row.get(mapping["serp_features"])
                if raw_sf is not None and not (isinstance(raw_sf, float) and pd.isna(raw_sf)):
                    sf_text = str(raw_sf).strip()
                    if sf_text.lower() not in MISSING_VALUE_TOKENS:
                        serp_features = [s.strip() for s in sf_text.split(",") if s.strip()]

            items.append(
                KeywordIdeaRecord(
                    original_keyword=kw_str,
                    keyword_type=KeywordCandidateType.RELATED,
                    source_code=self.source_code,
                    source_record_id=f"{file_name}:row:{row_number}",
                    country_code=cc,
                    language_code=lc,
                    collected_at=collected_at,
                    metrics=metrics,
                    source_intent=intent_val,
                    serp_features=serp_features,
                )
            )

        status = "OK" if not error_details else ("PARTIAL" if items else "ERROR")
        return FileImportReport(
            source_code=self.source_code,
            file_name=file_name,
            file_hash_sha256=file_hash,
            column_mapping=mapping,
            total_rows=len(df),
            imported_rows=len(items),
            error_rows=len(error_details),
            error_details=error_details,
            result=ProviderResult(
                provider_code=self.source_code,
                status=status,
                items=items,
            ),
        )


class MockSemrushProvider(BaseDataProvider):
    """Explicit deterministic Mock provider for tests and local dev without Semrush Business API."""

    provider_code = "semrush_api"
    supports_serp = False
    supports_keyword_ideas = True
    supports_keyword_metrics = True

    def check_credentials(self) -> bool:
        return True

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        items = [
            KeywordIdeaRecord(
                original_keyword=kw,
                keyword_type=KeywordCandidateType.PRIMARY_CANDIDATE,
                source_code=self.provider_code,
                country_code=cc,
                language_code=lc,
                source_intent="Informational",
                metrics=[
                    MetricRecord.available(
                        metric_type=MetricType.SEARCH_VOLUME,
                        source_code=self.provider_code,
                        numeric_value=1200.0,
                        unit="searches/month",
                        country_code=cc,
                        language_code=lc,
                    ),
                    MetricRecord.available(
                        metric_type=MetricType.KEYWORD_DIFFICULTY,
                        source_code=self.provider_code,
                        numeric_value=35.0,
                        unit="score_0_100",
                        country_code=cc,
                        language_code=lc,
                    ),
                ],
                extra_metadata={"mock": True},
            )
            for kw in keywords
        ]
        return ProviderResult(provider_code=self.provider_code, status="OK", items=items)

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return self.get_keyword_metrics(
            [seed_keyword, f"{seed_keyword} guide", f"best {seed_keyword}"][:limit],
            country_code=country_code,
            language_code=language_code,
        )

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return self.get_related_keywords(
            seed_keyword,
            country_code=country_code,
            language_code=language_code,
            limit=limit,
        )
