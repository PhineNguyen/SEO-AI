"""Resilient HTTP client with rate limiting, exponential backoff retries, and quota tracking."""

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.connectors.exceptions import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    ConnectorTimeoutError,
    ConnectorUpstreamError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Thread-safe minimum-interval rate limiter for external API connectors."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._min_interval = 1.0 / requests_per_second
        self._clock = clock
        self._sleep = sleep_fn
        self._lock = threading.Lock()
        self._next_allowed_at: float | None = None

    def acquire(self) -> float:
        """Wait until the next request slot is available and return seconds waited."""
        with self._lock:
            now = self._clock()
            if self._next_allowed_at is None or now >= self._next_allowed_at:
                self._next_allowed_at = now + self._min_interval
                return 0.0

            wait_seconds = self._next_allowed_at - now
            self._sleep(wait_seconds)
            self._next_allowed_at = self._clock() + self._min_interval
            return wait_seconds


@dataclass(frozen=True)
class RetryConfig:
    """Retry and exponential backoff parameters for external HTTP requests."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    jitter: bool = False
    retryable_status_codes: frozenset[int] = frozenset({429, 500, 502, 503, 504})

    def compute_delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Compute delay before the next retry attempt (1-indexed attempt)."""
        if retry_after is not None and retry_after >= 0:
            return min(retry_after, self.max_delay_seconds)
        delay = min(self.base_delay_seconds * (2 ** max(0, attempt - 1)), self.max_delay_seconds)
        if self.jitter:
            delay += random.uniform(0.0, delay * 0.25)
        return min(delay, self.max_delay_seconds)


@dataclass
class QuotaTracker:
    """Tracks API request counts and unit consumption for a connector instance."""

    provider_code: str
    requests_made: int = 0
    units_consumed: float = 0.0
    quota_remaining: float | None = None

    def record_request(self, units: float = 0.0, remaining: float | None = None) -> None:
        """Increment request and unit counters after an upstream call."""
        self.requests_made += 1
        self.units_consumed += units
        if remaining is not None:
            self.quota_remaining = remaining


def _parse_retry_after(header_value: str | None) -> float | None:
    """Parse numeric Retry-After header seconds if present."""
    if not header_value:
        return None
    try:
        seconds = float(header_value.strip())
    except ValueError:
        return None
    return max(0.0, seconds)


class ResilientHttpClient:
    """Synchronous HTTP client wrapper providing retries, timeouts, and rate-limit handling."""

    def __init__(
        self,
        provider_code: str,
        *,
        base_url: str = "",
        timeout_seconds: float = 15.0,
        retry_config: RetryConfig | None = None,
        rate_limiter: RateLimiter | None = None,
        default_headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.provider_code = provider_code
        self.retry_config = retry_config or RetryConfig()
        self.rate_limiter = rate_limiter
        self.quota = QuotaTracker(provider_code=provider_code)
        self._sleep = sleep_fn
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers=default_headers,
        )

    def __enter__(self) -> "ResilientHttpClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying httpx.Client if owned by this wrapper."""
        if self._owns_client:
            self._client.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        auth: Any = None,
        units: float = 1.0,
    ) -> httpx.Response:
        """Execute an HTTP request with rate limiting, retries, and typed error mapping."""
        max_attempts = max(1, self.retry_config.max_attempts)

        for attempt in range(1, max_attempts + 1):
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()

            start = time.perf_counter()
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=headers,
                    auth=auth,
                )
            except httpx.TimeoutException as exc:
                duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
                if attempt < max_attempts:
                    delay = self.retry_config.compute_delay(attempt)
                    logger.warning(
                        "connector_http_retry",
                        provider=self.provider_code,
                        method=method,
                        url=url,
                        attempt=attempt,
                        reason="timeout",
                        delay_seconds=delay,
                        duration_ms=duration_ms,
                    )
                    self._sleep(delay)
                    continue
                logger.error(
                    "connector_http_error",
                    provider=self.provider_code,
                    method=method,
                    url=url,
                    reason="timeout",
                    duration_ms=duration_ms,
                )
                raise ConnectorTimeoutError(
                    self.provider_code,
                    f"Request timed out after {max_attempts} attempts",
                ) from exc
            except httpx.RequestError as exc:
                duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
                if attempt < max_attempts:
                    delay = self.retry_config.compute_delay(attempt)
                    logger.warning(
                        "connector_http_retry",
                        provider=self.provider_code,
                        method=method,
                        url=url,
                        attempt=attempt,
                        reason=type(exc).__name__,
                        delay_seconds=delay,
                        duration_ms=duration_ms,
                    )
                    self._sleep(delay)
                    continue
                logger.error(
                    "connector_http_error",
                    provider=self.provider_code,
                    method=method,
                    url=url,
                    reason=type(exc).__name__,
                    duration_ms=duration_ms,
                )
                raise ConnectorUpstreamError(
                    self.provider_code,
                    f"Network error ({type(exc).__name__}) after {max_attempts} attempts",
                ) from exc

            duration_ms = round((time.perf_counter() - start) * 1000.0, 2)
            self.quota.record_request(units=units)
            status_code = response.status_code

            if 200 <= status_code < 300:
                logger.info(
                    "connector_http_request",
                    provider=self.provider_code,
                    method=method,
                    url=url,
                    status_code=status_code,
                    attempt=attempt,
                    duration_ms=duration_ms,
                )
                return response

            if status_code in (401, 403):
                logger.error(
                    "connector_http_error",
                    provider=self.provider_code,
                    method=method,
                    url=url,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
                raise ConnectorAuthError(
                    self.provider_code,
                    f"Authentication or permission error (HTTP {status_code})",
                    http_status=status_code,
                )

            if status_code == 429:
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                if attempt < max_attempts:
                    delay = self.retry_config.compute_delay(attempt, retry_after=retry_after)
                    logger.warning(
                        "connector_http_retry",
                        provider=self.provider_code,
                        method=method,
                        url=url,
                        status_code=429,
                        attempt=attempt,
                        delay_seconds=delay,
                        duration_ms=duration_ms,
                    )
                    self._sleep(delay)
                    continue
                raise ConnectorRateLimitError(
                    self.provider_code,
                    f"Rate limited (HTTP 429) after {max_attempts} attempts",
                    http_status=429,
                    retry_after_seconds=retry_after,
                )

            if status_code in self.retry_config.retryable_status_codes:
                if attempt < max_attempts:
                    delay = self.retry_config.compute_delay(attempt)
                    logger.warning(
                        "connector_http_retry",
                        provider=self.provider_code,
                        method=method,
                        url=url,
                        status_code=status_code,
                        attempt=attempt,
                        delay_seconds=delay,
                        duration_ms=duration_ms,
                    )
                    self._sleep(delay)
                    continue
                raise ConnectorUpstreamError(
                    self.provider_code,
                    f"Upstream server error (HTTP {status_code}) after {max_attempts} attempts",
                    http_status=status_code,
                )

            logger.error(
                "connector_http_error",
                provider=self.provider_code,
                method=method,
                url=url,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            raise ConnectorError(
                self.provider_code,
                f"Upstream request failed with HTTP {status_code}",
                retryable=False,
                http_status=status_code,
            )

        raise ConnectorUpstreamError(self.provider_code, "Request exhausted retry loop")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform a resilient HTTP GET request."""
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Perform a resilient HTTP POST request."""
        return self.request("POST", url, **kwargs)
