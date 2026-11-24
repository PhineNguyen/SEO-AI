"""Evidence-based Content Brief Generation & Review 3 Versioning Service (TASK-025..027)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.brief import (
    BriefFaq,
    BriefKeyword,
    BriefReview,
    BriefSection,
    ContentBrief,
)
from app.models.clustering import KeywordCluster
from app.models.project import Project
from app.models.research import Keyword, ResearchRun
from app.models.serp import CompetitorHeading, CompetitorPage, SerpResult, SerpSnapshot
from app.schemas.brief import (
    BriefEditRequest,
    BriefFaqInput,
    BriefSectionInput,
    ContentBriefDraft,
)
from app.services.brief_validator import validate_brief_draft

BriefGeneratorFn = Callable[[dict[str, Any], list[str]], ContentBriefDraft]


def _brief_snapshot(brief: ContentBrief) -> dict[str, Any]:
    return {
        "brief_id": str(brief.id),
        "version": brief.version,
        "origin": brief.origin,
        "status": brief.status,
        "suggested_seo_title": brief.suggested_seo_title,
        "meta_description": brief.meta_description,
        "h1": brief.h1,
        "content_angle": brief.content_angle,
        "section_count": len(brief.sections),
        "faq_count": len(brief.faqs),
    }


def default_evidence_brief_generator(
    context: dict[str, Any], previous_errors: list[str]
) -> ContentBriefDraft:
    """Deterministic evidence-backed Content Brief generator grounded strictly in DB SERP data."""
    primary_kw: str = context["primary_keyword"]
    secondary_kws: list[str] = context["secondary_keywords"]
    intent: str = context["search_intent"] or "Informational"
    serp_items: list[dict[str, Any]] = context["serp_items"]
    competitor_headings: list[str] = context["competitor_headings"]
    audience: str = context["target_audience"] or "Target readers searching for practical solutions"

    # Build H2/H3 outline strictly grounded in competitor headings & cluster keywords
    sections: list[BriefSectionInput] = [
        BriefSectionInput(
            heading_level=2,
            heading_text=f"Overview of {primary_kw}",
            section_order=1,
            key_points=[
                f"Directly address the {intent} search intent behind '{primary_kw}'.",
                "Summarize key decision criteria in the opening paragraph.",
            ],
            target_keywords=[primary_kw],
        )
    ]

    order = 2
    for heading in competitor_headings[:4]:
        sections.append(
            BriefSectionInput(
                heading_level=2,
                heading_text=heading[:250],
                section_order=order,
                key_points=[
                    f"Cover topic observed in top-ranking pages: {heading[:120]}.",
                    "Add concrete examples or comparisons rather than generic filler.",
                ],
                target_keywords=[secondary_kws[(order - 2) % len(secondary_kws)]]
                if secondary_kws
                else [primary_kw],
            )
        )
        order += 1

    if len(sections) == 1:
        for sec_kw in secondary_kws[:3]:
            sections.append(
                BriefSectionInput(
                    heading_level=2,
                    heading_text=f"Key Insights on {sec_kw}",
                    section_order=order,
                    key_points=[f"Explain '{sec_kw}' with actionable takeaways."],
                    target_keywords=[sec_kw],
                )
            )
            order += 1

    faqs = [
        BriefFaqInput(
            question=f"What should readers know first about {primary_kw}?",
            answer_guidance=f"Provide a clear, concise answer aligned with {intent} intent.",
            source_evidence=serp_items[0]["url"] if serp_items else "cluster_keywords",
            display_order=1,
        )
    ]

    competitor_insights = [
        {
            "position": item["position"],
            "url": item["url"],
            "domain": item["domain"],
            "title": item["title"],
        }
        for item in serp_items[:5]
    ]
    evidence_refs = [
        {"type": "serp_result", "position": item["position"], "url": item["url"]}
        for item in serp_items[:5]
    ]

    return ContentBriefDraft(
        search_intent=intent,
        target_audience=audience,
        content_objective=f"Satisfy {intent} search intent for '{primary_kw}' with evidence-backed depth.",
        content_angle=f"Practical, structured guide addressing '{primary_kw}' and related cluster subtopics.",
        suggested_seo_title=f"{primary_kw.title()} — Complete Evidence-Based Guide",
        meta_description=f"Explore {primary_kw} with clear criteria, comparisons, and actionable steps.",
        h1=f"{primary_kw.title()}: Essential Guide",
        competitor_insights=competitor_insights,
        important_topics=[s.heading_text for s in sections],
        content_recommendations=[
            "Answer the core search intent early and organize sections logically by subtopic.",
            "Include original examples, structured tables, or checklists where helpful to readers.",
            "Avoid artificial keyword stuffing; weave secondary keywords naturally into headings and body copy.",
        ],
        keyword_coverage={
            "primary_keyword": primary_kw,
            "secondary_keywords": secondary_kws,
            "total_cluster_keywords": 1 + len(secondary_kws),
        },
        evidence_refs=evidence_refs,
        sections=sections,
        faqs=faqs,
        model_version="evidence-brief-v1",
        prompt_version="brief-prompt-v1",
    )


class ContentBriefService:
    """Generates, validates (bounded retries), and manages versioned Review 3 Content Briefs."""

    def __init__(
        self,
        db: Session,
        generator: BriefGeneratorFn | None = None,
        max_validation_retries: int = 2,
    ) -> None:
        self._db = db
        self._generator = generator or default_evidence_brief_generator
        self._max_retries = max_validation_retries

    def _get_owned_run(self, research_run_id: UUID, owner_id: UUID) -> ResearchRun:
        run = self._db.scalar(
            select(ResearchRun)
            .join(Project, ResearchRun.project_id == Project.id)
            .where(ResearchRun.id == research_run_id, Project.owner_id == owner_id)
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found"
            )
        return run

    def _get_owned_brief(self, brief_id: UUID, owner_id: UUID) -> ContentBrief:
        brief = self._db.scalar(
            select(ContentBrief)
            .where(ContentBrief.id == brief_id)
            .options(
                selectinload(ContentBrief.brief_keywords),
                selectinload(ContentBrief.sections),
                selectinload(ContentBrief.faqs),
                selectinload(ContentBrief.reviews),
            )
        )
        if not brief:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Content brief not found"
            )
        self._get_owned_run(brief.research_run_id, owner_id)
        return brief

    def _gather_cluster_context(
        self, run: ResearchRun, cluster: KeywordCluster
    ) -> tuple[Keyword, list[Keyword], dict[str, Any]]:
        project = self._db.scalar(select(Project).where(Project.id == run.project_id))
        member_kw_ids = [m.keyword_id for m in cluster.members]
        kw_map = {
            kw.id: kw
            for kw in self._db.scalars(select(Keyword).where(Keyword.id.in_(member_kw_ids))).all()
        }
        primary_kw = (
            kw_map.get(cluster.primary_keyword_id)
            if cluster.primary_keyword_id
            else next(iter(kw_map.values()), None)
        )
        if primary_kw is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cluster has no keywords to generate a brief",
            )
        secondary_kws = [kw for kid, kw in kw_map.items() if kid != primary_kw.id]

        # Collect SERP results & competitor headings for primary keyword
        latest_snap = self._db.scalar(
            select(SerpSnapshot)
            .where(
                SerpSnapshot.research_run_id == run.id,
                SerpSnapshot.keyword_id == primary_kw.id,
            )
            .order_by(SerpSnapshot.collected_at.desc())
        )
        serp_items: list[dict[str, Any]] = []
        competitor_headings: list[str] = []
        if latest_snap:
            results = list(
                self._db.scalars(
                    select(SerpResult)
                    .where(SerpResult.serp_snapshot_id == latest_snap.id)
                    .order_by(SerpResult.position.asc())
                ).all()
            )
            page_ids: list[UUID] = []
            for r in results:
                serp_items.append(
                    {
                        "position": r.position,
                        "url": r.normalized_url,
                        "domain": r.domain,
                        "title": r.title,
                    }
                )
                if r.competitor_page_id:
                    page_ids.append(r.competitor_page_id)
            if page_ids:
                headings = list(
                    self._db.scalars(
                        select(CompetitorHeading)
                        .join(CompetitorPage, CompetitorHeading.competitor_page_id == CompetitorPage.id)
                        .where(
                            CompetitorHeading.competitor_page_id.in_(page_ids),
                            CompetitorHeading.level.in_((2, 3)),
                        )
                        .order_by(CompetitorHeading.position_order.asc())
                    ).all()
                )
                competitor_headings = [h.heading_text for h in headings]

        context = {
            "primary_keyword": primary_kw.original_keyword,
            "secondary_keywords": [k.original_keyword for k in secondary_kws],
            "all_cluster_keywords": {k.original_keyword for k in kw_map.values()},
            "search_intent": cluster.cluster_intent or "Informational",
            "target_audience": project.target_audience if project else "",
            "serp_items": serp_items,
            "allowed_serp_urls": {item["url"] for item in serp_items},
            "competitor_headings": competitor_headings,
        }
        return primary_kw, secondary_kws, context

    def _generate_validated_draft(
        self, context: dict[str, Any]
    ) -> ContentBriefDraft:
        last_errors: list[str] = []
        for _attempt in range(self._max_retries + 1):
            draft = self._generator(context, last_errors)
            validation = validate_brief_draft(
                draft,
                primary_keyword=context["primary_keyword"],
                allowed_cluster_keywords=context["all_cluster_keywords"],
                allowed_serp_urls=context["allowed_serp_urls"],
            )
            if validation.is_valid:
                return draft
            last_errors = validation.errors
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Content brief failed anti-hallucination validation after {self._max_retries + 1} attempts: {last_errors}",
        )

    def _persist_brief_version(
        self,
        *,
        run_id: UUID,
        cluster_id: UUID,
        primary_kw: Keyword,
        secondary_kws: list[Keyword],
        draft: ContentBriefDraft,
        origin: str,
        brief_status: str,
    ) -> ContentBrief:
        existing_versions = list(
            self._db.scalars(
                select(ContentBrief)
                .where(ContentBrief.cluster_id == cluster_id)
                .order_by(ContentBrief.version.desc())
            ).all()
        )
        next_version = (existing_versions[0].version + 1) if existing_versions else 1
        for prev in existing_versions:
            if prev.is_current:
                prev.is_current = False
        self._db.flush()

        brief = ContentBrief(
            research_run_id=run_id,
            cluster_id=cluster_id,
            primary_keyword_id=primary_kw.id,
            version=next_version,
            is_current=True,
            origin=origin,
            status=brief_status,
            search_intent=draft.search_intent,
            target_audience=draft.target_audience,
            content_objective=draft.content_objective,
            content_angle=draft.content_angle,
            suggested_seo_title=draft.suggested_seo_title,
            meta_description=draft.meta_description,
            h1=draft.h1,
            competitor_insights=draft.competitor_insights,
            important_topics=draft.important_topics,
            content_recommendations=draft.content_recommendations,
            keyword_coverage=draft.keyword_coverage,
            evidence_refs=draft.evidence_refs,
            model_version=draft.model_version,
            prompt_version=draft.prompt_version,
        )
        self._db.add(brief)
        self._db.flush()

        self._db.add(
            BriefKeyword(
                content_brief_id=brief.id,
                keyword_id=primary_kw.id,
                usage_role="PRIMARY",
                placement_hint="Title, H1, Intro",
            )
        )
        for sec in secondary_kws:
            self._db.add(
                BriefKeyword(
                    content_brief_id=brief.id,
                    keyword_id=sec.id,
                    usage_role="SECONDARY",
                    placement_hint="H2/H3 & Body",
                )
            )
        for idx, sec_in in enumerate(draft.sections, start=1):
            self._db.add(
                BriefSection(
                    content_brief_id=brief.id,
                    heading_level=sec_in.heading_level,
                    heading_text=sec_in.heading_text,
                    section_order=sec_in.section_order or idx,
                    key_points=sec_in.key_points,
                    target_keywords=sec_in.target_keywords,
                )
            )
        for idx, faq_in in enumerate(draft.faqs, start=1):
            self._db.add(
                BriefFaq(
                    content_brief_id=brief.id,
                    question=faq_in.question,
                    answer_guidance=faq_in.answer_guidance,
                    source_evidence=faq_in.source_evidence,
                    display_order=faq_in.display_order or idx,
                )
            )
        self._db.flush()
        return brief

    def generate_briefs_for_run(
        self, research_run_id: UUID, owner_id: UUID
    ) -> list[ContentBrief]:
        run = self._get_owned_run(research_run_id, owner_id)
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
        created_ids: list[UUID] = []
        for cluster in clusters:
            if not cluster.members:
                continue
            primary_kw, secondary_kws, context = self._gather_cluster_context(run, cluster)
            draft = self._generate_validated_draft(context)
            brief = self._persist_brief_version(
                run_id=run.id,
                cluster_id=cluster.id,
                primary_kw=primary_kw,
                secondary_kws=secondary_kws,
                draft=draft,
                origin="AI",
                brief_status="PENDING_REVIEW",
            )
            created_ids.append(brief.id)
        self._db.commit()
        return [self._get_owned_brief(bid, owner_id) for bid in created_ids]

    def list_briefs(
        self, research_run_id: UUID, owner_id: UUID, *, current_only: bool = True
    ) -> list[ContentBrief]:
        self._get_owned_run(research_run_id, owner_id)
        stmt = (
            select(ContentBrief)
            .where(ContentBrief.research_run_id == research_run_id)
            .options(
                selectinload(ContentBrief.brief_keywords),
                selectinload(ContentBrief.sections),
                selectinload(ContentBrief.faqs),
            )
            .order_by(ContentBrief.created_at.asc())
        )
        if current_only:
            stmt = stmt.where(ContentBrief.is_current.is_(True))
        return list(self._db.scalars(stmt).all())

    def get_brief(self, brief_id: UUID, owner_id: UUID) -> ContentBrief:
        return self._get_owned_brief(brief_id, owner_id)

    def edit_brief_versioned(
        self, brief_id: UUID, reviewer_id: UUID, payload: BriefEditRequest
    ) -> ContentBrief:
        """Create a new HUMAN version while preserving the original AI baseline row intact."""
        current = self._get_owned_brief(brief_id, reviewer_id)
        before = _brief_snapshot(current)

        kw_ids = [bk.keyword_id for bk in current.brief_keywords]
        kw_map = {
            kw.id: kw
            for kw in self._db.scalars(select(Keyword).where(Keyword.id.in_(kw_ids))).all()
        }
        primary_kw = kw_map[current.primary_keyword_id]
        secondary_kws = [kw for kid, kw in kw_map.items() if kid != primary_kw.id]

        sections_in = (
            payload.sections
            if payload.sections is not None
            else [
                BriefSectionInput(
                    heading_level=s.heading_level,
                    heading_text=s.heading_text,
                    section_order=s.section_order,
                    key_points=list(s.key_points),
                    target_keywords=list(s.target_keywords),
                )
                for s in current.sections
            ]
        )
        faqs_in = (
            payload.faqs
            if payload.faqs is not None
            else [
                BriefFaqInput(
                    question=f.question,
                    answer_guidance=f.answer_guidance,
                    source_evidence=f.source_evidence,
                    display_order=f.display_order,
                )
                for f in current.faqs
            ]
        )

        draft = ContentBriefDraft(
            search_intent=current.search_intent,
            target_audience=payload.target_audience
            if payload.target_audience is not None
            else current.target_audience,
            content_objective=payload.content_objective
            if payload.content_objective is not None
            else current.content_objective,
            content_angle=payload.content_angle
            if payload.content_angle is not None
            else current.content_angle,
            suggested_seo_title=payload.suggested_seo_title
            if payload.suggested_seo_title is not None
            else current.suggested_seo_title,
            meta_description=payload.meta_description
            if payload.meta_description is not None
            else current.meta_description,
            h1=payload.h1 if payload.h1 is not None else current.h1,
            competitor_insights=list(current.competitor_insights),
            important_topics=list(current.important_topics),
            content_recommendations=list(current.content_recommendations),
            keyword_coverage=dict(current.keyword_coverage),
            evidence_refs=list(current.evidence_refs),
            sections=sections_in,
            faqs=faqs_in,
            model_version=current.model_version,
            prompt_version=current.prompt_version,
        )

        new_brief = self._persist_brief_version(
            run_id=current.research_run_id,
            cluster_id=current.cluster_id,
            primary_kw=primary_kw,
            secondary_kws=secondary_kws,
            draft=draft,
            origin="HUMAN",
            brief_status="PENDING_REVIEW",
        )
        self._db.add(
            BriefReview(
                content_brief_id=new_brief.id,
                action="EDIT",
                before_snapshot=before,
                after_snapshot=_brief_snapshot(new_brief),
                reviewer_id=reviewer_id,
                feedback_notes=payload.feedback_notes,
            )
        )
        self._db.commit()
        return self._get_owned_brief(new_brief.id, reviewer_id)

    def approve_brief(
        self, brief_id: UUID, reviewer_id: UUID, feedback_notes: str | None = None
    ) -> ContentBrief:
        brief = self._get_owned_brief(brief_id, reviewer_id)
        before = _brief_snapshot(brief)
        brief.status = "APPROVED"
        self._db.add(
            BriefReview(
                content_brief_id=brief.id,
                action="APPROVE",
                before_snapshot=before,
                after_snapshot=_brief_snapshot(brief),
                reviewer_id=reviewer_id,
                feedback_notes=feedback_notes,
            )
        )
        self._db.commit()
        return self._get_owned_brief(brief.id, reviewer_id)

    def regenerate_brief(
        self, brief_id: UUID, reviewer_id: UUID, feedback_notes: str | None = None
    ) -> ContentBrief:
        current = self._get_owned_brief(brief_id, reviewer_id)
        before = _brief_snapshot(current)
        run = self._get_owned_run(current.research_run_id, reviewer_id)
        cluster = self._db.scalar(
            select(KeywordCluster)
            .where(KeywordCluster.id == current.cluster_id)
            .options(selectinload(KeywordCluster.members))
        )
        assert cluster is not None
        primary_kw, secondary_kws, context = self._gather_cluster_context(run, cluster)
        draft = self._generate_validated_draft(context)
        new_brief = self._persist_brief_version(
            run_id=run.id,
            cluster_id=cluster.id,
            primary_kw=primary_kw,
            secondary_kws=secondary_kws,
            draft=draft,
            origin="AI",
            brief_status="PENDING_REVIEW",
        )
        self._db.add(
            BriefReview(
                content_brief_id=new_brief.id,
                action="REGENERATE",
                before_snapshot=before,
                after_snapshot=_brief_snapshot(new_brief),
                reviewer_id=reviewer_id,
                feedback_notes=feedback_notes,
            )
        )
        self._db.commit()
        return self._get_owned_brief(new_brief.id, reviewer_id)
