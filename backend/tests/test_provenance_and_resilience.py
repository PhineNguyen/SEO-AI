"""Unit tests for Data Provenance DTOs, HTTP resilience, rate limiting, and BaseDataProvider."""

import httpx
import pytest
import respx
from app.connectors import (
    BaseDataProvider,
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorNotSupportedError,
    ConnectorRateLimitError,
    ConnectorTimeoutError,
    RateLimiter,
    ResilientHttpClient,
    RetryConfig,
)
from app.schemas.provenance import (
    DataStatus,
    KeywordCandidateType,
    KeywordIdeaRecord,
    MetricRecord,
    MetricType,
    ProviderResult,
    SerpResultRecord,
    SerpSnapshotRecord,
)
from pydantic import ValidationError


def test_metric_record_allows_legitimate_zero_and_blocks_missing_zero() -> None:
    zero_volume = MetricRecord.available(
        metric_type=MetricType.SEARCH_VOLUME,
        source_code="semrush_api",
        numeric_value=0.0,
        unit="searches/month",
        country_code="vn",
        language_code="VI",
    )
    assert zero_volume.data_status == DataStatus.AVAILABLE
    assert zero_volume.numeric_value == 0.0
    assert zero_volume.country_code == "VN"
    assert zero_volume.language_code == "vi"

    missing_volume = MetricRecord.missing(
        metric_type=MetricType.SEARCH_VOLUME,
        source_code="semrush_api",
        unit="searches/month",
        country_code="VN",
        language_code="vi",
        data_status=DataStatus.NOT_AVAILABLE,
    )
    assert missing_volume.numeric_value is None

    # Disguising NOT_AVAILABLE as 0 must be rejected
    with pytest.raises(ValidationError):
        MetricRecord(
            metric_type=MetricType.SEARCH_VOLUME,
            source_code="semrush_api",
            numeric_value=0.0,
            unit="searches/month",
            country_code="VN",
            language_code="vi",
            data_status=DataStatus.NOT_AVAILABLE,
        )

    # AVAILABLE without numeric_value must be rejected
    with pytest.raises(ValidationError):
        MetricRecord(
            metric_type=MetricType.SEARCH_VOLUME,
            source_code="semrush_api",
            numeric_value=None,
            unit="searches/month",
            country_code="VN",
            language_code="vi",
            data_status=DataStatus.AVAILABLE,
        )


def test_keyword_idea_and_serp_snapshot_normalize_locale_and_preserve_raw_keyword() -> None:
    idea = KeywordIdeaRecord(
        original_keyword="  Phần Mềm CRM cho SME  ",
        keyword_type=KeywordCandidateType.LONG_TAIL,
        source_code="spineditor_import",
        country_code="vn",
        language_code="VI",
    )
    assert idea.original_keyword == "  Phần Mềm CRM cho SME  "
    assert idea.country_code == "VN"
    assert idea.language_code == "vi"

    snapshot = SerpSnapshotRecord(
        query_text="phan mem crm",
        provider_code="dataforseo_serp",
        country_code="vn",
        language_code="vi",
        device="desktop",
        serp_features=["people_also_ask", "featured_snippet"],
        results=[
            SerpResultRecord(
                position=1,
                url="https://example.vn/crm",
                domain="example.vn",
                title="Top CRM",
                snippet="Summary",
            )
        ],
    )
    assert snapshot.country_code == "VN"
    assert len(snapshot.results) == 1


@respx.mock
def test_resilient_http_client_success_and_quota_tracking() -> None:
    respx.get("https://api.example.test/v1/metrics").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    with ResilientHttpClient(
        "test_provider",
        base_url="https://api.example.test",
        sleep_fn=lambda _s: None,
    ) as client:
        resp = client.get("/v1/metrics", units=20.0)
        assert resp.status_code == 200
        assert client.quota.requests_made == 1
        assert client.quota.units_consumed == 20.0


@respx.mock
def test_resilient_http_client_retries_503_with_exponential_backoff() -> None:
    route = respx.get("https://api.example.test/v1/ideas").mock(
        side_effect=[
            httpx.Response(503, text="unavailable"),
            httpx.Response(503, text="unavailable"),
            httpx.Response(200, json={"items": ["seo"]}),
        ]
    )
    sleeps: list[float] = []
    with ResilientHttpClient(
        "test_provider",
        base_url="https://api.example.test",
        retry_config=RetryConfig(max_attempts=3, base_delay_seconds=0.5, jitter=False),
        sleep_fn=sleeps.append,
    ) as client:
        resp = client.get("/v1/ideas")
        assert resp.status_code == 200
        assert route.call_count == 3
        assert sleeps == [0.5, 1.0]


@respx.mock
def test_resilient_http_client_handles_429_retry_after_and_exhaustion() -> None:
    respx.get("https://api.example.test/v1/rate-ok").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    sleeps: list[float] = []
    with ResilientHttpClient(
        "test_provider",
        base_url="https://api.example.test",
        retry_config=RetryConfig(max_attempts=2, base_delay_seconds=0.5, max_delay_seconds=5.0),
        sleep_fn=sleeps.append,
    ) as client:
        resp = client.get("/v1/rate-ok")
        assert resp.status_code == 200
        assert sleeps == [2.0]

    respx.get("https://api.example.test/v1/rate-fail").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "3"})
    )
    with ResilientHttpClient(
        "test_provider",
        base_url="https://api.example.test",
        retry_config=RetryConfig(max_attempts=2),
        sleep_fn=lambda _s: None,
    ) as client:
        with pytest.raises(ConnectorRateLimitError) as exc_info:
            client.get("/v1/rate-fail")
        assert exc_info.value.retry_after_seconds == 3.0


@respx.mock
def test_resilient_http_client_never_retries_auth_errors() -> None:
    route = respx.get("https://api.example.test/v1/secret").mock(
        return_value=httpx.Response(401, text="invalid key")
    )
    with ResilientHttpClient(
        "test_provider",
        base_url="https://api.example.test",
        retry_config=RetryConfig(max_attempts=3),
        sleep_fn=lambda _s: None,
    ) as client:
        with pytest.raises(ConnectorAuthError) as exc_info:
            client.get("/v1/secret")
        assert exc_info.value.http_status == 401
        assert route.call_count == 1


@respx.mock
def test_resilient_http_client_retries_timeouts_then_raises() -> None:
    route = respx.get("https://api.example.test/v1/slow").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )
    with ResilientHttpClient(
        "test_provider",
        base_url="https://api.example.test",
        retry_config=RetryConfig(max_attempts=2, base_delay_seconds=0.1),
        sleep_fn=lambda _s: None,
    ) as client:
        with pytest.raises(ConnectorTimeoutError):
            client.get("/v1/slow")
        assert route.call_count == 2


def test_rate_limiter_enforces_minimum_interval() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def fake_clock() -> float:
        return now[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(requests_per_second=2.0, clock=fake_clock, sleep_fn=fake_sleep)
    assert limiter.acquire() == 0.0
    now[0] += 0.1
    waited = limiter.acquire()
    assert pytest.approx(waited, abs=1e-6) == 0.4
    assert len(sleeps) == 1


class _DummyProvider(BaseDataProvider):
    provider_code = "dummy"

    def __init__(self, configured: bool) -> None:
        self._configured = configured

    def check_credentials(self) -> bool:
        return self._configured

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return ProviderResult(provider_code=self.provider_code, status="OK", items=[])

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return ProviderResult(provider_code=self.provider_code, status="OK", items=[])

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return ProviderResult(provider_code=self.provider_code, status="OK", items=[])


def test_base_data_provider_contract_and_error_records() -> None:
    unconfigured = _DummyProvider(configured=False)
    with pytest.raises(ConnectorConfigError) as cfg_exc:
        unconfigured.require_credentials()
    err_record = cfg_exc.value.to_error_record(context={"stage": "discovery"})
    assert err_record.provider_code == "dummy"
    assert err_record.error_code == "CONNECTOR_CONFIG_ERROR"
    assert err_record.retryable is False
    assert err_record.context == {"stage": "discovery"}

    configured = _DummyProvider(configured=True)
    configured.require_credentials()
    with pytest.raises(ConnectorNotSupportedError):
        configured.get_serp_results("seo", country_code="VN", language_code="vi")
