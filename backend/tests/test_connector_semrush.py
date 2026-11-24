"""Unit tests for Semrush API v4 connector, CSV/XLSX importer, and Mock provider."""

import io

import httpx
import openpyxl
import respx
from app.connectors import (
    MockSemrushProvider,
    ResilientHttpClient,
    RetryConfig,
    SemrushApiConnector,
    SemrushFileImporter,
)
from app.schemas.provenance import DataStatus, MetricType


@respx.mock
def test_semrush_api_metrics_partial_fault_isolation_and_missing_values() -> None:
    respx.get(
        "https://api.semrush.com/apis/v4/keywords/v1/metrics",
        params={"keyword": "crm", "country": "vn"},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "keyword": "crm",
                "volume": 5400,
                "keyword_difficulty": 48,
                "cpc": None,
                "competition": 0.72,
                "intent": "Informational",
                "serp_features": ["featured_snippet", "people_also_ask"],
            },
        )
    )
    respx.get(
        "https://api.semrush.com/apis/v4/keywords/v1/metrics",
        params={"keyword": "broken_kw", "country": "vn"},
    ).mock(return_value=httpx.Response(503, text="upstream error"))

    http = ResilientHttpClient(
        "semrush_api",
        base_url="https://api.semrush.com",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    connector = SemrushApiConnector(api_key="test-semrush-key", http_client=http)
    result = connector.get_keyword_metrics(["crm", "broken_kw"], country_code="VN", language_code="vi")

    assert result.status == "PARTIAL"
    assert len(result.items) == 1
    assert len(result.errors) == 1
    assert result.items[0].source_intent == "Informational"
    by_type = {m.metric_type: m for m in result.items[0].metrics}
    assert by_type[MetricType.SEARCH_VOLUME].numeric_value == 5400.0
    assert by_type[MetricType.CPC].data_status == DataStatus.NOT_AVAILABLE
    assert by_type[MetricType.CPC].numeric_value is None


@respx.mock
def test_semrush_api_related_keywords() -> None:
    respx.get("https://api.semrush.com/apis/v4/keywords/v1/ideas/related").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"keyword": "crm cho sme", "volume": 880, "keyword_difficulty": 22},
                    {"keyword": "phan mem crm mien phi", "volume": 1600, "keyword_difficulty": 31},
                ]
            },
        )
    )
    http = ResilientHttpClient(
        "semrush_api",
        base_url="https://api.semrush.com",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    connector = SemrushApiConnector(api_key="test-semrush-key", http_client=http)
    res = connector.get_related_keywords("crm", country_code="VN", language_code="vi", limit=10)
    assert res.status == "OK"
    assert len(res.items) == 2


def test_semrush_csv_importer_preserves_zero_and_marks_missing_not_available() -> None:
    csv_text = (
        "\ufeffKeyword,Volume,Keyword Difficulty,CPC (USD),Competitive Density,Intent,SERP Features\n"
        "phan mem crm,1200,45%,1.50,0.65,Commercial,\"Featured snippet, PAA\"\n"
        "tu khoa volume bang 0,0,n/a,-,,Informational,\n"
        "   ,100,10,0.1,0.1,Informational,\n"
    )
    importer = SemrushFileImporter()
    report = importer.import_bytes(
        csv_text.encode("utf-8"),
        file_name="semrush_export.csv",
        country_code="VN",
        language_code="vi",
    )

    assert report.total_rows == 3
    assert report.imported_rows == 2
    assert report.error_rows == 1
    assert report.result.status == "PARTIAL"
    assert len(report.file_hash_sha256) == 64

    first = report.result.items[0]
    first_metrics = {m.metric_type: m for m in first.metrics}
    assert first_metrics[MetricType.SEARCH_VOLUME].numeric_value == 1200.0
    assert first_metrics[MetricType.KEYWORD_DIFFICULTY].numeric_value == 45.0
    assert first.serp_features == ["Featured snippet", "PAA"]

    second = report.result.items[1]
    second_metrics = {m.metric_type: m for m in second.metrics}
    assert second_metrics[MetricType.SEARCH_VOLUME].data_status == DataStatus.AVAILABLE
    assert second_metrics[MetricType.SEARCH_VOLUME].numeric_value == 0.0
    assert second_metrics[MetricType.KEYWORD_DIFFICULTY].data_status == DataStatus.NOT_AVAILABLE
    assert second_metrics[MetricType.KEYWORD_DIFFICULTY].numeric_value is None
    assert second_metrics[MetricType.CPC].data_status == DataStatus.NOT_AVAILABLE


def test_semrush_xlsx_importer_and_missing_header_error() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Keyword", "Volume", "KD %"])
    ws.append(["seo onpage", 1900, 38])
    buf = io.BytesIO()
    wb.save(buf)

    importer = SemrushFileImporter()
    report = importer.import_bytes(
        buf.getvalue(),
        file_name="semrush.xlsx",
        country_code="VN",
        language_code="vi",
    )
    assert report.imported_rows == 1
    assert report.result.items[0].original_keyword == "seo onpage"

    bad_report = importer.import_bytes(
        b"WrongCol,Volume\nfoo,100\n",
        file_name="bad.csv",
        country_code="VN",
        language_code="vi",
    )
    assert bad_report.result.status == "ERROR"
    assert bad_report.result.errors[0].error_code == "MISSING_KEYWORD_COLUMN"


def test_mock_semrush_provider() -> None:
    mock = MockSemrushProvider()
    assert mock.check_credentials() is True
    res = mock.get_keyword_ideas("seo", country_code="VN", language_code="vi", limit=2)
    assert res.status == "OK"
    assert len(res.items) == 2
