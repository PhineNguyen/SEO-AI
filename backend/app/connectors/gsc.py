"""Google Search Console OAuth 2.0 manager and Search Analytics connector."""

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.connectors.base import BaseDataProvider
from app.connectors.exceptions import (
    ConnectorAuthError,
    ConnectorConfigError,
    ConnectorError,
    ConnectorNotSupportedError,
)
from app.connectors.http_client import RateLimiter, ResilientHttpClient, RetryConfig
from app.models.oauth_credential import OAuthCredential
from app.schemas.provenance import (
    KeywordCandidateType,
    KeywordIdeaRecord,
    MetricRecord,
    MetricType,
    ProviderResult,
)
from app.utils.normalization import normalize_country_code, normalize_language_code
from app.utils.security import decrypt_oauth_token, encrypt_oauth_token

GSC_READONLY_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_API_BASE_URL = "https://www.googleapis.com/webmasters/v3"

# ISO-2 to ISO-3 mapping for GSC country dimension filter when needed.
ISO2_TO_ISO3: dict[str, str] = {
    "VN": "vnm",
    "US": "usa",
    "GB": "gbr",
    "SG": "sgp",
    "AU": "aus",
    "CA": "can",
    "DE": "deu",
    "FR": "fra",
    "JP": "jpn",
}


class GoogleOAuthManager:
    """Manages Google OAuth 2.0 URL generation, token exchange, refresh, and encrypted storage."""

    def __init__(
        self,
        settings: Settings,
        *,
        http_client: ResilientHttpClient | None = None,
    ) -> None:
        self.settings = settings
        self._http = http_client or ResilientHttpClient(
            provider_code="google_oauth",
            timeout_seconds=15.0,
            retry_config=RetryConfig(max_attempts=2, base_delay_seconds=0.5),
        )

    def _require_client_config(self) -> tuple[str, str, str]:
        client_id = (self.settings.GOOGLE_CLIENT_ID or "").strip()
        client_secret = (
            self.settings.GOOGLE_CLIENT_SECRET.get_secret_value().strip()
            if self.settings.GOOGLE_CLIENT_SECRET is not None
            else ""
        )
        redirect_uri = self.settings.GOOGLE_OAUTH_REDIRECT_URI.strip()
        if not client_id or not client_secret:
            raise ConnectorConfigError(
                "google_gsc",
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured",
            )
        return client_id, client_secret, redirect_uri

    def build_authorization_url(
        self,
        *,
        state: str,
        scopes: list[str] | None = None,
    ) -> str:
        """Build a Google OAuth 2.0 consent URL requesting offline refresh tokens."""
        client_id, _secret, redirect_uri = self._require_client_config()
        resolved_scopes = scopes or [GSC_READONLY_SCOPE]
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(resolved_scopes),
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"{GOOGLE_AUTH_URL}?{query}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        """Exchange an OAuth authorization code for access and refresh tokens."""
        client_id, client_secret, redirect_uri = self._require_client_config()
        response = self._http.post(
            GOOGLE_TOKEN_URL,
            json={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            units=0.0,
        )
        return dict(response.json())

    def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Use a stored refresh token to obtain a fresh Google OAuth access token."""
        client_id, client_secret, _redirect_uri = self._require_client_config()
        response = self._http.post(
            GOOGLE_TOKEN_URL,
            json={
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
            },
            units=0.0,
        )
        return dict(response.json())

    def save_encrypted_credential(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        provider: str,
        access_token: str,
        refresh_token: str | None = None,
        scopes: list[str] | None = None,
        expires_in_seconds: int | None = None,
        account_email: str | None = None,
    ) -> OAuthCredential:
        """Encrypt and upsert a user's Google OAuth credential in PostgreSQL."""
        encrypted_access = encrypt_oauth_token(access_token, self.settings)
        encrypted_refresh = (
            encrypt_oauth_token(refresh_token, self.settings) if refresh_token else None
        )
        expires_at = (
            datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
            if expires_in_seconds is not None
            else None
        )

        existing = db.scalar(
            select(OAuthCredential).where(
                OAuthCredential.user_id == user_id,
                OAuthCredential.provider == provider,
            )
        )
        if existing is None:
            cred = OAuthCredential(
                user_id=user_id,
                provider=provider,
                account_email=account_email,
                encrypted_access_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                scopes=scopes or [GSC_READONLY_SCOPE],
                expires_at=expires_at,
            )
            db.add(cred)
        else:
            cred = existing
            cred.encrypted_access_token = encrypted_access
            if encrypted_refresh is not None:
                cred.encrypted_refresh_token = encrypted_refresh
            if scopes is not None:
                cred.scopes = scopes
            if account_email is not None:
                cred.account_email = account_email
            cred.expires_at = expires_at

        db.commit()
        db.refresh(cred)
        return cred

    def get_valid_access_token(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        provider: str = "google_gsc",
    ) -> str:
        """Decrypt and return a valid access token, refreshing if near expiration."""
        cred = db.scalar(
            select(OAuthCredential).where(
                OAuthCredential.user_id == user_id,
                OAuthCredential.provider == provider,
            )
        )
        if cred is None:
            raise ConnectorAuthError(
                provider,
                f"No OAuth credentials found for provider '{provider}'",
                http_status=401,
            )

        now = datetime.now(UTC)
        if cred.expires_at is None or cred.expires_at > now + timedelta(seconds=60):
            return decrypt_oauth_token(cred.encrypted_access_token, self.settings)

        if not cred.encrypted_refresh_token:
            raise ConnectorAuthError(
                provider,
                "OAuth access token expired and no refresh token is stored",
                http_status=401,
            )

        refresh_plain = decrypt_oauth_token(cred.encrypted_refresh_token, self.settings)
        refreshed = self.refresh_access_token(refresh_plain)
        new_access = str(refreshed.get("access_token") or "")
        if not new_access:
            raise ConnectorAuthError(provider, "Google OAuth token refresh returned no token")

        expires_in = int(refreshed.get("expires_in") or 3600)
        self.save_encrypted_credential(
            db,
            user_id=user_id,
            provider=provider,
            access_token=new_access,
            refresh_token=refreshed.get("refresh_token"),
            expires_in_seconds=expires_in,
        )
        return new_access


class GscConnector(BaseDataProvider):
    """Google Search Console Search Analytics connector for verified owned properties.

    GSC only provides performance queries for properties verified by the authenticated
    Google account; it is NOT a market-wide keyword discovery tool.
    """

    provider_code = "gsc_api"
    supports_serp = False
    supports_keyword_ideas = False
    supports_keyword_metrics = True

    def __init__(
        self,
        *,
        access_token: str | None,
        site_url: str | None = None,
        http_client: ResilientHttpClient | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._access_token = (access_token or "").strip()
        self.site_url = (site_url or "").strip() or None
        self._http = http_client or ResilientHttpClient(
            provider_code=self.provider_code,
            base_url=GSC_API_BASE_URL,
            timeout_seconds=timeout_seconds,
            retry_config=RetryConfig(max_attempts=3, base_delay_seconds=0.5),
            rate_limiter=RateLimiter(requests_per_second=10.0),
        )

    def check_credentials(self) -> bool:
        return bool(self._access_token)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        self.require_credentials()
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def list_verified_properties(self) -> list[str]:
        """Return GSC property URIs that the authenticated user has verified access to."""
        response = self._http.get("/sites", headers=self._headers(), units=1.0)
        entries = response.json().get("siteEntry") or []
        verified: list[str] = []
        for entry in entries:
            if entry.get("permissionLevel") != "siteUnverifiedUser" and entry.get("siteUrl"):
                verified.append(str(entry["siteUrl"]))
        return verified

    def verify_property_access(self, site_url: str) -> None:
        """Ensure the requested GSC property is verified for the authenticated account."""
        verified = self.list_verified_properties()
        if site_url not in verified:
            raise ConnectorAuthError(
                self.provider_code,
                f"Authenticated account does not have verified access to GSC property '{site_url}'",
                http_status=403,
            )

    def query_search_analytics(
        self,
        site_url: str,
        *,
        start_date: date,
        end_date: date,
        country_code: str,
        language_code: str,
        row_limit: int = 25000,
        max_rows: int = 50000,
        verify_access: bool = True,
        query_contains: str | None = None,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Query GSC searchAnalytics with pagination via startRow."""
        start = time.perf_counter()
        cc = normalize_country_code(country_code)
        lc = normalize_language_code(language_code)
        page_size = max(1, min(row_limit, 25000))

        try:
            if verify_access:
                self.verify_property_access(site_url)

            encoded_site = quote(site_url, safe="")
            collected_at = datetime.now(UTC)
            records: list[KeywordIdeaRecord] = []
            start_row = 0

            while len(records) < max_rows:
                batch_limit = min(page_size, max_rows - len(records))
                body: dict[str, Any] = {
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["query"],
                    "rowLimit": batch_limit,
                    "startRow": start_row,
                }
                filters: list[dict[str, Any]] = []
                if cc in ISO2_TO_ISO3:
                    filters.append(
                        {
                            "dimension": "country",
                            "operator": "equals",
                            "expression": ISO2_TO_ISO3[cc],
                        }
                    )
                if query_contains:
                    filters.append(
                        {
                            "dimension": "query",
                            "operator": "contains",
                            "expression": query_contains,
                        }
                    )
                if filters:
                    body["dimensionFilterGroups"] = [{"filters": filters}]

                response = self._http.post(
                    f"/sites/{encoded_site}/searchAnalytics/query",
                    json=body,
                    headers=self._headers(),
                    units=1.0,
                )
                rows = response.json().get("rows") or []
                if not rows:
                    break

                for row in rows:
                    keys = row.get("keys") or []
                    if not keys or not str(keys[0]).strip():
                        continue
                    query_text = str(keys[0])
                    metrics = [
                        MetricRecord.available(
                            metric_type=MetricType.GSC_CLICKS,
                            source_code=self.provider_code,
                            numeric_value=float(row.get("clicks", 0.0)),
                            unit="clicks",
                            country_code=cc,
                            language_code=lc,
                            collected_at=collected_at,
                        ),
                        MetricRecord.available(
                            metric_type=MetricType.GSC_IMPRESSIONS,
                            source_code=self.provider_code,
                            numeric_value=float(row.get("impressions", 0.0)),
                            unit="impressions",
                            country_code=cc,
                            language_code=lc,
                            collected_at=collected_at,
                        ),
                        MetricRecord.available(
                            metric_type=MetricType.GSC_CTR,
                            source_code=self.provider_code,
                            numeric_value=float(row.get("ctr", 0.0)),
                            unit="ratio_0_1",
                            country_code=cc,
                            language_code=lc,
                            collected_at=collected_at,
                        ),
                        MetricRecord.available(
                            metric_type=MetricType.GSC_POSITION,
                            source_code=self.provider_code,
                            numeric_value=float(row.get("position", 0.0)),
                            unit="position",
                            country_code=cc,
                            language_code=lc,
                            collected_at=collected_at,
                        ),
                    ]
                    records.append(
                        KeywordIdeaRecord(
                            original_keyword=query_text,
                            keyword_type=KeywordCandidateType.SUPPORTING,
                            source_code=self.provider_code,
                            country_code=cc,
                            language_code=lc,
                            collected_at=collected_at,
                            metrics=metrics,
                            extra_metadata={
                                "site_url": site_url,
                                "start_date": start_date.isoformat(),
                                "end_date": end_date.isoformat(),
                            },
                        )
                    )

                if len(rows) < batch_limit:
                    break
                start_row += len(rows)

        except ConnectorError as exc:
            return ProviderResult(
                provider_code=self.provider_code,
                status="ERROR",
                items=[],
                errors=[exc.to_error_record(context={"site_url": site_url})],
                duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
            )

        return ProviderResult(
            provider_code=self.provider_code,
            status="OK",
            items=records,
            quota_used=self._http.quota.units_consumed,
            duration_ms=round((time.perf_counter() - start) * 1000.0, 2),
        )

    def get_keyword_ideas(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        raise ConnectorNotSupportedError(
            self.provider_code,
            "Google Search Console does not provide market-wide keyword ideas; use query_search_analytics for owned properties",
        )

    def get_keyword_metrics(
        self,
        keywords: list[str],
        *,
        country_code: str,
        language_code: str,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Fetch GSC performance metrics for owned property queries matching the target list."""
        if not self.site_url:
            raise ConnectorConfigError(
                self.provider_code,
                "site_url must be configured on GscConnector to query Search Analytics",
            )
        end = date.today() - timedelta(days=2)
        start = end - timedelta(days=90)
        full_result = self.query_search_analytics(
            self.site_url,
            start_date=start,
            end_date=end,
            country_code=country_code,
            language_code=language_code,
            verify_access=True,
        )
        if full_result.status == "ERROR":
            return full_result
        target_lower = {k.strip().lower() for k in keywords}
        filtered = [
            item
            for item in full_result.items
            if item.original_keyword.strip().lower() in target_lower
        ]
        return full_result.model_copy(update={"items": filtered})

    def get_related_keywords(
        self,
        seed_keyword: str,
        *,
        country_code: str,
        language_code: str,
        limit: int = 50,
    ) -> ProviderResult[KeywordIdeaRecord]:
        """Find existing owned-property GSC queries containing the seed keyword."""
        if not self.site_url:
            raise ConnectorConfigError(
                self.provider_code,
                "site_url must be configured on GscConnector to query related site queries",
            )
        end = date.today() - timedelta(days=2)
        start = end - timedelta(days=90)
        return self.query_search_analytics(
            self.site_url,
            start_date=start,
            end_date=end,
            country_code=country_code,
            language_code=language_code,
            max_rows=limit,
            query_contains=seed_keyword,
            verify_access=True,
        )
