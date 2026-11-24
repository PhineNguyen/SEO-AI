"""Google Keyword Planner (GKP) CSV/Excel file importer.

Supports free keyword research exports downloaded directly from Google Ads Keyword Planner
(including UTF-16LE / UTF-8-SIG TSV/CSV files with GKP's 2-line metadata preamble).
"""

import csv
import hashlib
import io
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from app.connectors.semrush import MISSING_VALUE_TOKENS, FileImportReport
from app.connectors.spineditor import _normalize_header, _parse_spineditor_number
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


def _decode_gkp_bytes(content: bytes) -> str:
    """Decode GKP CSV/TSV exports (Google Ads often exports UTF-16LE or UTF-8-SIG)."""
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _strip_gkp_preamble(text: str) -> str:
    """Skip Google Keyword Planner's optional 2-line title/date-range preamble before headers."""
    lines = text.splitlines()
    for idx, line in enumerate(lines[:6]):
        if not any(sep in line for sep in ("\t", ",", ";")):
            continue
        cells = [_normalize_header(cell.strip('"')) for cell in line.replace(";", ",").replace("\t", ",").split(",")]
        if any(cell in ("keyword", "tu khoa", "keywords") for cell in cells):
            return "\n".join(lines[idx:])
    return text


def _detect_delimiter(text: str) -> str:
    first_lines = "\n".join(text.splitlines()[:5])
    if "\t" in first_lines.splitlines()[0]:
        return "\t"
    try:
        return csv.Sniffer().sniff(first_lines, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


class GoogleKeywordPlannerImporter:
    """Importer for free Google Ads Keyword Planner CSV/TSV/XLSX exports."""

    source_code = "gkp_csv"

    COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
        "keyword": ("keyword", "tu khoa", "keywords"),
        "volume": (
            "avg. monthly searches",
            "avg monthly searches",
            "so lan tim kiem trung binh hang thang",
            "search volume",
            "volume",
        ),
        "competition_index": (
            "competition (indexed value)",
            "competition indexed value",
            "canh tranh (gia tri duoc lap chi muc)",
        ),
        "bid_low": (
            "top of page bid (low range)",
            "gia thau dau trang (pham vi thap)",
        ),
        "bid_high": (
            "top of page bid (high range)",
            "gia thau dau trang (pham vi cao)",
        ),
        "currency": ("currency", "tien te"),
    }

    def _detect_columns(
        self,
        headers: list[str],
        override_mapping: dict[str, str] | None = None,
    ) -> dict[str, str]:
        normalized_map = {_normalize_header(str(h)): str(h) for h in headers}
        mapping: dict[str, str] = {}
        for canonical, aliases in self.COLUMN_ALIASES.items():
            if override_mapping and canonical in override_mapping:
                mapping[canonical] = override_mapping[canonical]
                continue
            for alias in aliases:
                if _normalize_header(alias) in normalized_map:
                    mapping[canonical] = normalized_map[_normalize_header(alias)]
                    break
        return mapping

    def import_bytes(
        self,
        content: bytes,
        *,
        file_name: str,
        country_code: str = "VN",
        language_code: str = "vi",
        column_mapping: dict[str, str] | None = None,
    ) -> FileImportReport:
        """Parse a Google Keyword Planner export into provenance-annotated KeywordIdeaRecords."""
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        file_hash = hashlib.sha256(content).hexdigest()
        lower_name = file_name.lower()

        if lower_name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(content), dtype=object)
        else:
            decoded = _strip_gkp_preamble(_decode_gkp_bytes(content))
            delimiter = _detect_delimiter(decoded)
            df = pd.read_csv(io.StringIO(decoded), sep=delimiter, dtype=object)

        mapping = self._detect_columns(list(df.columns), column_mapping)
        if "keyword" not in mapping:
            err = ProviderErrorRecord(
                provider_code=self.source_code,
                error_code="MISSING_KEYWORD_COLUMN",
                message="Required 'Keyword' column was not found in Google Keyword Planner export",
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
            row_number = int(idx) + 2
            raw_kw = row.get(mapping["keyword"])
            kw_str = (
                ""
                if raw_kw is None or (isinstance(raw_kw, float) and pd.isna(raw_kw))
                else str(raw_kw)
            )
            if not kw_str.strip():
                error_details.append({"row": row_number, "error": "Empty keyword"})
                continue

            currency = "VND" if cc == "VN" else "USD"
            if "currency" in mapping:
                raw_cur = row.get(mapping["currency"])
                if raw_cur is not None and not (isinstance(raw_cur, float) and pd.isna(raw_cur)):
                    cur_clean = str(raw_cur).strip().upper()
                    if cur_clean and cur_clean.lower() not in MISSING_VALUE_TOKENS:
                        currency = cur_clean[:10]

            metrics: list[MetricRecord] = []

            # Search Volume
            if "volume" in mapping:
                val, raw_val = _parse_spineditor_number(row.get(mapping["volume"]))
                if val is not None:
                    metrics.append(
                        MetricRecord.available(
                            metric_type=MetricType.SEARCH_VOLUME,
                            source_code=self.source_code,
                            numeric_value=val,
                            raw_value=raw_val,
                            unit="searches/month",
                            country_code=cc,
                            language_code=lc,
                            source_record_id=f"{file_name}:row:{row_number}",
                            collected_at=collected_at,
                        )
                    )
                else:
                    metrics.append(
                        MetricRecord.missing(
                            metric_type=MetricType.SEARCH_VOLUME,
                            source_code=self.source_code,
                            unit="searches/month",
                            raw_value=raw_val,
                            country_code=cc,
                            language_code=lc,
                            data_status=DataStatus.NOT_AVAILABLE,
                            source_record_id=f"{file_name}:row:{row_number}",
                            collected_at=collected_at,
                        )
                    )

            # Competition (0-100 indexed -> normalized 0-1 ratio)
            if "competition_index" in mapping:
                comp_val, comp_raw = _parse_spineditor_number(row.get(mapping["competition_index"]))
                if comp_val is not None:
                    ratio = comp_val / 100.0 if comp_val > 1.0 else comp_val
                    metrics.append(
                        MetricRecord.available(
                            metric_type=MetricType.COMPETITION,
                            source_code=self.source_code,
                            numeric_value=round(ratio, 4),
                            raw_value=comp_raw,
                            unit="ratio_0_1",
                            country_code=cc,
                            language_code=lc,
                            source_record_id=f"{file_name}:row:{row_number}",
                            collected_at=collected_at,
                        )
                    )
                else:
                    metrics.append(
                        MetricRecord.missing(
                            metric_type=MetricType.COMPETITION,
                            source_code=self.source_code,
                            unit="ratio_0_1",
                            raw_value=comp_raw,
                            country_code=cc,
                            language_code=lc,
                            data_status=DataStatus.NOT_AVAILABLE,
                            source_record_id=f"{file_name}:row:{row_number}",
                            collected_at=collected_at,
                        )
                    )

            # CPC estimated from midpoint of low/high top-of-page bid when available
            bid_low, _ = (
                _parse_spineditor_number(row.get(mapping["bid_low"]))
                if "bid_low" in mapping
                else (None, None)
            )
            bid_high, _ = (
                _parse_spineditor_number(row.get(mapping["bid_high"]))
                if "bid_high" in mapping
                else (None, None)
            )
            if bid_low is not None and bid_high is not None:
                cpc_val = round((bid_low + bid_high) / 2.0, 4)
                metrics.append(
                    MetricRecord.available(
                        metric_type=MetricType.CPC,
                        source_code=self.source_code,
                        numeric_value=cpc_val,
                        raw_value=f"{bid_low}-{bid_high}",
                        unit=currency,
                        currency=currency,
                        country_code=cc,
                        language_code=lc,
                        source_record_id=f"{file_name}:row:{row_number}",
                        collected_at=collected_at,
                    )
                )
            elif bid_low is not None or bid_high is not None:
                single = bid_low if bid_low is not None else bid_high
                assert single is not None
                metrics.append(
                    MetricRecord.available(
                        metric_type=MetricType.CPC,
                        source_code=self.source_code,
                        numeric_value=single,
                        raw_value=str(single),
                        unit=currency,
                        currency=currency,
                        country_code=cc,
                        language_code=lc,
                        source_record_id=f"{file_name}:row:{row_number}",
                        collected_at=collected_at,
                    )
                )
            elif "bid_low" in mapping or "bid_high" in mapping:
                metrics.append(
                    MetricRecord.missing(
                        metric_type=MetricType.CPC,
                        source_code=self.source_code,
                        unit=currency,
                        currency=currency,
                        country_code=cc,
                        language_code=lc,
                        data_status=DataStatus.NOT_AVAILABLE,
                        source_record_id=f"{file_name}:row:{row_number}",
                        collected_at=collected_at,
                    )
                )

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
