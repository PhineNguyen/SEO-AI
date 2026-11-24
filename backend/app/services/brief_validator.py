"""Anti-Hallucination & Keyword Coverage Validator for Content Briefs (TASK-026)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.brief import ContentBriefDraft

# Disallowed fabricated rigid SEO rules (word-count quotas or keyword-density percentages)
FORBIDDEN_FORMULA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(minimum|at least|tối thiểu)\s+\d{3,5}\s*(words|từ)\b", re.IGNORECASE),
    re.compile(r"\bkeyword\s+density\s*[:=]?\s*\d+(\.\d+)?%", re.IGNORECASE),
    re.compile(r"\bmật độ từ khóa\s*[:=]?\s*\d+(\.\d+)?%", re.IGNORECASE),
)


@dataclass
class BriefValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


def validate_brief_draft(
    draft: ContentBriefDraft,
    *,
    primary_keyword: str,
    allowed_cluster_keywords: set[str],
    allowed_serp_urls: set[str],
) -> BriefValidationResult:
    """Validate that a ContentBriefDraft contains no hallucinated keywords, URLs, or rigid formulas."""
    errors: list[str] = []
    allowed_kw_lower = {k.strip().lower() for k in allowed_cluster_keywords if k.strip()}
    allowed_urls_norm = {u.strip().rstrip("/") for u in allowed_serp_urls if u.strip()}

    # 1. Primary keyword presence in SEO Title & H1
    pk_lower = primary_keyword.strip().lower()
    if pk_lower and pk_lower not in draft.suggested_seo_title.lower():
        errors.append(f"Primary keyword '{primary_keyword}' missing from suggested_seo_title")
    if pk_lower and pk_lower not in draft.h1.lower():
        errors.append(f"Primary keyword '{primary_keyword}' missing from h1")

    # 2. All section target_keywords must belong to the cluster
    for idx, section in enumerate(draft.sections, start=1):
        for kw in section.target_keywords:
            if kw.strip().lower() not in allowed_kw_lower:
                errors.append(
                    f"Hallucinated keyword '{kw}' in section {idx} not present in cluster"
                )

    # 3. All referenced URLs in evidence_refs & competitor_insights must exist in SERP results
    for ref in draft.evidence_refs:
        url = str(ref.get("url", "")).strip().rstrip("/")
        if url and url not in allowed_urls_norm:
            errors.append(f"Hallucinated evidence URL '{url}' not found in SERP snapshots")

    for insight in draft.competitor_insights:
        url = str(insight.get("url", "")).strip().rstrip("/")
        if url and url not in allowed_urls_norm:
            errors.append(f"Hallucinated competitor URL '{url}' not found in SERP snapshots")

    # 4. Reject invented rigid word-count or keyword-density formulas
    all_guidance_texts = [
        *draft.content_recommendations,
        draft.content_angle,
        draft.content_objective,
    ]
    for text in all_guidance_texts:
        for pat in FORBIDDEN_FORMULA_PATTERNS:
            if pat.search(text):
                errors.append(
                    f"Disallowed rigid SEO formula detected ('{pat.pattern}') in content guidance"
                )

    return BriefValidationResult(is_valid=len(errors) == 0, errors=errors)
