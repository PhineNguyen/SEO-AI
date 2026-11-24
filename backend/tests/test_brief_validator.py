"""Unit tests for Sprint 7 Content Brief Anti-Hallucination Validator (TASK-026)."""

from app.schemas.brief import BriefSectionInput, ContentBriefDraft
from app.services.brief_validator import validate_brief_draft


def _sample_draft(**overrides) -> ContentBriefDraft:
    base = {
        "search_intent": "Commercial",
        "target_audience": "SME founders",
        "content_objective": "Compare top CRM software",
        "content_angle": "Evidence-based comparison",
        "suggested_seo_title": "Phan Mem CRM Tot Nhat 2026",
        "meta_description": "So sanh chi tiet cac phan mem CRM.",
        "h1": "Phan Mem CRM Tot Nhat Cho Doanh Nghiep",
        "competitor_insights": [{"position": 1, "url": "https://a.com/crm"}],
        "important_topics": ["Pricing", "Features"],
        "content_recommendations": ["Use real pricing comparisons."],
        "keyword_coverage": {"primary_keyword": "phan mem crm tot nhat"},
        "evidence_refs": [{"type": "serp_result", "url": "https://a.com/crm"}],
        "sections": [
            BriefSectionInput(
                heading_level=2,
                heading_text="So sanh tinh nang",
                section_order=1,
                target_keywords=["phan mem crm tot nhat"],
            )
        ],
        "faqs": [],
    }
    base.update(overrides)
    return ContentBriefDraft(**base)


def test_validator_accepts_grounded_brief() -> None:
    res = validate_brief_draft(
        _sample_draft(),
        primary_keyword="phan mem crm tot nhat",
        allowed_cluster_keywords={"phan mem crm tot nhat", "top phan mem crm"},
        allowed_serp_urls={"https://a.com/crm"},
    )
    assert res.is_valid
    assert res.errors == []


def test_validator_catches_hallucinated_url_keyword_and_rigid_formula() -> None:
    bad = _sample_draft(
        evidence_refs=[{"type": "serp_result", "url": "https://fake-hallucinated.example/xyz"}],
        sections=[
            BriefSectionInput(
                heading_level=2,
                heading_text="Fake section",
                section_order=1,
                target_keywords=["invented keyword not in cluster"],
            )
        ],
        content_recommendations=[
            "Write minimum 2500 words with keyword density 2.5%."
        ],
    )
    res = validate_brief_draft(
        bad,
        primary_keyword="phan mem crm tot nhat",
        allowed_cluster_keywords={"phan mem crm tot nhat"},
        allowed_serp_urls={"https://a.com/crm"},
    )
    assert not res.is_valid
    assert any("Hallucinated keyword" in e for e in res.errors)
    assert any("Hallucinated evidence URL" in e for e in res.errors)
    assert any("Disallowed rigid SEO formula" in e for e in res.errors)
