"""Unit tests for DataForSEO SERP/Keyword connector and MockDataForSeoProvider."""

import httpx
import pytest
import respx
from app.connectors import (
    ConnectorNotSupportedError,
    DataForSeoConnector,
    MockDataForSeoProvider,
    ResilientHttpClient,
    RetryConfig,
)
from app.schemas.provenance import DataStatus, MetricType


@respx.mock
def test_dataforseo_serp_parses_organic_and_serp_features() -> None:
    respx.post("https://sandbox.dataforseo.com/v3/serp/google/organic/live/advanced").mock(
        return_value=httpx.Response(
            200,
            json={
                "status_code": 20000,
                "status_message": "Ok.",
                "tasks": [
                    {
                        "status_code": 20000,
                        "cost": 0.002,
                        "result": [
                            {
                                "se_results_count": 125000,
                                "items": [
                                    {"type": "ai_overview"},
                                    {"type": "people_also_ask"},
                                    {
                                        "type": "featured_snippet",
                                        "rank_group": 1,
                                        "url": "https://blog.example.vn/crm-la-gi",
                                        "domain": "blog.example.vn",
                                        "title": "CRM là gì?",
                                        "description": "Định nghĩa CRM chi tiết.",
                                    },
                                    {
                                        "type": "organic",
                                        "rank_group": 2,
                                        "url": "https://www.youtube.com/watch?v=123",
                                        "domain": "www.youtube.com",
                                        "title": "Video hướng dẫn CRM",
                                        "description": "Video giải thích CRM",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
        )
    )

    http = ResilientHttpClient(
        "dataforseo_serp",
        base_url="https://sandbox.dataforseo.com",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    connector = DataForSeoConnector(
        login="user@example.com",
        password="secret",
        use_sandbox=True,
        http_client=http,
    )
    result = connector.get_serp_results(
        "crm la gi",
        country_code="vn",
        language_code="vi",
        device="desktop",
        depth=10,
    )

    assert result.status == "OK"
    assert len(result.items) == 1
    snapshot = result.items[0]
    assert snapshot.country_code == "VN"
    assert snapshot.language_code == "vi"
    assert snapshot.device == "desktop"
    assert snapshot.serp_features == ["ai_overview", "featured_snippet", "people_also_ask"]
    assert len(snapshot.results) == 2
    assert snapshot.results[0].result_type == "FEATURED_SNIPPET"
    assert snapshot.results[1].result_type == "VIDEO"


@respx.mock
def test_dataforseo_balance_exhausted_returns_quota_error() -> None:
    respx.post("https://sandbox.dataforseo.com/v3/serp/google/organic/live/advanced").mock(
        return_value=httpx.Response(
            200,
            json={"status_code": 40200, "status_message": "Payment Required"},
        )
    )
    http = ResilientHttpClient(
        "dataforseo_serp",
        base_url="https://sandbox.dataforseo.com",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    connector = DataForSeoConnector(
        login="user@example.com",
        password="secret",
        use_sandbox=True,
        http_client=http,
    )
    result = connector.get_serp_results("seo", country_code="VN", language_code="vi")
    assert result.status == "ERROR"
    assert result.errors[0].error_code == "CONNECTOR_QUOTA_EXCEEDED"


@respx.mock
def test_dataforseo_optional_keyword_api_toggle_and_missing_values() -> None:
    disabled = DataForSeoConnector(
        login="user@example.com",
        password="secret",
        enable_keyword_api=False,
    )
    with pytest.raises(ConnectorNotSupportedError):
        disabled.get_keyword_metrics(["seo"], country_code="VN", language_code="vi")

    respx.post("https://sandbox.dataforseo.com/v3/keywords_data/google_ads/search_volume/live").mock(
        return_value=httpx.Response(
            200,
            json={
                "status_code": 20000,
                "tasks": [
                    {
                        "status_code": 20000,
                        "result": [
                            {
                                "keyword": "phan mem crm",
                                "search_volume": 2400,
                                "cpc": None,
                                "competition_index": 65,
                            }
                        ],
                    }
                ],
            },
        )
    )
    http = ResilientHttpClient(
        "dataforseo_serp",
        base_url="https://sandbox.dataforseo.com",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    enabled = DataForSeoConnector(
        login="user@example.com",
        password="secret",
        enable_keyword_api=True,
        http_client=http,
    )
    res = enabled.get_keyword_metrics(["phan mem crm"], country_code="VN", language_code="vi")
    assert res.status == "OK"
    assert len(res.items) == 1
    by_type = {m.metric_type: m for m in res.items[0].metrics}
    assert by_type[MetricType.SEARCH_VOLUME].numeric_value == 2400.0
    assert by_type[MetricType.CPC].data_status == DataStatus.NOT_AVAILABLE
    assert by_type[MetricType.CPC].numeric_value is None
    assert pytest.approx(by_type[MetricType.COMPETITION].numeric_value) == 0.65


def test_mock_dataforseo_provider_returns_valid_dtos() -> None:
    mock = MockDataForSeoProvider()
    assert mock.check_credentials() is True

    serp = mock.get_serp_results("seo tools", country_code="US", language_code="en", depth=5)
    assert serp.status == "OK"
    assert len(serp.items[0].results) == 5

    ideas = mock.get_keyword_ideas("crm", country_code="VN", language_code="vi", limit=3)
    assert ideas.status == "OK"
    assert len(ideas.items) == 3
