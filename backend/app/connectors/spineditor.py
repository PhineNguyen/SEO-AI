"""Spineditor CSV/Excel file importer with Vietnamese encoding and column mapping support.

Spineditor does not provide an official public REST API; per project architecture,
integration is implemented cleanly via structured CSV/XLSX import with full provenance.
"""

import csv
import hashlib
import io
import unicodedata
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from app.connectors.semrush import MISSING_VALUE_TOKENS, FileImportReport
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


def _normalize_header(text: str) -> str:
    """Fold Vietnamese diacritics and lowercase a column header for flexible matching."""
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    without_accents = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return " ".join(without_accents.replace("đ", "d").replace("_", " ").split())


def _decode_csv_bytes(content: bytes) -> str:
    """Decode CSV bytes trying UTF-8-SIG, UTF-8, Windows-1258 (Vietnamese), then Latin-1."""
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _detect_csv_delimiter(sample_text: str) -> str:
    """Detect common CSV delimiters (comma, semicolon, tab)."""
    first_lines = "\n".join(sample_text.splitlines()[:5])
    try:
        dialect = csv.Sniffer().sniff(first_lines, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        return ","


def _parse_spineditor_number(raw: Any) -> tuple[float | None, str | None]:
    """Parse numeric metric values (including thousands separators) without turning missing into 0."""
    if raw is None:
        return None, None
    if isinstance(raw, float) and pd.isna(raw):
        return None, None
    text = str(raw).strip()
    if text.lower() in MISSING_VALUE_TOKENS:
        return None, text or None

    cleaned = (
        text.replace("₫", "")
        .replace("VND", "")
        .replace("vnd", "")
        .replace("$", "")
        .replace("%", "")
        .replace(" ", "")
        .strip()
    )
    # Handle Vietnamese/EU thousands dot notation like "1.200" or "12.500"
    # (never treat leading "0." such as "0.027" as thousands separator).
    if "." in cleaned and "," not in cleaned:
        parts = cleaned.split(".")
        if (
            len(parts) > 1
            and parts[0].isdigit()
            and not parts[0].startswith("0")
            and all(len(p) == 3 and p.isdigit() for p in parts[1:])
        ):
            cleaned = "".join(parts)
    else:
        cleaned = cleaned.replace(",", "")

    try:
        return float(cleaned), text
    except ValueError:
        return None, text


class SpineditorFileImporter:
    """Flexible CSV/XLSX importer for Spineditor keyword research exports."""

    source_code = "spineditor_import"

    COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
        "keyword": ("tu khoa", "keyword", "keywords", "cum tu khoa", "phrase"),
        "volume": (
            "luong tim kiem",
            "search volume",
            "volume",
            "tim kiem/thang",
            "luot tim kiem",
            "avg. monthly searches",
        ),
        "cpc": ("cpc", "gia thau", "cpc (vnd)", "cpc (usd)"),
        "competition": ("canh tranh", "competition", "do canh tranh"),
        "allintitle": ("allintitle", "all in title"),
        "kgr": ("kgr", "keyword golden ratio"),
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
                if alias in normalized_map:
                    mapping[canonical] = normalized_map[alias]
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
        """Parse a Spineditor CSV or XLSX export into provenance-annotated KeywordIdeaRecords."""
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        file_hash = hashlib.sha256(content).hexdigest()
        lower_name = file_name.lower()

        if lower_name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(content), dtype=object)
        else:
            decoded = _decode_csv_bytes(content)
            delimiter = _detect_csv_delimiter(decoded)
            df = pd.read_csv(io.StringIO(decoded), sep=delimiter, dtype=object)

        mapping = self._detect_columns(list(df.columns), column_mapping)
        if "keyword" not in mapping:
            err = ProviderErrorRecord(
                provider_code=self.source_code,
                error_code="MISSING_KEYWORD_COLUMN",
                message="Required keyword column ('Từ khóa' / 'Keyword') was not found in Spineditor file",
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

            metrics: list[MetricRecord] = []
            metric_specs = [
                ("volume", MetricType.SEARCH_VOLUME, "searches/month", None),
                ("cpc", MetricType.CPC, "VND", "VND"),
                ("competition", MetricType.COMPETITION, "ratio_0_1", None),
            ]
            for key, metric_type, unit, currency in metric_specs:
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
                val, raw_val = _parse_spineditor_number(row.get(col_name))
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

            extra_metadata: dict[str, Any] = {}
            for extra_key in ("allintitle", "kgr"):
                col_name = mapping.get(extra_key)
                if col_name:
                    val, raw_val = _parse_spineditor_number(row.get(col_name))
                    if val is not None:
                        extra_metadata[extra_key] = val
                    elif raw_val is not None:
                        extra_metadata[f"{extra_key}_raw"] = raw_val

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
                    extra_metadata=extra_metadata,
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
