"""Excel (.xlsx 7-sheet) & Google Sheets OAuth Export Services (TASK-028, TASK-029)."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.brief import ContentBrief, ExportJob
from app.models.clustering import KeywordCluster
from app.models.data_source import DataSource
from app.models.oauth_credential import OAuthCredential
from app.models.project import Project
from app.models.research import Keyword, KeywordMetric, ResearchRun, SourceImport
from app.models.serp import KeywordIntent, SerpSnapshot
from app.utils.security import TokenEncryptor

EXPORT_SHEET_NAMES: tuple[str, ...] = (
    "Overview",
    "All Keywords",
    "SERP Analysis",
    "Search Intent",
    "Keyword Clusters",
    "Content Brief",
    "Data Sources",
)

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _style_header_row(ws: Any, headers: list[str]) -> None:
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


class ExportService:
    """Exports a research run to a styled 7-sheet Excel workbook or Google Sheets."""

    def __init__(self, db: Session, export_dir: Path | None = None) -> None:
        self._db = db
        self._export_dir = export_dir or Path("exports")

    def _get_owned_run(self, research_run_id: UUID, owner_id: UUID) -> tuple[ResearchRun, Project]:
        row = self._db.execute(
            select(ResearchRun, Project)
            .join(Project, ResearchRun.project_id == Project.id)
            .where(ResearchRun.id == research_run_id, Project.owner_id == owner_id)
        ).first()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found"
            )
        return row[0], row[1]

    def _collect_export_datasets(
        self, run: ResearchRun, project: Project
    ) -> dict[str, tuple[list[str], list[list[Any]]]]:
        keywords = list(
            self._db.scalars(
                select(Keyword)
                .where(Keyword.research_run_id == run.id)
                .order_by(Keyword.priority_score.desc().nulls_last(), Keyword.created_at.asc())
            ).all()
        )
        kw_by_id = {k.id: k for k in keywords}
        kw_ids = list(kw_by_id.keys())

        metrics = (
            list(
                self._db.scalars(
                    select(KeywordMetric)
                    .where(KeywordMetric.keyword_id.in_(kw_ids))
                    .order_by(KeywordMetric.collected_at.desc())
                ).all()
            )
            if kw_ids
            else []
        )
        metric_map: dict[UUID, dict[str, Any]] = {}
        for m in metrics:
            b = metric_map.setdefault(m.keyword_id, {})
            if m.metric_type not in b:
                b[m.metric_type] = (
                    float(m.numeric_value)
                    if m.data_status == "AVAILABLE" and m.numeric_value is not None
                    else m.data_status
                )

        intents = (
            list(
                self._db.scalars(
                    select(KeywordIntent).where(
                        KeywordIntent.keyword_id.in_(kw_ids),
                        KeywordIntent.is_current.is_(True),
                    )
                ).all()
            )
            if kw_ids
            else []
        )
        intent_by_kw = {i.keyword_id: i for i in intents}

        snapshots = list(
            self._db.scalars(
                select(SerpSnapshot)
                .where(SerpSnapshot.research_run_id == run.id)
                .options(selectinload(SerpSnapshot.results))
                .order_by(SerpSnapshot.collected_at.desc())
            ).all()
        )
        clusters = list(
            self._db.scalars(
                select(KeywordCluster)
                .where(
                    KeywordCluster.research_run_id == run.id,
                    KeywordCluster.status.in_(("ACTIVE", "APPROVED")),
                )
                .options(selectinload(KeywordCluster.members))
                .order_by(KeywordCluster.created_at.asc())
            ).all()
        )
        briefs = list(
            self._db.scalars(
                select(ContentBrief)
                .where(
                    ContentBrief.research_run_id == run.id,
                    ContentBrief.is_current.is_(True),
                )
                .options(selectinload(ContentBrief.sections), selectinload(ContentBrief.faqs))
                .order_by(ContentBrief.created_at.asc())
            ).all()
        )
        imports = list(
            self._db.scalars(
                select(SourceImport).where(SourceImport.research_run_id == run.id)
            ).all()
        )
        sources = list(self._db.scalars(select(DataSource).order_by(DataSource.code.asc())).all())
        source_by_id = {s.id: s for s in sources}

        overview_rows = [
            ["Project Name", project.name],
            ["Niche", project.niche],
            ["Target Locale", f"{run.country_code} / {run.language_code} ({run.device})"],
            ["Research Run", run.name],
            ["Total Keywords", len(keywords)],
            ["SERP Snapshots", len(snapshots)],
            ["Active/Approved Clusters", len(clusters)],
            ["Current Content Briefs", len(briefs)],
            ["Exported At (UTC)", datetime.now(UTC).isoformat()],
        ]

        kw_rows = []
        for kw in keywords:
            mm = metric_map.get(kw.id, {})
            intent = intent_by_kw.get(kw.id)
            kw_rows.append(
                [
                    kw.original_keyword,
                    kw.normalized_keyword,
                    kw.cleaning_status,
                    kw.review_status,
                    mm.get("SEARCH_VOLUME", "NOT_COLLECTED"),
                    mm.get("KEYWORD_DIFFICULTY", "NOT_COLLECTED"),
                    mm.get("CPC", "NOT_COLLECTED"),
                    intent.primary_intent if intent else "NOT_CLASSIFIED",
                    float(kw.priority_score) if kw.priority_score is not None else "",
                    kw.priority_tier or "",
                    kw.priority_reasoning or "",
                ]
            )

        serp_rows = []
        for snap in snapshots:
            kw_text = kw_by_id[snap.keyword_id].original_keyword if snap.keyword_id in kw_by_id else ""
            for res in sorted(snap.results, key=lambda r: r.position):
                serp_rows.append(
                    [
                        kw_text,
                        snap.provider_code,
                        snap.country_code,
                        snap.device,
                        res.position,
                        res.domain,
                        res.title,
                        res.url,
                    ]
                )

        intent_rows = [
            [
                kw_by_id[i.keyword_id].original_keyword if i.keyword_id in kw_by_id else "",
                i.primary_intent,
                i.secondary_intent or "",
                float(i.confidence),
                i.origin,
                i.model_version,
                i.reasoning,
            ]
            for i in intents
        ]

        cluster_rows = []
        for c in clusters:
            primary_text = (
                kw_by_id[c.primary_keyword_id].original_keyword
                if c.primary_keyword_id and c.primary_keyword_id in kw_by_id
                else ""
            )
            member_texts = [
                kw_by_id[m.keyword_id].original_keyword
                for m in c.members
                if m.keyword_id in kw_by_id
            ]
            cluster_rows.append(
                [
                    c.cluster_name,
                    primary_text,
                    c.cluster_intent or "",
                    c.status,
                    c.origin,
                    len(c.members),
                    ", ".join(member_texts),
                    c.clustering_reasoning,
                ]
            )

        brief_rows = []
        for b in briefs:
            pk_text = (
                kw_by_id[b.primary_keyword_id].original_keyword
                if b.primary_keyword_id in kw_by_id
                else ""
            )
            outline = " | ".join(
                f"H{s.heading_level}: {s.heading_text}" for s in b.sections
            )
            faq_text = " | ".join(f.question for f in b.faqs)
            brief_rows.append(
                [
                    pk_text,
                    b.version,
                    b.origin,
                    b.status,
                    b.search_intent,
                    b.suggested_seo_title,
                    b.meta_description,
                    b.h1,
                    b.content_angle,
                    outline,
                    faq_text,
                ]
            )

        ds_rows = [
            [s.code, s.name, s.source_type, "ACTIVE" if s.is_active else "INACTIVE", ""]
            for s in sources
        ]
        for imp in imports:
            src = source_by_id.get(imp.source_id)
            ds_rows.append(
                [
                    src.code if src else "import",
                    imp.file_name,
                    "FILE_IMPORT",
                    imp.status,
                    f"imported={imp.imported_rows}, errors={imp.error_rows}, sha256={imp.file_hash_sha256[:12]}",
                ]
            )

        return {
            "Overview": (["Field", "Value"], overview_rows),
            "All Keywords": (
                [
                    "Original Keyword",
                    "Normalized Keyword",
                    "Cleaning Status",
                    "Review Status",
                    "Search Volume",
                    "KD",
                    "CPC",
                    "Search Intent",
                    "Priority Score",
                    "Priority Tier",
                    "Priority Reasoning",
                ],
                kw_rows,
            ),
            "SERP Analysis": (
                ["Keyword", "Provider", "Country", "Device", "Position", "Domain", "Title", "URL"],
                serp_rows,
            ),
            "Search Intent": (
                ["Keyword", "Primary Intent", "Secondary Intent", "Confidence", "Origin", "Model", "Reasoning"],
                intent_rows,
            ),
            "Keyword Clusters": (
                ["Cluster Name", "Primary Keyword", "Intent", "Status", "Origin", "Member Count", "Keywords", "Reasoning"],
                cluster_rows,
            ),
            "Content Brief": (
                [
                    "Primary Keyword",
                    "Version",
                    "Origin",
                    "Status",
                    "Intent",
                    "SEO Title",
                    "Meta Description",
                    "H1",
                    "Content Angle",
                    "H2/H3 Outline",
                    "FAQs",
                ],
                brief_rows,
            ),
            "Data Sources": (
                ["Source Code", "Name / File", "Type", "Status", "Provenance Details"],
                ds_rows,
            ),
        }

    def export_excel(
        self, research_run_id: UUID, owner_id: UUID
    ) -> tuple[ExportJob, bytes]:
        """Generate a 7-sheet styled .xlsx workbook and record an ExportJob."""
        run, project = self._get_owned_run(research_run_id, owner_id)
        datasets = self._collect_export_datasets(run, project)

        wb = Workbook()
        first = True
        for sheet_name in EXPORT_SHEET_NAMES:
            ws = wb.active if first else wb.create_sheet(title=sheet_name)
            ws.title = sheet_name
            first = False
            headers, rows = datasets[sheet_name]
            _style_header_row(ws, headers)
            for row in rows:
                ws.append(row)
            # Add clickable hyperlinks on SERP Analysis URL column
            if sheet_name == "SERP Analysis":
                for row_idx in range(2, ws.max_row + 1):
                    cell = ws.cell(row=row_idx, column=8)
                    if cell.value and str(cell.value).startswith("http"):
                        cell.hyperlink = str(cell.value)
                        cell.style = "Hyperlink"

        buffer = BytesIO()
        wb.save(buffer)
        xlsx_bytes = buffer.getvalue()

        self._export_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._export_dir / f"research_run_{run.id}.xlsx"
        out_path.write_bytes(xlsx_bytes)

        job = ExportJob(
            research_run_id=run.id,
            export_type="EXCEL",
            status="COMPLETED",
            file_path=str(out_path),
            created_by=owner_id,
            completed_at=datetime.now(UTC),
        )
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job, xlsx_bytes

    def export_google_sheets(
        self,
        research_run_id: UUID,
        owner_id: UUID,
        *,
        http_client: httpx.Client | None = None,
    ) -> ExportJob:
        """Export all 7 worksheets to Google Sheets using encrypted OAuth tokens (TASK-029)."""
        run, project = self._get_owned_run(research_run_id, owner_id)
        cred = self._db.scalar(
            select(OAuthCredential).where(
                OAuthCredential.user_id == owner_id,
                OAuthCredential.provider == "google_sheets",
            )
        )
        if not cred:
            job = ExportJob(
                research_run_id=run.id,
                export_type="GOOGLE_SHEETS",
                status="FAILED",
                error_message="Google Sheets OAuth credential not connected for this user.",
                created_by=owner_id,
                completed_at=datetime.now(UTC),
            )
            self._db.add(job)
            self._db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Google Sheets OAuth permission is not connected for this account.",
            )

        settings = get_settings()
        encryptor = TokenEncryptor(settings.OAUTH_TOKEN_ENCRYPTION_KEY.get_secret_value())
        access_token = encryptor.decrypt(cred.encrypted_access_token)
        datasets = self._collect_export_datasets(run, project)

        client = http_client or httpx.Client(timeout=20.0)
        close_after = http_client is None
        try:
            auth_headers = {"Authorization": f"Bearer {access_token}"}
            create_payload = {
                "properties": {"title": f"{project.name} - {run.name}"},
                "sheets": [{"properties": {"title": name}} for name in EXPORT_SHEET_NAMES],
            }
            resp = client.post(
                "https://sheets.googleapis.com/v4/spreadsheets",
                json=create_payload,
                headers=auth_headers,
            )
            resp.raise_for_status()
            created = resp.json()
            spreadsheet_id = created["spreadsheetId"]
            spreadsheet_url = created.get(
                "spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
            )

            value_ranges = []
            for sheet_name in EXPORT_SHEET_NAMES:
                headers, rows = datasets[sheet_name]
                value_ranges.append(
                    {
                        "range": f"'{sheet_name}'!A1",
                        "values": [headers, *[[str(c) for c in r] for r in rows]],
                    }
                )
            batch_resp = client.post(
                f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate",
                json={"valueInputOption": "USER_ENTERED", "data": value_ranges},
                headers=auth_headers,
            )
            batch_resp.raise_for_status()

            job = ExportJob(
                research_run_id=run.id,
                export_type="GOOGLE_SHEETS",
                status="COMPLETED",
                google_spreadsheet_id=spreadsheet_id,
                google_spreadsheet_url=spreadsheet_url,
                created_by=owner_id,
                completed_at=datetime.now(UTC),
            )
            self._db.add(job)
            self._db.commit()
            self._db.refresh(job)
            return job
        except Exception as exc:
            job = ExportJob(
                research_run_id=run.id,
                export_type="GOOGLE_SHEETS",
                status="FAILED",
                error_message=str(exc),
                created_by=owner_id,
                completed_at=datetime.now(UTC),
            )
            self._db.add(job)
            self._db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Google Sheets export failed: {exc}",
            ) from exc
        finally:
            if close_after:
                client.close()

    def list_export_jobs(self, research_run_id: UUID, owner_id: UUID) -> list[ExportJob]:
        self._get_owned_run(research_run_id, owner_id)
        return list(
            self._db.scalars(
                select(ExportJob)
                .where(ExportJob.research_run_id == research_run_id)
                .order_by(ExportJob.created_at.desc())
            ).all()
        )
