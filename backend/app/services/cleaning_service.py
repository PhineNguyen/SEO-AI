"""Deterministic Python keyword normalization, deduplication, and non-destructive cleaning."""

import re
import unicodedata
import uuid
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.research import Keyword
from app.repositories.research_repository import ResearchRepository
from app.schemas.research import CleaningSummary

EDGE_PUNCTUATION_REGEX = re.compile(r"^[\s\-_.,;:!?\"'()\[\]{}|/\\]+|[\s\-_.,;:!?\"'()\[\]{}|/\\]+$")
INVALID_ONLY_SYMBOLS_REGEX = re.compile(r"^[\W\d_]+$")
MAX_VALID_KEYWORD_LENGTH = 200


def normalize_keyword_text(text: str) -> str:
    """Normalize a keyword to NFC Unicode, lowercase, trimmed punctuation, single spaces."""
    nfc = unicodedata.normalize("NFC", text)
    cleaned = EDGE_PUNCTUATION_REGEX.sub("", nfc.strip().lower())
    return " ".join(cleaned.split())


def fold_vietnamese_accents(text: str) -> str:
    """Fold Vietnamese diacritics for accent-insensitive near-duplicate comparison."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return " ".join(stripped.replace("đ", "d").split())


def is_invalid_keyword(normalized: str) -> bool:
    """Return True if a normalized keyword is blank, pure symbols/digits, or over-length."""
    if not normalized or len(normalized) > MAX_VALID_KEYWORD_LENGTH:
        return True
    return bool(INVALID_ONLY_SYMBOLS_REGEX.match(normalized))


def compute_near_duplicate_similarity(a: str, b: str) -> float:
    """Compute similarity between two normalized keywords combining accent folding and token sort."""
    fold_a = fold_vietnamese_accents(a)
    fold_b = fold_vietnamese_accents(b)
    if fold_a == fold_b:
        return 1.0

    tokens_a = sorted(fold_a.split())
    tokens_b = sorted(fold_b.split())
    if tokens_a == tokens_b:
        return 0.98

    seq_ratio = SequenceMatcher(None, fold_a, fold_b).ratio()
    sorted_ratio = SequenceMatcher(None, " ".join(tokens_a), " ".join(tokens_b)).ratio()
    return max(seq_ratio, sorted_ratio)


def _canonical_sort_key(kw: Keyword) -> tuple[int, int, int, str]:
    """Prefer SEED/manual entries, then keywords with more available metrics, then earliest."""
    is_seed = 0 if kw.keyword_type == "SEED" or kw.is_manual_entry else 1
    available_metrics = sum(1 for m in kw.metrics if m.data_status == "AVAILABLE")
    return (is_seed, -available_metrics, len(kw.original_keyword), str(kw.id))


class KeywordCleaningService:
    """Non-destructive keyword cleaning engine.

    Preserves all original rows and metrics: duplicates, near-duplicates, irrelevant,
    and invalid rows are flagged via `cleaning_status` and `duplicate_of_keyword_id`
    instead of being hard-deleted. Never removes keywords solely for low or missing volume.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ResearchRepository(db)

    def clean_research_run(
        self,
        research_run_id: uuid.UUID,
        *,
        irrelevant_terms: list[str] | None = None,
        near_duplicate_threshold: float = 0.88,
    ) -> CleaningSummary:
        """Run normalization, invalid detection, deduplication, and irrelevant flagging."""
        keywords = self.repo.list_all_keywords_for_cleaning(research_run_id)
        neg_terms = [
            fold_vietnamese_accents(term)
            for term in (irrelevant_terms or [])
            if term and term.strip()
        ]

        # Reset cleaning_status temporarily to RAW so partial unique index on ACTIVE
        # never collides while re-evaluating canonical winners.
        for kw in keywords:
            kw.normalized_keyword = normalize_keyword_text(kw.original_keyword)
            kw.cleaning_status = "RAW"
            kw.duplicate_of_keyword_id = None
        self.db.flush()

        # Step 1: Invalid & Irrelevant detection
        candidates_by_norm: dict[str, list[Keyword]] = {}
        invalid_count = 0
        irrelevant_count = 0

        for kw in keywords:
            if is_invalid_keyword(kw.normalized_keyword):
                kw.cleaning_status = "INVALID"
                invalid_count += 1
                continue

            folded = fold_vietnamese_accents(kw.normalized_keyword)
            if neg_terms and any(term in folded for term in neg_terms):
                kw.cleaning_status = "IRRELEVANT"
                irrelevant_count += 1
                continue

            candidates_by_norm.setdefault(kw.normalized_keyword, []).append(kw)

        # Step 2: Exact deduplication (preserve all duplicate rows pointing to canonical winner)
        canonical_active: list[Keyword] = []
        duplicate_count = 0

        for _norm_text, group in candidates_by_norm.items():
            ordered = sorted(group, key=_canonical_sort_key)
            winner = ordered[0]
            winner.cleaning_status = "ACTIVE"
            canonical_active.append(winner)

            for dup in ordered[1:]:
                dup.cleaning_status = "DUPLICATE"
                dup.duplicate_of_keyword_id = winner.id
                duplicate_count += 1

        # Step 3: Near-duplicate detection across exact-unique active keywords
        canonical_active.sort(key=_canonical_sort_key)
        retained_active: list[Keyword] = []
        near_duplicate_count = 0

        for kw in canonical_active:
            matched_parent: Keyword | None = None
            for existing in retained_active:
                similarity = compute_near_duplicate_similarity(
                    kw.normalized_keyword,
                    existing.normalized_keyword,
                )
                if similarity >= near_duplicate_threshold:
                    matched_parent = existing
                    break

            if matched_parent is not None:
                kw.cleaning_status = "NEAR_DUPLICATE"
                kw.duplicate_of_keyword_id = matched_parent.id
                near_duplicate_count += 1
            else:
                retained_active.append(kw)

        self.db.commit()

        return CleaningSummary(
            research_run_id=research_run_id,
            total_processed=len(keywords),
            active_count=len(retained_active),
            duplicate_count=duplicate_count,
            near_duplicate_count=near_duplicate_count,
            irrelevant_count=irrelevant_count,
            invalid_count=invalid_count,
        )
