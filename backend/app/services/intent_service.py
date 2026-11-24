"""Evidence-based Search Intent classification service with anti-hallucination validation."""

from abc import ABC, abstractmethod
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from app.agents.prompts.intent_prompt import (
    INTENT_PROMPT_VERSION,
    INTENT_SYSTEM_PROMPT,
    build_intent_user_message,
)
from app.models.research import Keyword
from app.models.serp import KeywordIntent, SerpSnapshot
from app.repositories.serp_repository import SerpRepository
from app.schemas.intent import IntentClassificationOutput, SearchIntentType
from app.schemas.provenance import SerpResultRecord


class IntentValidationError(Exception):
    """Raised when an AI intent classification fails anti-hallucination validation."""


def validate_intent_evidence(
    output: IntentClassificationOutput,
    valid_serp_urls: set[str],
) -> None:
    """Verify every cited evidence URL exists in collected SERP results."""
    if valid_serp_urls and not output.evidence_urls:
        raise IntentValidationError("Intent output must cite at least one SERP evidence URL")

    hallucinated = [url for url in output.evidence_urls if url not in valid_serp_urls]
    if hallucinated:
        raise IntentValidationError(
            f"Intent output cited URLs not present in SERP snapshot: {hallucinated}"
        )


class BaseIntentClassifier(ABC):
    """Interface for Search Intent classifiers (OpenAI Structured Outputs or heuristic baseline)."""

    model_version: str = "unknown"
    prompt_version: str = INTENT_PROMPT_VERSION

    @abstractmethod
    def classify(
        self,
        *,
        keyword: str,
        country_code: str,
        language_code: str,
        serp_features: list[str],
        serp_results: list[SerpResultRecord],
        competitor_headings_by_url: dict[str, list[str]] | None = None,
    ) -> IntentClassificationOutput:
        """Classify keyword search intent using SERP evidence."""


class OpenAIIntentClassifier(BaseIntentClassifier):
    """OpenAI Structured Outputs intent classifier with bounded retry on evidence validation."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_validation_retries: int = 2,
        client: OpenAI | None = None,
    ) -> None:
        self.model_version = model
        self.prompt_version = INTENT_PROMPT_VERSION
        self.max_validation_retries = max(1, max_validation_retries)
        self._client = client or OpenAI(api_key=api_key)

    def classify(
        self,
        *,
        keyword: str,
        country_code: str,
        language_code: str,
        serp_features: list[str],
        serp_results: list[SerpResultRecord],
        competitor_headings_by_url: dict[str, list[str]] | None = None,
    ) -> IntentClassificationOutput:
        user_msg = build_intent_user_message(
            keyword=keyword,
            country_code=country_code,
            language_code=language_code,
            serp_features=serp_features,
            serp_results=serp_results,
            competitor_headings_by_url=competitor_headings_by_url,
        )
        valid_urls = {r.url for r in serp_results}
        last_error: Exception | None = None

        for attempt in range(self.max_validation_retries):
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ]
            if last_error is not None and attempt > 0:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Previous output failed validation ({last_error}). "
                        "Cite ONLY exact URLs from <untrusted_serp_data>.",
                    }
                )

            completion = self._client.beta.chat.completions.parse(
                model=self.model_version,
                messages=messages,
                response_format=IntentClassificationOutput,
                temperature=0.0,
            )
            parsed = completion.choices[0].message.parsed
            if parsed is None:
                last_error = IntentValidationError("Model returned empty structured output")
                continue

            try:
                validate_intent_evidence(parsed, valid_urls)
                return parsed
            except IntentValidationError as exc:
                last_error = exc

        raise IntentValidationError(
            f"Intent classification failed validation after {self.max_validation_retries} attempts: {last_error}"
        )


class HeuristicIntentClassifier(BaseIntentClassifier):
    """Deterministic SERP-evidence-based intent classifier for 0-cost testing and benchmarking."""

    model_version = "heuristic-serp-v1"
    prompt_version = "heuristic_v1"

    TRANSACTIONAL_TERMS = (
        "mua ", "mua-", "buy ", "báo giá", "bao gia", "giá ", "price", "pricing",
        "tải ", "download", "đăng ký", "dang ky", "sign up", "order", "coupon",
        "giảm giá", "shop", "store", "dịch vụ ", "dich vu ", "thuê ", "hire ",
    )
    COMMERCIAL_TERMS = (
        "top ", "best ", "tốt nhất", "tot nhat", "so sánh", "so sanh", " vs ",
        "review", "đánh giá", "danh gia", "nên mua", "nen mua", "alternatives",
        "comparison", "chọn ", "recommended",
    )
    NAVIGATIONAL_TERMS = (
        "login", "đăng nhập", "dang nhap", "trang chủ", "official", "app ",
        "portal", "support", "facebook", "shopee", "youtube", "gmail", "ahrefs",
        "semrush", "canva", "hubspot", "salesforce", "zalo", "misa", "kiotviet",
    )
    INFORMATIONAL_TERMS = (
        "là gì", "la gi", "what is", "how to", "cách ", "cach ", "hướng dẫn",
        "huong dan", "guide", "tutorial", "tại sao", "tai sao", "why ",
        "kinh nghiệm", "ví dụ", "example", "definition", "meaning", "mẹo ",
    )

    def classify(
        self,
        *,
        keyword: str,
        country_code: str,
        language_code: str,
        serp_features: list[str],
        serp_results: list[SerpResultRecord],
        competitor_headings_by_url: dict[str, list[str]] | None = None,
    ) -> IntentClassificationOutput:
        kw_lower = f" {keyword.lower()} "
        scores: dict[SearchIntentType, float] = {
            "INFORMATIONAL": 0.1,
            "NAVIGATIONAL": 0.0,
            "COMMERCIAL": 0.0,
            "TRANSACTIONAL": 0.0,
        }
        signals: list[str] = []

        # 1. SERP features signals
        if "shopping" in serp_features or "local_pack" in serp_features:
            scores["TRANSACTIONAL"] += 1.5
            signals.append("SERP contains shopping/local_pack")
        if "featured_snippet" in serp_features or "people_also_ask" in serp_features:
            scores["INFORMATIONAL"] += 0.8
            signals.append("SERP contains featured_snippet/PAA")

        # 2. SERP result types & titles/snippets signals (strongest evidence)
        ecom_count = sum(1 for r in serp_results[:10] if r.result_type == "ECOMMERCE")
        if ecom_count >= 2:
            scores["TRANSACTIONAL"] += 2.2
            signals.append(f"{ecom_count} ecommerce results in Top 10")

        for r in serp_results[:5]:
            text = f" {r.title.lower()} {(r.snippet or '').lower()} {r.url.lower()} "
            if any(t in text for t in self.TRANSACTIONAL_TERMS):
                scores["TRANSACTIONAL"] += 0.7
            if any(t in text for t in self.COMMERCIAL_TERMS):
                scores["COMMERCIAL"] += 0.85
            if any(t in text for t in self.INFORMATIONAL_TERMS):
                scores["INFORMATIONAL"] += 0.7
            if any(t in text for t in ("/login", "/signin", "dang-nhap", "official")):
                scores["NAVIGATIONAL"] += 1.2

        # 3. Keyword query signals (supporting evidence)
        if any(t in kw_lower for t in self.NAVIGATIONAL_TERMS) and not any(
            t in kw_lower for t in self.COMMERCIAL_TERMS
        ) and not any(t in kw_lower for t in self.INFORMATIONAL_TERMS):
            scores["NAVIGATIONAL"] += 2.5
            signals.append("Query contains brand/navigational cue")
        if any(t in kw_lower for t in self.TRANSACTIONAL_TERMS):
            scores["TRANSACTIONAL"] += 2.0
            signals.append("Query contains transactional cue")
        if any(t in kw_lower for t in self.COMMERCIAL_TERMS):
            scores["COMMERCIAL"] += 2.2
            signals.append("Query contains commercial investigation cue")
        if any(t in kw_lower for t in self.INFORMATIONAL_TERMS):
            scores["INFORMATIONAL"] += 2.0
            signals.append("Query contains informational cue")

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        primary: SearchIntentType = ranked[0][0]
        top_score = ranked[0][1]
        second_intent: SearchIntentType | None = ranked[1][0] if ranked[1][1] >= 1.2 else None
        total = sum(scores.values()) or 1.0
        confidence = round(min(0.95, max(0.5, top_score / total + 0.25)), 3)

        evidence_urls = [r.url for r in serp_results[:3]]
        reasoning = (
            f"Classified as {primary} based on SERP evidence "
            f"({len(serp_results)} results analyzed; signals: {', '.join(signals) or 'organic title/URL pattern'})."
        )
        return IntentClassificationOutput(
            primary_intent=primary,
            secondary_intent=second_intent,
            confidence=confidence,
            reasoning=reasoning,
            evidence_urls=evidence_urls,
            serp_signals=signals,
        )


class IntentService:
    """Orchestrates evidence-based Search Intent classification and persists versioned records."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.serp_repo = SerpRepository(db)

    def classify_and_save(
        self,
        *,
        keyword: Keyword,
        serp_snapshot: SerpSnapshot | None,
        classifier: BaseIntentClassifier,
        country_code: str,
        language_code: str,
    ) -> KeywordIntent:
        """Classify a keyword using its SERP snapshot and persist KeywordIntent with provenance."""
        serp_results: list[SerpResultRecord] = []
        headings_by_url: dict[str, list[str]] = {}
        serp_features: list[str] = []

        if serp_snapshot is not None:
            serp_features = list(serp_snapshot.serp_features or [])
            for res in sorted(serp_snapshot.results, key=lambda r: r.position):
                serp_results.append(
                    SerpResultRecord(
                        position=res.position,
                        url=res.url,
                        domain=res.domain,
                        title=res.title,
                        snippet=res.snippet,
                        result_type=res.result_type,  # type: ignore[arg-type]
                    )
                )
                if res.competitor_page and res.competitor_page.headings:
                    headings_by_url[res.url] = [
                        f"H{h.level}: {h.heading_text}"
                        for h in sorted(res.competitor_page.headings, key=lambda x: x.position_order)
                    ]

        output = classifier.classify(
            keyword=keyword.normalized_keyword,
            country_code=country_code,
            language_code=language_code,
            serp_features=serp_features,
            serp_results=serp_results,
            competitor_headings_by_url=headings_by_url,
        )
        validate_intent_evidence(output, {r.url for r in serp_results})

        intent = self.serp_repo.save_keyword_intent(
            keyword_id=keyword.id,
            serp_snapshot_id=serp_snapshot.id if serp_snapshot else None,
            primary_intent=output.primary_intent,
            secondary_intent=output.secondary_intent,
            confidence=output.confidence,
            reasoning=output.reasoning,
            evidence={
                "evidence_urls": output.evidence_urls,
                "serp_signals": output.serp_signals,
                "content_type_dominant": output.content_type_dominant,
            },
            model_version=classifier.model_version,
            prompt_version=classifier.prompt_version,
            origin="AI",
        )
        self.db.commit()
        return intent
