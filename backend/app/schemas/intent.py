"""Pydantic v2 structured output schemas for evidence-based Search Intent classification."""

from typing import Literal

from pydantic import BaseModel, Field

SearchIntentType = Literal[
    "INFORMATIONAL",
    "NAVIGATIONAL",
    "COMMERCIAL",
    "TRANSACTIONAL",
]


class IntentClassificationOutput(BaseModel):
    """Structured output contract returned by LLM or heuristic Search Intent classifiers."""

    primary_intent: SearchIntentType
    secondary_intent: SearchIntentType | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=10, max_length=2000)
    evidence_urls: list[str] = Field(default_factory=list)
    serp_signals: list[str] = Field(default_factory=list)
    content_type_dominant: str | None = None
