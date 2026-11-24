"""SSRF-protected competitor HTML fetcher and heading (H1-H3) parser."""

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.utils.logging import get_logger

logger = get_logger(__name__)

BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")
MAX_REDIRECTS = 5


class SSRFBlockedError(Exception):
    """Raised when a URL resolves to a private, loopback, link-local, or disallowed host."""


@dataclass
class ExtractedHeading:
    """Single extracted HTML heading."""

    level: int
    text: str
    position_order: int


@dataclass
class CompetitorFetchResult:
    """Outcome of fetching and parsing a competitor webpage."""

    url: str
    fetch_status: str  # FETCHED | BLOCKED_SSRF | TIMEOUT | ERROR
    http_status: int | None = None
    page_title: str | None = None
    meta_description: str | None = None
    content_type_inferred: str | None = None
    word_count_estimate: int | None = None
    headings: list[ExtractedHeading] = field(default_factory=list)
    error_detail: str | None = None


def _is_disallowed_ip(ip_str: str) -> bool:
    """Return True for private, loopback, link-local, multicast, or reserved IPs."""
    ip_obj = ipaddress.ip_address(ip_str)
    return bool(
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_safe_public_url(
    url: str,
    *,
    dns_resolver: Callable[..., list[Any]] = socket.getaddrinfo,
) -> str:
    """Validate that a URL uses http/https and resolves strictly to public IP addresses."""
    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFBlockedError(f"Disallowed URL scheme: {parsed.scheme}")

    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        raise SSRFBlockedError("URL missing hostname")
    if hostname == "localhost" or any(hostname.endswith(sfx) for sfx in BLOCKED_HOST_SUFFIXES):
        raise SSRFBlockedError(f"Blocked internal hostname: {hostname}")

    # Direct IP literal check
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if _is_disallowed_ip(hostname):
            raise SSRFBlockedError(f"Blocked non-public IP literal: {hostname}")
        return url

    # DNS resolution check (all returned A/AAAA records must be public)
    try:
        addr_infos = dns_resolver(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"DNS resolution failed for {hostname}") from exc

    if not addr_infos:
        raise SSRFBlockedError(f"DNS returned no addresses for {hostname}")

    for info in addr_infos:
        sockaddr = info[4]
        resolved_ip = str(sockaddr[0])
        if _is_disallowed_ip(resolved_ip):
            raise SSRFBlockedError(
                f"Hostname '{hostname}' resolved to disallowed non-public IP"
            )

    return url


def _infer_content_type(title: str, headings: list[ExtractedHeading], url: str) -> str:
    combined = f"{title} {' '.join(h.text for h in headings[:5])} {url}".lower()
    if any(k in combined for k in ("top ", "best ", "tốt nhất", "danh sách", "review")):
        return "listicle"
    if any(k in combined for k in (" vs ", "so sánh", "comparison", "alternative")):
        return "comparison"
    if any(k in combined for k in ("là gì", "hướng dẫn", "how to", "guide", "what is", "cách ")):
        return "guide"
    if any(k in combined for k in ("bảng giá", "pricing", "mua ", "buy ", "product", "sản phẩm")):
        return "product"
    return "article"


def parse_competitor_html(html: str, url: str) -> CompetitorFetchResult:
    """Sanitize untrusted competitor HTML and extract title, meta description, and H1-H3."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    title_text = (
        " ".join(soup.title.get_text(" ", strip=True).split()) if soup.title else None
    )
    meta_desc = None
    meta_tag = soup.find("meta", attrs={"name": lambda v: isinstance(v, str) and v.lower() == "description"})
    if meta_tag and meta_tag.get("content"):
        meta_desc = " ".join(str(meta_tag["content"]).split())[:500]

    headings: list[ExtractedHeading] = []
    order = 1
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if not text:
            continue
        level = int(tag.name[1])
        headings.append(ExtractedHeading(level=level, text=text[:300], position_order=order))
        order += 1

    body_text = soup.get_text(" ", strip=True)
    word_count = len(body_text.split()) if body_text else 0

    return CompetitorFetchResult(
        url=url,
        fetch_status="FETCHED",
        http_status=200,
        page_title=title_text[:300] if title_text else None,
        meta_description=meta_desc,
        content_type_inferred=_infer_content_type(title_text or "", headings, url),
        word_count_estimate=word_count,
        headings=headings,
    )


class SafeCompetitorFetcher:
    """Fetches competitor pages from SERP URLs with strict SSRF, redirect, and size guards."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_bytes: int = 2_097_152,
        user_agent: str = "KeywordResearchAgentBot/1.0",
        dns_resolver: Callable[..., list[Any]] = socket.getaddrinfo,
        client: httpx.Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self._dns_resolver = dns_resolver
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_and_parse(self, url: str) -> CompetitorFetchResult:
        """Validate URL (including every redirect hop), stream up to max_bytes, and parse HTML."""
        current_url = url
        try:
            for _hop in range(MAX_REDIRECTS + 1):
                validate_safe_public_url(current_url, dns_resolver=self._dns_resolver)

                with self._client.stream("GET", current_url) as response:
                    status = response.status_code
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            return CompetitorFetchResult(
                                url=url,
                                fetch_status="ERROR",
                                http_status=status,
                                error_detail="Redirect missing Location header",
                            )
                        current_url = urljoin(current_url, location)
                        continue

                    if status >= 400:
                        return CompetitorFetchResult(
                            url=url,
                            fetch_status="ERROR",
                            http_status=status,
                            error_detail=f"HTTP {status}",
                        )

                    chunks: list[bytes] = []
                    total_bytes = 0
                    for chunk in response.iter_bytes():
                        remaining = self.max_bytes - total_bytes
                        if remaining <= 0:
                            break
                        chunks.append(chunk[:remaining])
                        total_bytes += len(chunks[-1])

                    raw_html = b"".join(chunks).decode("utf-8", errors="replace")
                    parsed = parse_competitor_html(raw_html, current_url)
                    parsed.http_status = status
                    return parsed

            return CompetitorFetchResult(
                url=url,
                fetch_status="ERROR",
                error_detail="Too many redirects",
            )
        except SSRFBlockedError as exc:
            logger.warning("competitor_fetch_ssrf_blocked", url=url, reason=str(exc))
            return CompetitorFetchResult(
                url=url,
                fetch_status="BLOCKED_SSRF",
                error_detail=str(exc),
            )
        except httpx.TimeoutException:
            return CompetitorFetchResult(
                url=url,
                fetch_status="TIMEOUT",
                error_detail="Request timed out",
            )
        except Exception as exc:
            return CompetitorFetchResult(
                url=url,
                fetch_status="ERROR",
                error_detail=type(exc).__name__,
            )
