"""Unit tests for Google Keyword Planner CSV/TSV/XLSX importer."""

from app.connectors import GoogleKeywordPlannerImporter
from app.schemas.provenance import DataStatus, MetricType


def test_gkp_utf16_tsv_with_preamble_parses_volume_competition_and_cpc() -> None:
    tsv_text = (
        "Keyword Stats 2026-11-24 at 09_00_00\n"
        "November 1, 2025 - October 31, 2026\n"
        "Keyword\tCurrency\tAvg. monthly searches\tCompetition (indexed value)\t"
        "Top of page bid (low range)\tTop of page bid (high range)\n"
        "phần mềm crm\tVND\t5400\t65\t10000\t20000\n"
        "từ khóa ít tìm kiếm\tVND\t0\t-\t-\t-\n"
    )
    importer = GoogleKeywordPlannerImporter()
    report = importer.import_bytes(
        tsv_text.encode("utf-16"),
        file_name="Keyword Stats 2026.csv",
        country_code="VN",
        language_code="vi",
    )

    assert report.source_code == "gkp_csv"
    assert report.result.status == "OK"
    assert report.imported_rows == 2

    first = report.result.items[0]
    first_metrics = {m.metric_type: m for m in first.metrics}
    assert first.original_keyword == "phần mềm crm"
    assert first_metrics[MetricType.SEARCH_VOLUME].numeric_value == 5400.0
    assert first_metrics[MetricType.COMPETITION].numeric_value == 0.65
    assert first_metrics[MetricType.CPC].numeric_value == 15000.0
    assert first_metrics[MetricType.CPC].currency == "VND"

    second = report.result.items[1]
    second_metrics = {m.metric_type: m for m in second.metrics}
    assert second_metrics[MetricType.SEARCH_VOLUME].data_status == DataStatus.AVAILABLE
    assert second_metrics[MetricType.SEARCH_VOLUME].numeric_value == 0.0
    assert second_metrics[MetricType.COMPETITION].data_status == DataStatus.NOT_AVAILABLE
    assert second_metrics[MetricType.CPC].data_status == DataStatus.NOT_AVAILABLE
