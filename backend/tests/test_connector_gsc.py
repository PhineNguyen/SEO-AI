"""Unit tests for Google Search Console OAuth manager and Search Analytics connector."""

from datetime import date

import httpx
import pytest
import respx
from app.config import Settings
from app.connectors import (
    GSC_READONLY_SCOPE,
    ConnectorNotSupportedError,
    GoogleOAuthManager,
    GscConnector,
    ResilientHttpClient,
    RetryConfig,
)
from app.schemas.provenance import MetricType


@respx.mock
def test_google_oauth_manager_url_exchange_and_refresh() -> None:
    settings = Settings(
        GOOGLE_CLIENT_ID="test-client-id.apps.googleusercontent.com",
        GOOGLE_CLIENT_SECRET="test-client-secret",
        GOOGLE_OAUTH_REDIRECT_URI="http://localhost:8000/api/v1/oauth/google/callback",
    )
    http = ResilientHttpClient(
        "google_oauth",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    manager = GoogleOAuthManager(settings, http_client=http)

    auth_url = manager.build_authorization_url(state="state-token-123")
    assert "accounts.google.com/o/oauth2/v2/auth" in auth_url
    assert "access_type=offline" in auth_url
    assert "webmasters.readonly" in auth_url
    assert "state=state-token-123" in auth_url
    assert GSC_READONLY_SCOPE in "https://www.googleapis.com/auth/webmasters.readonly"

    respx.post("https://oauth2.googleapis.com/token").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "access_token": "ya29.initial",
                    "refresh_token": "1//refresh-token",
                    "expires_in": 3600,
                },
            ),
            httpx.Response(
                200,
                json={
                    "access_token": "ya29.refreshed",
                    "expires_in": 3600,
                },
            ),
        ]
    )

    exchanged = manager.exchange_code("auth-code-xyz")
    assert exchanged["access_token"] == "ya29.initial"
    assert exchanged["refresh_token"] == "1//refresh-token"

    refreshed = manager.refresh_access_token("1//refresh-token")
    assert refreshed["access_token"] == "ya29.refreshed"


@respx.mock
def test_gsc_connector_enforces_verified_property_and_paginates() -> None:
    respx.get("https://www.googleapis.com/webmasters/v3/sites").mock(
        return_value=httpx.Response(
            200,
            json={
                "siteEntry": [
                    {"siteUrl": "sc-domain:example.vn", "permissionLevel": "siteOwner"},
                    {"siteUrl": "https://unverified.vn/", "permissionLevel": "siteUnverifiedUser"},
                ]
            },
        )
    )
    query_route = respx.post(
        "https://www.googleapis.com/webmasters/v3/sites/sc-domain%3Aexample.vn/searchAnalytics/query"
    ).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "rows": [
                        {
                            "keys": ["phan mem crm"],
                            "clicks": 120,
                            "impressions": 3000,
                            "ctr": 0.04,
                            "position": 5.2,
                        },
                        {
                            "keys": ["crm cho doanh nghiep nho"],
                            "clicks": 45,
                            "impressions": 900,
                            "ctr": 0.05,
                            "position": 7.8,
                        },
                    ]
                },
            ),
            httpx.Response(
                200,
                json={
                    "rows": [
                        {
                            "keys": ["bao gia crm"],
                            "clicks": 30,
                            "impressions": 400,
                            "ctr": 0.075,
                            "position": 4.1,
                        }
                    ]
                },
            ),
        ]
    )

    http = ResilientHttpClient(
        "gsc_api",
        base_url="https://www.googleapis.com/webmasters/v3",
        retry_config=RetryConfig(max_attempts=1),
        sleep_fn=lambda _s: None,
    )
    gsc = GscConnector(access_token="ya29.valid", site_url="sc-domain:example.vn", http_client=http)

    # Unverified property must be blocked with CONNECTOR_AUTH_ERROR
    blocked = gsc.query_search_analytics(
        "https://unverified.vn/",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 11, 1),
        country_code="VN",
        language_code="vi",
    )
    assert blocked.status == "ERROR"
    assert blocked.errors[0].error_code == "CONNECTOR_AUTH_ERROR"

    # Verified property paginates across 2 requests when row_limit=2
    result = gsc.query_search_analytics(
        "sc-domain:example.vn",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 11, 1),
        country_code="VN",
        language_code="vi",
        row_limit=2,
        max_rows=10,
    )
    assert result.status == "OK"
    assert query_route.call_count == 2
    assert len(result.items) == 3

    first_metrics = {m.metric_type: m for m in result.items[0].metrics}
    assert first_metrics[MetricType.GSC_CLICKS].numeric_value == 120.0
    assert first_metrics[MetricType.GSC_IMPRESSIONS].numeric_value == 3000.0
    assert first_metrics[MetricType.GSC_CTR].numeric_value == 0.04
    assert first_metrics[MetricType.GSC_POSITION].numeric_value == 5.2

    # Market-wide keyword ideas are explicitly unsupported on GSC
    with pytest.raises(ConnectorNotSupportedError):
        gsc.get_keyword_ideas("crm", country_code="VN", language_code="vi")
