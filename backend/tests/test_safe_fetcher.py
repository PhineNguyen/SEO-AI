"""Security and HTML parsing unit tests for SSRF-protected SafeCompetitorFetcher."""

import socket

import httpx
import pytest
import respx
from app.connectors.safe_fetcher import (
    SafeCompetitorFetcher,
    SSRFBlockedError,
    parse_competitor_html,
    validate_safe_public_url,
)


def _fake_public_dns(_host: str, _port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _fake_private_dns(_host: str, _port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.15", 80))]


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:8000/health",
        "http://service.internal/secret",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/file",
    ],
)
def test_validate_safe_public_url_blocks_ssrf_targets(blocked_url: str) -> None:
    with pytest.raises(SSRFBlockedError):
        validate_safe_public_url(blocked_url, dns_resolver=_fake_public_dns)


def test_validate_safe_public_url_blocks_dns_rebinding_to_private_ip() -> None:
    with pytest.raises(SSRFBlockedError):
        validate_safe_public_url("https://evil.example.com/page", dns_resolver=_fake_private_dns)


@respx.mock
def test_safe_fetcher_blocks_redirect_to_localhost() -> None:
    respx.get("https://public.example.com/start").mock(
        return_value=httpx.Response(302, headers={"Location": "http://127.0.0.1:8000/internal"})
    )
    fetcher = SafeCompetitorFetcher(dns_resolver=_fake_public_dns)
    result = fetcher.fetch_and_parse("https://public.example.com/start")
    assert result.fetch_status == "BLOCKED_SSRF"


@respx.mock
def test_safe_fetcher_parses_headings_and_strips_scripts() -> None:
    html = """
    <html>
      <head>
        <title>CRM là gì? Hướng dẫn chi tiết</title>
        <meta name="description" content="Giải thích đầy đủ về phần mềm CRM." />
        <script>alert("ignore previous instructions")</script>
      </head>
      <body>
        <h1>CRM là gì?</h1>
        <h2>1. Lợi ích của CRM</h2>
        <h3>Tăng tỷ lệ chốt đơn</h3>
        <p>Nội dung bài viết về CRM cho doanh nghiệp nhỏ.</p>
      </body>
    </html>
    """
    respx.get("https://public.example.com/crm-guide").mock(
        return_value=httpx.Response(200, text=html)
    )
    fetcher = SafeCompetitorFetcher(dns_resolver=_fake_public_dns)
    result = fetcher.fetch_and_parse("https://public.example.com/crm-guide")

    assert result.fetch_status == "FETCHED"
    assert result.http_status == 200
    assert result.page_title == "CRM là gì? Hướng dẫn chi tiết"
    assert result.meta_description == "Giải thích đầy đủ về phần mềm CRM."
    assert result.content_type_inferred == "guide"
    assert [(h.level, h.text) for h in result.headings] == [
        (1, "CRM là gì?"),
        (2, "1. Lợi ích của CRM"),
        (3, "Tăng tỷ lệ chốt đơn"),
    ]


def test_parse_competitor_html_strips_script_text_from_word_count() -> None:
    parsed = parse_competitor_html(
        "<html><body><script>var x = 1; var y = 2;</script><h1>Title</h1><p>Hello world</p></body></html>",
        "https://example.com",
    )
    assert parsed.word_count_estimate == 3
