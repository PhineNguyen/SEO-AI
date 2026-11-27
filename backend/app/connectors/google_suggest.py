"""Free Google Autocomplete (Suggest) keyword discovery connector."""

from __future__ import annotations

from typing import Any

import httpx

from app.connectors.base import BaseDataProvider
from app.schemas.provenance import KeywordIdeaRecord, ProviderErrorRecord, ProviderResult

GOOGLE_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"

VI_MODIFIERS: tuple[str, ...] = (
    "{seed}",
    "{seed} là gì",
    "{seed} tốt nhất",
    "cách {seed}",
    "giá {seed}",
    "so sánh {seed}",
    "review {seed}",
    "mua {seed}",
)

EN_MODIFIERS: tuple[str, ...] = (
    "{seed}",
    "what is {seed}",
    "best {seed}",
    "how to {seed}",
    "{seed} pricing",
    "{seed} vs",
    "{seed} review",
    "buy {seed}",
)


class GoogleSuggestConnector(BaseDataProvider):
    """Fetches real keyword suggestions from Google Autocomplete (no API key required)."""

    provider_code = "google_suggest"

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._http_client = http_client
        self._timeout = timeout_seconds

    def check_credentials(self) -> bool:
        return True

    def _fetch_single_query(
        self,
        client: httpx.Client,
        query: str,
        *,
        country_code: str,
        language_code: str,
    ) -> list[str]:
        resp = client.get(
            GOOGLE_SUGGEST_URL,
            params={
                "client": "firefox",
                "hl": language_code.lower(),
                "gl": country_code.upper(),
                "q": query,
            },
            headers={"User-Agent": "Mozilla/5.0 (compatible; SEOKeywordResearchBot/1.0)"},
        )
        resp.raise_for_status()
        payload: Any = resp.json()
        if isinstance(payload, list) and len(payload) >= 2 and isinstance(payload[1], list):
            return [str(item).strip() for item in payload[1] if str(item).strip()]
        return []

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str = "VN",
        language_code: str = "vi",
        limit: int = 40,
        expand_modifiers: bool = True,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Collect real autocomplete suggestions without fabricating any quantitative metrics."""
        cleaned_seed = seed_keyword.strip()
        if not cleaned_seed:
            return ProviderResult(provider_code=self.provider_code, status="OK", items=[])

        is_vi = language_code.lower().startswith("vi")
        templates = (VI_MODIFIERS if is_vi else EN_MODIFIERS) if expand_modifiers else ("{seed}",)
        queries = [tpl.format(seed=cleaned_seed) for tpl in templates]

        client = self._http_client or httpx.Client(timeout=self._timeout)
        close_after = self._http_client is None
        seen: set[str] = set()
        items: list[KeywordIdeaRecord] = []
        errors: list[ProviderErrorRecord] = []

        try:
            for q in queries:
                if len(items) >= limit:
                    break
                try:
                    suggestions = self._fetch_single_query(
                        client, q, country_code=country_code, language_code=language_code
                    )
                except Exception as exc:
                    errors.append(
                        ProviderErrorRecord(
                            provider_code=self.provider_code,
                            error_type="UPSTREAM_ERROR",
                            message=f"Query '{q}' failed: {exc}",
                        )
                    )
                    continue

                for suggestion in suggestions:
                    norm = suggestion.lower()
                    if norm in seen:
                        continue
                    seen.add(norm)
                    items.append(
                        KeywordIdeaRecord(
                            original_keyword=suggestion,
                            source_code=self.provider_code,
                            country_code=country_code.upper(),
                            language_code=language_code.lower(),
                            keyword_type="RELATED",
                            metrics=[],
                        )
                    )
                    if len(items) >= limit:
                        break
        finally:
            if close_after:
                client.close()

        status_str = "OK" if items else ("ERROR" if errors else "OK")
        if items and errors:
            status_str = "PARTIAL"
        return ProviderResult(
            provider_code=self.provider_code,
            status=status_str,
            items=items,
            errors=errors,
        )

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str = "VN",
        language_code: str = "vi",
    ) -> ProviderResult[KeywordIdeaRecord]:
        return ProviderResult(provider_code=self.provider_code, status="OK", items=[])

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str = "VN",
        language_code: str = "vi",
        limit: int = 40,
    ) -> ProviderResult[KeywordIdeaRecord]:
        return self.get_keyword_ideas(
            seed_keyword,
            country_code=country_code,
            language_code=language_code,
            limit=limit,
            expand_modifiers=True,
        )
