"""Unit tests for deterministic keyword normalization and near-duplicate similarity."""

from app.services.cleaning_service import (
    compute_near_duplicate_similarity,
    fold_vietnamese_accents,
    is_invalid_keyword,
    normalize_keyword_text,
)


def test_normalize_keyword_text_and_accent_folding() -> None:
    assert normalize_keyword_text("  Phần   Mềm CRM!! ") == "phần mềm crm"
    assert fold_vietnamese_accents("Phần Mềm Quản Lý Đơn Hàng") == "phan mem quan ly don hang"


def test_is_invalid_keyword_checks() -> None:
    assert is_invalid_keyword("") is True
    assert is_invalid_keyword("123456") is True
    assert is_invalid_keyword("---!!!") is True
    assert is_invalid_keyword("a" * 201) is True
    assert is_invalid_keyword("crm 2026") is False


def test_near_duplicate_similarity_detects_accent_and_word_order_variants() -> None:
    assert compute_near_duplicate_similarity("phần mềm crm", "phan mem crm") == 1.0
    assert compute_near_duplicate_similarity("crm cho sme", "sme cho crm") >= 0.95
    assert compute_near_duplicate_similarity("phần mềm crm", "thiết kế website") < 0.5
