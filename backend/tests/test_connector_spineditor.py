"""Unit tests for Spineditor CSV/Excel importer with Vietnamese headers and number formats."""

import io

import openpyxl
from app.connectors import SpineditorFileImporter
from app.schemas.provenance import DataStatus, MetricType


def test_spineditor_vietnamese_csv_semicolon_and_number_parsing() -> None:
    csv_text = (
        "\ufeffTừ khóa;Lượng tìm kiếm;Giá thầu;Cạnh tranh;Allintitle;KGR\n"
        "phần mềm quản lý bán hàng;12.500;15.000 VND;0.82;340;0.027\n"
        "từ khóa volume bằng 0;0;-;N/A;0;-\n"
        "   ;500;1000;0.2;10;0.02\n"
    )
    importer = SpineditorFileImporter()
    report = importer.import_bytes(
        csv_text.encode("utf-8"),
        file_name="spineditor_vn.csv",
        country_code="VN",
        language_code="vi",
    )

    assert report.source_code == "spineditor_import"
    assert report.total_rows == 3
    assert report.imported_rows == 2
    assert report.error_rows == 1
    assert report.result.status == "PARTIAL"
    assert len(report.file_hash_sha256) == 64

    first = report.result.items[0]
    assert first.original_keyword == "phần mềm quản lý bán hàng"
    first_metrics = {m.metric_type: m for m in first.metrics}
    assert first_metrics[MetricType.SEARCH_VOLUME].numeric_value == 12500.0
    assert first_metrics[MetricType.CPC].numeric_value == 15000.0
    assert first_metrics[MetricType.COMPETITION].numeric_value == 0.82
    assert first.extra_metadata["allintitle"] == 340.0
    assert first.extra_metadata["kgr"] == 0.027

    second = report.result.items[1]
    second_metrics = {m.metric_type: m for m in second.metrics}
    assert second_metrics[MetricType.SEARCH_VOLUME].data_status == DataStatus.AVAILABLE
    assert second_metrics[MetricType.SEARCH_VOLUME].numeric_value == 0.0
    assert second_metrics[MetricType.CPC].data_status == DataStatus.NOT_AVAILABLE
    assert second_metrics[MetricType.CPC].numeric_value is None
    assert second_metrics[MetricType.COMPETITION].data_status == DataStatus.NOT_AVAILABLE


def test_spineditor_xlsx_import_with_custom_column_mapping() -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Custom_KW", "Custom_Vol"])
    ws.append(["dịch vụ seo tổng thể", "2,400"])
    buf = io.BytesIO()
    wb.save(buf)

    importer = SpineditorFileImporter()
    report = importer.import_bytes(
        buf.getvalue(),
        file_name="spineditor_custom.xlsx",
        country_code="VN",
        language_code="vi",
        column_mapping={"keyword": "Custom_KW", "volume": "Custom_Vol"},
    )
    assert report.result.status == "OK"
    assert report.imported_rows == 1
    item = report.result.items[0]
    assert item.original_keyword == "dịch vụ seo tổng thể"
    by_type = {m.metric_type: m for m in item.metrics}
    assert by_type[MetricType.SEARCH_VOLUME].numeric_value == 2400.0
    assert by_type[MetricType.CPC].data_status == DataStatus.NOT_COLLECTED


def test_spineditor_missing_keyword_column_returns_error() -> None:
    importer = SpineditorFileImporter()
    report = importer.import_bytes(
        b"ColA,ColB\n1,2\n",
        file_name="invalid.csv",
    )
    assert report.result.status == "ERROR"
    assert report.result.errors[0].error_code == "MISSING_KEYWORD_COLUMN"
