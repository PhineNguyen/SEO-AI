"""Unified BaseDataProvider interface for all SEO keyword and SERP connectors."""

from abc import ABC, abstractmethod
from typing import Any

from app.connectors.exceptions import ConnectorConfigError, ConnectorNotSupportedError
from app.schemas.provenance import (
    DeviceType,
    KeywordIdeaRecord,
    ProviderResult,
    SerpSnapshotRecord,
)


class BaseDataProvider(ABC):
    """Abstract base interface implemented by all external SEO data providers."""

    provider_code: str = "unknown"
    supports_serp: bool = False
    supports_keyword_ideas: bool = True
    supports_keyword_metrics: bool = True

    @abstractmethod
    def check_credentials(self) -> bool:
        """Return True if required credentials or configuration are present."""

    def require_credentials(self) -> None:
        """Raise ConnectorConfigError if credentials are missing."""
        if not self.check_credentials():
            raise ConnectorConfigError(
                self.provider_code,
                f"Credentials are not configured for provider '{self.provider_code}'",
            )

    @abstractmethod
    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Discover keyword ideas from a seed keyword."""

    @abstractmethod
    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Collect metrics (volume, KD, CPC, competition) for a list of keywords."""

    @abstractmethod
    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Collect semantically or SERP-related keywords for a seed keyword."""

    def get_serp_results(
        self,
        keyword: str,
        *,
        country_code: str,
        language_code: str,
        device: DeviceType = "desktop",
        location_name: str | None = None,
        depth: int = 10,
    ) -> ProviderResult[SerpSnapshotRecord]:
        """Collect Top-N organic SERP results and SERP features if supported."""
        raise ConnectorNotSupportedError(
            self.provider_code,
            f"Provider '{self.provider_code}' does not support SERP collection",
        )

    def close(self) -> None:  # noqa: B027
        """Release underlying resources (e.g. HTTP connection pools)."""

    def __enter__(self) -> "BaseDataProvider":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
