"""Typed exception hierarchy for external SEO data connectors."""

from typing import Any

from app.schemas.provenance import ProviderErrorRecord


class ConnectorError(Exception):
    """Base exception for all SEO data provider connector failures."""

    error_code: str = "CONNECTOR_ERROR"

    def __init__(
        self,
        provider_code: str,
        message: str,
        *,
        retryable: bool = False,
        http_status: int | None = None,
    ) -> None:
        super().__init__(f"[{provider_code}] {message}")
        self.provider_code = provider_code
        self.message = message
        self.retryable = retryable
        self.http_status = http_status

    def to_error_record(self, context: dict[str, Any] | None = None) -> ProviderErrorRecord:
        """Convert this exception into a structured, persistable ProviderErrorRecord."""
        return ProviderErrorRecord(
            provider_code=self.provider_code,
            error_code=self.error_code,
            message=self.message,
            retryable=self.retryable,
            http_status=self.http_status,
            context=context or {},
        )


class ConnectorConfigError(ConnectorError):
    """Raised when required API credentials or connector settings are missing."""

    error_code = "CONNECTOR_CONFIG_ERROR"

    def __init__(self, provider_code: str, message: str) -> None:
        super().__init__(provider_code, message, retryable=False, http_status=None)


class ConnectorAuthError(ConnectorError):
    """Raised on HTTP 401/403 authentication or authorization failures."""

    error_code = "CONNECTOR_AUTH_ERROR"

    def __init__(
        self,
        provider_code: str,
        message: str,
        *,
        http_status: int | None = 401,
    ) -> None:
        super().__init__(provider_code, message, retryable=False, http_status=http_status)


class ConnectorRateLimitError(ConnectorError):
    """Raised when an upstream provider rate-limits requests (HTTP 429)."""

    error_code = "CONNECTOR_RATE_LIMIT"

    def __init__(
        self,
        provider_code: str,
        message: str,
        *,
        http_status: int | None = 429,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(provider_code, message, retryable=True, http_status=http_status)
        self.retry_after_seconds = retry_after_seconds


class ConnectorQuotaExceededError(ConnectorError):
    """Raised when an upstream API account has exhausted its credit/unit balance."""

    error_code = "CONNECTOR_QUOTA_EXCEEDED"

    def __init__(
        self,
        provider_code: str,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(provider_code, message, retryable=False, http_status=http_status)


class ConnectorTimeoutError(ConnectorError):
    """Raised when an upstream request times out across all retry attempts."""

    error_code = "CONNECTOR_TIMEOUT"

    def __init__(self, provider_code: str, message: str) -> None:
        super().__init__(provider_code, message, retryable=True, http_status=None)


class ConnectorUpstreamError(ConnectorError):
    """Raised on transient upstream 5xx or network connectivity failures."""

    error_code = "CONNECTOR_UPSTREAM_ERROR"

    def __init__(
        self,
        provider_code: str,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(provider_code, message, retryable=True, http_status=http_status)


class ConnectorNotSupportedError(ConnectorError):
    """Raised when a capability (e.g. SERP fetch) is not supported by a provider."""

    error_code = "CONNECTOR_NOT_SUPPORTED"

    def __init__(self, provider_code: str, message: str) -> None:
        super().__init__(provider_code, message, retryable=False, http_status=None)
