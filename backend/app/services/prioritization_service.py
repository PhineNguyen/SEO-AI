"""Configurable Keyword Prioritization Service (TASK-021)."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectSettings
from app.models.research import Keyword, KeywordMetric, ResearchRun
from app.models.serp import KeywordIntent

DEFAULT_PRIORITIZATION_WEIGHTS: dict[str, float] = {
    "search_volume": 0.35,
    "keyword_difficulty": 0.25,
    "intent_value": 0.25,
    "cpc": 0.15,
}

INTENT_BUSINESS_SCORES: dict[str, float] = {
    "Transactional": 100.0,
    "Commercial": 85.0,
    "Informational": 55.0,
    "Navigational": 30.0,
}


def compute_priority_for_keyword(
    *,
    search_volume: float | None,
    keyword_difficulty: float | None,
    cpc: float | None,
    primary_intent: str | None,
    weights: dict[str, float] | None = None,
) -> tuple[Decimal, str, str]:
    """Compute a 0-100 priority score with NULL-safe weight renormalization and explanation."""
    w = weights or DEFAULT_PRIORITIZATION_WEIGHTS
    signals: dict[str, tuple[float | None, str]] = {}

    if search_volume is not None:
        # Log scale: 0 -> 0, 100 -> 40, 1000 -> 60, 10000 -> 80, 100000+ -> 100
        vol_score = min(100.0, math.log10(max(search_volume, 0.0) + 1.0) * 20.0)
        signals["search_volume"] = (vol_score, f"volume={int(search_volume)} ({vol_score:.1f}/100)")
    else:
        signals["search_volume"] = (None, "volume=NOT_AVAILABLE")

    if keyword_difficulty is not None:
        # Lower KD is easier to rank -> higher score
        kd_score = max(0.0, min(100.0, 100.0 - float(keyword_difficulty)))
        signals["keyword_difficulty"] = (
            kd_score,
            f"KD={keyword_difficulty:.1f} (ease={kd_score:.1f}/100)",
        )
    else:
        signals["keyword_difficulty"] = (None, "KD=NOT_AVAILABLE")

    norm_intent = primary_intent.strip().title() if primary_intent else None
    if norm_intent is not None and norm_intent in INTENT_BUSINESS_SCORES:
        intent_score = INTENT_BUSINESS_SCORES[norm_intent]
        signals["intent_value"] = (intent_score, f"intent={norm_intent} ({intent_score:.0f}/100)")
    else:
        signals["intent_value"] = (None, "intent=NOT_CLASSIFIED")

    if cpc is not None:
        # Cap at $10 CPC for 100/100 commercial signal
        cpc_score = min(100.0, max(0.0, (float(cpc) / 10.0) * 100.0))
        signals["cpc"] = (cpc_score, f"CPC={cpc:.2f} ({cpc_score:.1f}/100)")
    else:
        signals["cpc"] = (None, "CPC=NOT_AVAILABLE")

    available_weight = sum(
        float(w.get(name, 0.0)) for name, (val, _) in signals.items() if val is not None
    )
    if available_weight <= 0:
        return (
            Decimal("50.00"),
            "P2",
            "Default neutral score (50.0): all quantitative metrics are NOT_AVAILABLE.",
        )

    weighted_sum = 0.0
    parts: list[str] = []
    missing_parts: list[str] = []
    for name, (val, desc) in signals.items():
        base_w = float(w.get(name, 0.0))
        if val is not None and base_w > 0:
            eff_w = base_w / available_weight
            weighted_sum += val * eff_w
            parts.append(f"{desc} x{eff_w:.2f}")
        elif val is None and base_w > 0:
            missing_parts.append(desc)

    final_score = round(min(max(weighted_sum, 0.0), 100.0), 2)
    tier = "P1" if final_score >= 70.0 else ("P2" if final_score >= 40.0 else "P3")
    reasoning = f"Score {final_score:.2f} ({tier}): " + "; ".join(parts)
    if missing_parts:
        reasoning += " | Missing (excluded, not treated as 0): " + ", ".join(missing_parts)
    return Decimal(f"{final_score:.2f}"), tier, reasoning


class PrioritizationService:
    """Computes and persists configurable priority scores for a research run."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def prioritize_run(
        self, research_run_id: UUID, owner_id: UUID
    ) -> tuple[int, dict[str, float], list[dict[str, Any]]]:
        run = self._db.scalar(
            select(ResearchRun)
            .join(Project, ResearchRun.project_id == Project.id)
            .where(ResearchRun.id == research_run_id, Project.owner_id == owner_id)
        )
        if not run:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found"
            )

        settings_row = self._db.scalar(
            select(ProjectSettings).where(ProjectSettings.project_id == run.project_id)
        )
        weights = dict(DEFAULT_PRIORITIZATION_WEIGHTS)
        if settings_row and settings_row.prioritization_weights:
            for k, v in settings_row.prioritization_weights.items():
                if k in weights:
                    weights[k] = float(v)

        keywords = list(
            self._db.scalars(
                select(Keyword).where(
                    Keyword.research_run_id == research_run_id,
                    Keyword.cleaning_status.in_(("ACTIVE", "RAW")),
                )
            ).all()
        )
        if not keywords:
            return 0, weights, []

        kw_ids = [kw.id for kw in keywords]
        metrics = list(
            self._db.scalars(
                select(KeywordMetric)
                .where(
                    KeywordMetric.keyword_id.in_(kw_ids),
                    KeywordMetric.data_status == "AVAILABLE",
                )
                .order_by(KeywordMetric.collected_at.desc())
            ).all()
        )
        latest_metrics: dict[UUID, dict[str, float]] = {}
        for m in metrics:
            bucket = latest_metrics.setdefault(m.keyword_id, {})
            if m.metric_type not in bucket and m.numeric_value is not None:
                bucket[m.metric_type] = float(m.numeric_value)

        intents = {
            row.keyword_id: row.primary_intent
            for row in self._db.scalars(
                select(KeywordIntent).where(
                    KeywordIntent.keyword_id.in_(kw_ids),
                    KeywordIntent.is_current.is_(True),
                )
            ).all()
        }

        scored: list[dict[str, Any]] = []
        for kw in keywords:
            m_map = latest_metrics.get(kw.id, {})
            score, tier, reasoning = compute_priority_for_keyword(
                search_volume=m_map.get("SEARCH_VOLUME"),
                keyword_difficulty=m_map.get("KEYWORD_DIFFICULTY"),
                cpc=m_map.get("CPC"),
                primary_intent=intents.get(kw.id),
                weights=weights,
            )
            kw.priority_score = score
            kw.priority_tier = tier
            kw.priority_reasoning = reasoning
            scored.append(
                {
                    "keyword_id": str(kw.id),
                    "keyword": kw.original_keyword,
                    "priority_score": float(score),
                    "priority_tier": tier,
                    "priority_reasoning": reasoning,
                }
            )

        self._db.commit()
        scored.sort(key=lambda item: item["priority_score"], reverse=True)
        return len(scored), weights, scored[:20]
