"""DataForSEO connector (SERP + optional Keywords Data API) and deterministic Mock provider."""

import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.config import Settings
from app.connectors.base import BaseDataProvider
from app.connectors.exceptions import (
    ConnectorError,
    ConnectorNotSupportedError,
    ConnectorQuotaExceededError,
    ConnectorUpstreamError,
)
from app.connectors.http_client import RateLimiter, ResilientHttpClient, RetryConfig
from app.schemas.provenance import (
    DataStatus,
    DeviceType,
    KeywordCandidateType,
    KeywordIdeaRecord,
    MetricRecord,
    MetricType,
    ProviderResult,
    SerpResultRecord,
    SerpSnapshotRecord,
)
from app.utils.normalization import normalize_country_code, normalize_language_code

# Standard DataForSEO numeric location codes for common SEO markets.
COUNTRY_TO_LOCATION_CODE: dict[str, int] = {
    "VN": 2704,
    "US": 2840,
    "GB": 2826,
    "SG": 2702,
    "AU": 2036,
    "CA": 2124,
    "DE": 2276,
    "FR": 2250,
    "JP": 2392,
    "KR": 2410,
}

DATAFORSEO_SERP_FEATURE_TYPES: set[str] = {
    "featured_snippet",
    "people_also_ask",
    "ai_overview",
    "local_pack",
    "knowledge_graph",
    "video",
    "images",
    "shopping",
    "top_stories",
    "related_searches",
    "paid",
}

FORUM_DOMAINS: tuple[str, ...] = ("reddit.com", "quora.com", "voz.vn", "tinhte.vn")
VIDEO_DOMAINS: tuple[str, ...] = ("youtube.com", "youtu.be", "vimeo.com", "tiktok.com")
ECOMMERCE_DOMAINS: tuple[str, ...] = (
    "shopee.vn",
    "lazada.vn",
    "tiki.vn",
    "amazon.com",
    "ebay.com",
)


def _classify_result_type(item_type: str, domain: str) -> str:
    if item_type == "featured_snippet":
        return "FEATURED_SNIPPET"
    lowered = domain.lower()
    if any(d in lowered for d in VIDEO_DOMAINS):
        return "VIDEO"
    if any(d in lowered for d in FORUM_DOMAINS):
        return "FORUM"
    if any(d in lowered for d in ECOMMERCE_DOMAINS):
        return "ECOMMERCE"
    return "ORGANIC"


def _extract_domain(url: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback.lower().removeprefix("www.")
    hostname = urlparse(url).hostname or ""
    return hostname.lower().removeprefix("www.") or "unknown"


class DataForSeoConnector(BaseDataProvider):
    """DataForSEO v3 connector supporting Google Organic SERP and optional Keywords Data API."""

    provider_code = "dataforseo_serp"
    supports_serp = True
    supports_keyword_ideas = True
    supports_keyword_metrics = True

    def __init__(
        self,
        *,
        login: str | None,
        password: str | None,
        use_sandbox: bool = True,
        enable_keyword_api: bool = False,
        http_client: ResilientHttpClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._login = (login or "").strip()
        self._password = (password or "").strip()
        self.use_sandbox = use_sandbox
        self.enable_keyword_api = enable_keyword_api
        base_url = (
            "https://sandbox.dataforseo.com" if use_sandbox else "https://api.dataforseo.com"
        )
        self._http = http_client or ResilientHttpClient(
            provider_code=self.provider_code,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            retry_config=RetryConfig(max_attempts=3, base_delay_seconds=0.5),
            rate_limiter=RateLimiter(requests_per_second=5.0),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "DataForSeoConnector":
        """Instantiate connector from application Settings."""
        password = (
            settings.DATAFORSEO_PASSWORD.get_secret_value()
            if settings.DATAFORSEO_PASSWORD is not None
            else None
        )
        return cls(
            login=settings.DATAFORSEO_LOGIN,
            password=password,
            use_sandbox=settings.DATAFORSEO_USE_SANDBOX,
            enable_keyword_api=settings.DATAFORSEO_ENABLE_KEYWORD_API,
        )

    def check_credentials(self) -> bool:
        return bool(self._login and self._password)

    def close(self) -> None:
        self._http.close()

    def _auth_tuple(self) -> tuple[str, str]:
        self.require_credentials()
        return (self._login, self._password)

    def _validate_api_envelope(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        status_code = body.get("status_code")
        if status_code in (40200, 40201):
            raise ConnectorQuotaExceededError(
                self.provider_code,
                str(body.get("status_message") or "DataForSEO account balance exhausted"),
                http_status=402,
            )
        if status_code != 20000:
            raise ConnectorUpstreamError(
                self.provider_code,
                f"DataForSEO API error ({status_code}): {body.get('status_message', 'Unknown')}",
            )
        tasks = body.get("tasks") or []
        if not isinstance(tasks, list):
            return []
        for task in tasks:
            task_code = task.get("status_code")
            if task_code in (40200, 40201):
                raise ConnectorQuotaExceededError(
                    self.provider_code,
                    str(task.get("status_message") or "DataForSEO task quota exceeded"),
                    http_status=402,
                )
        return tasks

    def _build_location_payload(
        self,
        *,
        country_code: str,
        language_code: str,
        location_name: str | None = None,
    ) -> dict[str, Any]:
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code).split("-")[0]
        payload: dict[str, Any] = {"language_code": lc}
        if location_name:
            payload["location_name"] = location_name
        elif cc in COUNTRY_TO_LOCATION_CODE:
            payload["location_code"] = COUNTRY_TO_LOCATION_CODE[cc]
        else:
            payload["location_name"] = cc
        return payload

    def get_serp_results(
        self,
        keyword: str,
        *,
        country_code: str,
        language_code: str,
        device: DeviceType = "desktop",
        location_name: str | None = None,
        depth: int = 10,
    ) -> ProviderResult[SerpSnapshotRecord]:
        """Fetch live Google organic Top-N results and SERP features from DataForSEO."""
        start = time.perf_counter()
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)

        task_payload: dict[str, Any] = {
            "keyword": keyword,
            "device": device,
            "depth": max(1, min(depth, 100)),
            **self._build_location_payload(
                country_code=cc,
                language_code=lc,
                location_name=location_name,
            ),
        }

        try:
            response = self._http.post(
                "/v3/serp/google/organic/live/advanced",
                json=[task_payload],
                auth=self._auth_tuple(),
                units=1.0,
            )
            tasks = self._validate_api_envelope(response.json())
        except ConnectorError as exc:
            return ProviderResult(
                provider_code=self.provider_code,
                status="ERROR",
                items=[],
                errors=[exc.to_error_record(context={"keyword": keyword, "country": cc})],
                duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            )

        snapshots: list[SerpSnapshotRecord] = []
        collected_at = datetime.now(UTC)

        for task in tasks:
            if task.get("status_code") != 20000:
                continue
            for result_block in task.get("result") or []:
                raw_items = result_block.get("items") or []
                features: set[str] = set()
                parsed_results: list[SerpResultRecord] = []

                for raw_item in raw_items:
                    item_type = str(raw_item.get("type") or "")
                    if item_type in DATAFORSEO_SERP_FEATURE_TYPES:
                        features.add(item_type)

                    if item_type in ("organic", "featured_snippet"):
                        url = str(raw_item.get("url") or "").strip()
                        if not url:
                            continue
                        rank = int(
                            raw_item.get("rank_group")
                            or raw_item.get("rank_absolute")
                            or (len(parsed_results) + 1)
                        )
                        domain = _extract_domain(url, raw_item.get("domain"))
                        parsed_results.append(
                            SerpResultRecord(
                                position=rank,
                                url=url,
                                domain=domain,
                                title=str(raw_item.get("title") or "").strip() or domain,
                                snippet=raw_item.get("description"),
                                result_type=_classify_result_type(item_type, domain),  # type: ignore[arg-type]
                            )
                        )

                parsed_results.sort(key=lambda r: r.position)
                snapshots.append(
                    SerpSnapshotRecord(
                        query_text=keyword,
                        provider_code=self.provider_code,
                        country_code=cc,
                        language_code=lc,
                        location_name=location_name,
                        device=device,
                        serp_features=sorted(features),
                        results=parsed_results[:depth],
                        data_status=(
                            DataStatus.AVAILABLE
                            if parsed_results
                            else DataStatus.NOT_AVAILABLE
                        ),
                        collected_at=collected_at,
                        raw_metadata={
                            "se_results_count": result_block.get("se_results_count"),
                            "check_url": result_block.get("check_url"),
                            "cost": task.get("cost"),
                        },
                    )
                )

        duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return ProviderResult(
            provider_code=self.provider_code,
            status="OK" if snapshots else "ERROR",
            items=snapshots,
            quota_used=self._http.quota.units_consumed,
            duration_ms=duration_ms,
        )

    def _require_keyword_api(self) -> None:
        if not self.enable_keyword_api:
            raise ConnectorNotSupportedError(
                "dataforseo_kw",
                "DataForSEO Keywords Data API is disabled (set DATAFORSEO_ENABLE_KEYWORD_API=true)",
            )

    def _parse_keyword_item(
        self,
        item: dict[str, Any],
        *,
        country_code: str,
        language_code: str,
        keyword_type: KeywordCandidateType,
        collected_at: datetime,
    ) -> KeywordIdeaRecord | None:
        keyword_text = str(item.get("keyword") or "").strip()
        if not keyword_text:
            return None

        source_code = "dataforseo_kw"
        metrics: list[MetricRecord] = []

        sv = item.get("search_volume")
        if sv is not None:
            metrics.append(
                MetricRecord.available(
                    metric_type=MetricType.SEARCH_VOLUME,
                    source_code=source_code,
                    numeric_value=float(sv),
                    unit="searches/month",
                    country_code=country_code,
                    language_code=language_code,
                    collected_at=collected_at,
                )
            )
        else:
            metrics.append(
                MetricRecord.missing(
                    metric_type=MetricType.SEARCH_VOLUME,
                    source_code=source_code,
                    unit="searches/month",
                    country_code=country_code,
                    language_code=language_code,
                    collected_at=collected_at,
                )
            )

        cpc = item.get("cpc")
        if cpc is not None:
            metrics.append(
                MetricRecord.available(
                    metric_type=MetricType.CPC,
                    source_code=source_code,
                    numeric_value=float(cpc),
                    unit="USD",
                    currency="USD",
                    country_code=country_code,
                    language_code=language_code,
                    collected_at=collected_at,
                )
            )
        else:
            metrics.append(
                MetricRecord.missing(
                    metric_type=MetricType.CPC,
                    source_code=source_code,
                    unit="USD",
                    currency="USD",
                    country_code=country_code,
                    language_code=language_code,
                    collected_at=collected_at,
                )
            )

        comp = item.get("competition_index")
        if comp is not None:
            metrics.append(
                MetricRecord.available(
                    metric_type=MetricType.COMPETITION,
                    source_code=source_code,
                    numeric_value=float(comp) / 100.0,
                    raw_value=str(comp),
                    unit="ratio_0_1",
                    country_code=country_code,
                    language_code=language_code,
                    collected_at=collected_at,
                )
            )
        else:
            metrics.append(
                MetricRecord.missing(
                    metric_type=MetricType.COMPETITION,
                    source_code=source_code,
                    unit="ratio_0_1",
                    country_code=country_code,
                    language_code=language_code,
                    collected_at=collected_at,
                )
            )

        return KeywordIdeaRecord(
            original_keyword=keyword_text,
            keyword_type=keyword_type,
            source_code=source_code,
            country_code=country_code,
            language_code=language_code,
            collected_at=collected_at,
            metrics=metrics,
        )

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Collect Google Ads search volume, CPC, and competition via DataForSEO Keywords API."""
        self._require_keyword_api()
        start = time.perf_counter()
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)

        if not keywords:
            return ProviderResult(provider_code="dataforseo_kw", status="OK", items=[])

        payload = {
            "keywords": keywords,
            **self._build_location_payload(country_code=cc, language_code=lc),
        }

        try:
            response = self._http.post(
                "/v3/keywords_data/google_ads/search_volume/live",
                json=[payload],
                auth=self._auth_tuple(),
                units=1.0,
            )
            tasks = self._validate_api_envelope(response.json())
        except ConnectorError as exc:
            return ProviderResult(
                provider_code="dataforseo_kw",
                status="ERROR",
                items=[],
                errors=[exc.to_error_record(context={"keyword_count": len(keywords)})],
                duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            )

        collected_at = datetime.now(UTC)
        records: list[KeywordIdeaRecord] = []
        for task in tasks:
            if task.get("status_code") != 20000:
                continue
            for item in task.get("result") or []:
                parsed = self._parse_keyword_item(
                    item,
                    country_code=cc,
                    language_code=lc,
                    keyword_type=KeywordCandidateType.PRIMARY_CANDIDATE,
                    collected_at=collected_at,
                )
                if parsed is not None:
                    records.append(parsed)

        return ProviderResult(
            provider_code="dataforseo_kw",
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
        """Discover keyword ideas via DataForSEO Google Ads keywords_for_keywords endpoint."""
        self._require_keyword_api()
        start = time.perf_counter()
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)

        payload = {
            "keywords": [seed_keyword],
            **self._build_location_payload(country_code=cc, language_code=lc),
        }

        try:
            response = self._http.post(
                "/v3/keywords_data/google_ads/keywords_for_keywords/live",
                json=[payload],
                auth=self._auth_tuple(),
                units=1.0,
            )
            tasks = self._validate_api_envelope(response.json())
        except ConnectorError as exc:
            return ProviderResult(
                provider_code="dataforseo_kw",
                status="ERROR",
                items=[],
                errors=[exc.to_error_record(context={"seed_keyword": seed_keyword})],
                duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            )

        collected_at = datetime.now(UTC)
        records: list[KeywordIdeaRecord] = []
        for task in tasks:
            if task.get("status_code") != 20000:
                continue
            for item in (task.get("result") or [])[:limit]:
                parsed = self._parse_keyword_item(
                    item,
                    country_code=cc,
                    language_code=lc,
                    keyword_type=KeywordCandidateType.RELATED,
                    collected_at=collected_at,
                )
                if parsed is not None:
                    records.append(parsed)

        return ProviderResult(
            provider_code="dataforseo_kw",
            status="OK",
            items=records,
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
        return self.get_keyword_ideas(
            seed_keyword,
            country_code=country_code,
            language_code=language_code,
            limit=limit,
        )


class MockDataForSeoProvider(BaseDataProvider):
    """Explicit deterministic Mock provider for tests and local dev without DataForSEO credentials."""

    provider_code = "dataforseo_serp"
    supports_serp = True
    supports_keyword_ideas = True
    supports_keyword_metrics = True

    def check_credentials(self) -> bool:
        return True

    def get_serp_results(
        self,
        keyword: str,
        *,
        country_code: str,
        language_code: str,
        device: DeviceType = "desktop",
        location_name: str | None = None,
        depth: int = 10,
    ) -> ProviderResult[SerpSnapshotRecord]:
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        slug = "-".join(keyword.lower().split())
        results = [
            SerpResultRecord(
                position=pos,
                url=f"https://competitor{pos}.example.com/{slug}",
                domain=f"competitor{pos}.example.com",
                title=f"{keyword.title()} Guide #{pos}",
                snippet=f"Mock SERP snippet for {keyword} at position {pos}.",
                result_type="ORGANIC",
            )
            for pos in range(1, min(depth, 10) + 1)
        ]
        snapshot = SerpSnapshotRecord(
            query_text=keyword,
            provider_code=self.provider_code,
            country_code=cc,
            language_code=lc,
            location_name=location_name,
            device=device,
            serp_features=["people_also_ask", "related_searches"],
            results=results,
            data_status=DataStatus.AVAILABLE,
            raw_metadata={"mock": True},
        )
        return ProviderResult(provider_code=self.provider_code, status="OK", items=[snapshot])

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        suffixes = ["la gi", "tot nhat", "gia bao nhieu", "cho doanh nghiep"]
        items: list[KeywordIdeaRecord] = []
        for idx, suffix in enumerate(suffixes[:limit], start=1):
            kw = f"{seed_keyword} {suffix}".strip()
            items.append(
                KeywordIdeaRecord(
                    original_keyword=kw,
                    keyword_type=KeywordCandidateType.RELATED,
                    source_code="dataforseo_kw",
                    country_code=cc,
                    language_code=lc,
                    metrics=[
                        MetricRecord.available(
                            metric_type=MetricType.SEARCH_VOLUME,
                            source_code="dataforseo_kw",
                            numeric_value=float(idx * 300),
                            unit="searches/month",
                            country_code=cc,
                            language_code=lc,
                        )
                    ],
                    extra_metadata={"mock": True},
                )
            )
        return ProviderResult(provider_code="dataforseo_kw", status="OK", items=items)

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
                source_code="dataforseo_kw",
                country_code=cc,
                language_code=lc,
                metrics=[
                    MetricRecord.available(
                        metric_type=MetricType.SEARCH_VOLUME,
                        source_code="dataforseo_kw",
                        numeric_value=500.0,
                        unit="searches/month",
                        country_code=cc,
                        language_code=lc,
                    ),
                    MetricRecord.missing(
                        metric_type=MetricType.KEYWORD_DIFFICULTY,
                        source_code="dataforseo_kw",
                        unit="score_0_100",
                        country_code=cc,
                        language_code=lc,
                        data_status=DataStatus.NOT_APPLICABLE,
                    ),
                ],
                extra_metadata={"mock": True},
            )
            for kw in keywords
        ]
        return ProviderResult(provider_code="dataforseo_kw", status="OK", items=items)

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return self.get_keyword_ideas(
            seed_keyword,
            country_code=country_code,
            language_code=language_code,
            limit=limit,
        )
