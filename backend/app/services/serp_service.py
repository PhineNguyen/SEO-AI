"""Application service for SERP collection and SSRF-safe competitor heading extraction."""


from sqlalchemy.orm import Session

from app.connectors.base import BaseDataProvider
from app.connectors.exceptions import ConnectorError
from app.connectors.safe_fetcher import SafeCompetitorFetcher
from app.models.research import Keyword, ResearchRun
from app.models.serp import CompetitorPage, SerpSnapshot
from app.repositories.research_repository import ResearchRepository
from app.repositories.serp_repository import SerpRepository
from app.schemas.provenance import DeviceType, ProviderErrorRecord


class SerpService:
    """Collects append-only SERP snapshots and extracts competitor page heading outlines."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.research_repo = ResearchRepository(db)
        self.serp_repo = SerpRepository(db)

    def collect_serp_for_keywords(
        self,
        run: ResearchRun,
        keywords: list[Keyword],
        *,
        provider: BaseDataProvider,
        depth: int = 10,
    ) -> tuple[list[SerpSnapshot], list[ProviderErrorRecord]]:
        """Collect SERP Top-N snapshots for keywords with per-keyword fault isolation."""
        snapshots: list[SerpSnapshot] = []
        errors: list[ProviderErrorRecord] = []
        device: DeviceType = "mobile" if run.device == "mobile" else "desktop"

        for kw in keywords:
            try:
                result = provider.get_serp_results(
                    kw.normalized_keyword,
                    country_code=run.country_code,
                    language_code=run.language_code,
                    device=device,
                    depth=depth,
                )
            except ConnectorError as exc:
                errors.append(exc.to_error_record(context={"keyword": kw.normalized_keyword}))
                continue

            if result.errors:
                errors.extend(result.errors)
            for snap_record in result.items:
                saved = self.serp_repo.save_serp_snapshot(
                    research_run_id=run.id,
                    keyword_id=kw.id,
                    record=snap_record,
                )
                snapshots.append(saved)

        self.db.commit()
        return snapshots, errors

    def fetch_headings_for_snapshot(
        self,
        snapshot: SerpSnapshot,
        *,
        fetcher: SafeCompetitorFetcher,
        max_pages: int = 10,
    ) -> list[CompetitorPage]:
        """Fetch and persist H1-H3 headings for pending competitor pages in a SERP snapshot."""
        updated_pages: list[CompetitorPage] = []
        for result in sorted(snapshot.results, key=lambda r: r.position)[:max_pages]:
            page = result.competitor_page
            if page is None or page.fetch_status == "FETCHED":
                continue
            fetch_res = fetcher.fetch_and_parse(page.url)
            self.serp_repo.save_competitor_fetch(page, fetch_res)
            updated_pages.append(page)

        self.db.commit()
        return updated_pages
