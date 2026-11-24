"""Normalization and validation helpers for domains, URLs, countries, and languages."""

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"fbclid", "gclid", "msclkid", "ref", "mc_cid", "mc_eid"}

DOMAIN_REGEX = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
COUNTRY_CODE_REGEX = re.compile(r"^[A-Z]{2}$")
LANGUAGE_CODE_REGEX = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def _reject_ip_or_localhost(hostname: str) -> None:
    """Reject localhost and literal IPv4/IPv6 hostnames."""
    lowered = hostname.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        raise ValueError("localhost is not allowed as a project domain or URL")
    try:
        ipaddress.ip_address(lowered)
    except ValueError:
        return
    raise ValueError("IP literals are not allowed as a project domain or URL")


def normalize_domain(raw_domain: str) -> str:
    """Normalize a domain string to lowercase host without scheme, path, or leading www."""
    cleaned = raw_domain.strip()
    if not cleaned:
        raise ValueError("Domain must not be empty")

    candidate = cleaned if "://" in cleaned else f"https://{cleaned}"
    parsed = urlparse(candidate)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid domain")

    hostname = hostname.rstrip(".").lower()
    _reject_ip_or_localhost(hostname)

    if hostname.startswith("www."):
        stripped_www = hostname[4:]
        if "." in stripped_www:
            hostname = stripped_www

    if len(hostname) > 253 or not DOMAIN_REGEX.match(hostname):
        raise ValueError(f"Invalid domain format: {raw_domain}")
    return hostname


def normalize_base_url(raw_url: str) -> str:
    """Validate and normalize an HTTP/HTTPS base URL for a project website."""
    cleaned = raw_url.strip()
    if not cleaned:
        raise ValueError("Base URL must not be empty")

    parsed = urlparse(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Base URL must use http or https scheme")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Base URL must include a valid hostname")

    hostname_lower = hostname.rstrip(".").lower()
    _reject_ip_or_localhost(hostname_lower)
    if len(hostname_lower) > 253 or not DOMAIN_REGEX.match(hostname_lower):
        raise ValueError(f"Invalid base URL hostname: {hostname}")

    netloc = f"{hostname_lower}:{parsed.port}" if parsed.port else hostname_lower
    path = parsed.path
    if path == "/" and not parsed.query and not parsed.fragment:
        path = ""

    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def normalize_country_code(raw: str) -> str:
    """Normalize and validate an ISO 3166-1 alpha-2 country code (e.g. VN, US)."""
    normalized = raw.strip().upper()
    if not COUNTRY_CODE_REGEX.match(normalized):
        raise ValueError("target_country must be a 2-letter uppercase ISO code (e.g. VN, US)")
    return normalized


def normalize_language_code(raw: str) -> str:
    """Normalize and validate a BCP-47 language tag (e.g. vi, en, en-US)."""
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > 10:
        raise ValueError("target_language must be a valid language tag (1-10 chars)")

    parts = cleaned.split("-")
    parts[0] = parts[0].lower()
    normalized = "-".join(parts)
    if not LANGUAGE_CODE_REGEX.match(normalized):
        raise ValueError("target_language must match BCP-47 format (e.g. vi, en, en-US)")
    return normalized


def normalize_serp_url(raw_url: str) -> str:
    """Normalize a SERP URL for accurate cross-keyword SERP Overlap matching.

    Lowercases scheme and host, strips leading www., drops fragments and common
    tracking query parameters (utm_*, fbclid, gclid), and trims trailing slashes.
    """
    parsed = urlparse(raw_url.strip())
    scheme = (parsed.scheme or "https").lower()
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if hostname.startswith("www.") and "." in hostname[4:]:
        hostname = hostname[4:]

    netloc = f"{hostname}:{parsed.port}" if parsed.port and parsed.port not in (80, 443) else hostname
    path = parsed.path or ""
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    elif path == "/":
        path = ""

    filtered_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_QUERY_KEYS
        and not any(k.lower().startswith(p) for p in TRACKING_QUERY_PREFIXES)
    ]
    filtered_params.sort()
    query = urlencode(filtered_params)
    return urlunparse((scheme, netloc, path, "", query, ""))
