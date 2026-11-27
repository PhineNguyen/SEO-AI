"""Unit tests for the free Google Autocomplete (Suggest) keyword discovery connector."""

import httpx
import respx
from app.connectors.google_suggest import GOOGLE_SUGGEST_URL, GoogleSuggestConnector


def test_google_suggest_connector_parses_and_deduplicates_without_fake_metrics() -> None:
    with respx.mock() as mock_router:
        mock_router.get(GOOGLE_SUGGEST_URL).mock(
            return_value=httpx.Response(
                200,
                json=[
                    "phan mem crm",
                    [
                        "phan mem crm tot nhat",
                        "phan mem crm mien phi",
                        "phan mem crm tot nhat",
                    ],
                ],
            )
        )
        with httpx.Client() as client:
            connector = GoogleSuggestConnector(http_client=client)
            res = connector.get_keyword_ideas(
                "phan mem crm", country_code="VN", language_code="vi", expand_modifiers=False
            )
            assert res.status == "OK"
            assert len(res.items) == 2
            assert all(item.metrics == [] for item in res.items)
