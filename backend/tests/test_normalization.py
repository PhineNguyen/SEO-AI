"""Unit tests for domain, base URL, country, language normalization, and settings schemas."""

import pytest
from app.schemas.project import ProjectSettingsUpdate
from app.utils.normalization import (
    normalize_base_url,
    normalize_country_code,
    normalize_domain,
    normalize_language_code,
)
from pydantic import ValidationError


def test_normalize_domain_valid_inputs() -> None:
    assert normalize_domain("https://WWW.Example.VN/blog?a=1") == "example.vn"
    assert normalize_domain("  sub.Domain.com:8080/path ") == "sub.domain.com"
    assert normalize_domain("example.com.") == "example.com"


@pytest.mark.parametrize(
    "bad_domain",
    [
        "",
        "   ",
        "localhost",
        "api.localhost",
        "127.0.0.1",
        "http://192.168.1.10/admin",
        "::1",
        "not a domain",
        "singlelabel",
    ],
)
def test_normalize_domain_rejects_invalid_and_local_hosts(bad_domain: str) -> None:
    with pytest.raises(ValueError):
        normalize_domain(bad_domain)


def test_normalize_base_url_valid_and_invalid() -> None:
    assert normalize_base_url("https://Example.VN/") == "https://example.vn"
    assert normalize_base_url("http://blog.example.vn/seo") == "http://blog.example.vn/seo"

    for bad_url in (
        "ftp://example.vn",
        "http://localhost:8000",
        "http://192.168.1.1",
        "https://127.0.0.1:8000",
        "example.vn",
    ):
        with pytest.raises(ValueError):
            normalize_base_url(bad_url)


def test_normalize_country_and_language_codes() -> None:
    assert normalize_country_code(" vn ") == "VN"
    assert normalize_language_code(" VI ") == "vi"
    assert normalize_language_code("EN-US") == "en-US"

    with pytest.raises(ValueError):
        normalize_country_code("VNM")
    with pytest.raises(ValueError):
        normalize_country_code("12")
    with pytest.raises(ValueError):
        normalize_language_code("english_us")


def test_project_settings_clustering_weights_validation() -> None:
    valid = ProjectSettingsUpdate(
        clustering_weights={"semantic": 0.4, "serp_overlap": 0.4, "intent": 0.2},
        prioritization_weights={"volume": 0.3, "kd": 0.2},
    )
    assert valid.clustering_weights == {"semantic": 0.4, "serp_overlap": 0.4, "intent": 0.2}

    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(
            clustering_weights={"semantic": 0.5, "serp_overlap": 0.5, "intent": 0.2}
        )

    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(
            clustering_weights={"semantic": 0.5, "serp_overlap": 0.5}
        )

    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(prioritization_weights={"volume": -0.1})
