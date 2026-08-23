"""
Shared output schemas for the Analysis & NLP layer.

Role 3 (RAG/Memo) needs ONE consistent schema per concept -- not three ad hoc
shapes for ratios, sentiment, and comparisons. Every model here carries a
`SourceRef` back to the ingestion layer's citation metadata, so a memo claim
like "current ratio is 1.8, a healthy level" traces all the way back to the
specific balance sheet line items it was computed from.

NOTE ON THE INGESTION SCHEMA DEPENDENCY:
This module imports `CitationMetadata` from `ingestion.schemas` where
possible. If Role 1's real schema isn't available in a given environment,
`ingestion.schemas` is NOT vendored/duplicated here -- instead we degrade to
a local placeholder (`SourceRef`) which is a deliberately looser version of
the same idea (document type + identifier + section), flagged below as an
ASSUMPTION TO RECONCILE. In this project both schemas are in fact available
side by side (see analysis/utils.py `to_source_ref`), so integration is a
matter of thin adaptation, not a rewrite.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# ASSUMPTION FLAG: placeholder source reference
# --------------------------------------------------------------------------- #
# If ingestion.schemas.CitationMetadata isn't importable in some environment,
# this is the fallback shape analysis output degrades to. It carries strictly
# less than the real thing (no retrieved_at, no source_name distinction from
# document_type) -- reconcile against ingestion.schemas.CitationMetadata as
# soon as Role 1's schema is available, rather than building further on this.
class SourceRef(BaseModel):
    ticker: str
    document_type: str
    source_url: Optional[str] = None
    section_id: Optional[str] = None
    as_of_date: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Ratios
# --------------------------------------------------------------------------- #

class RatioCategory(str, Enum):
    LIQUIDITY = "liquidity"
    PROFITABILITY = "profitability"
    LEVERAGE = "leverage"
    VALUATION = "valuation"


class HealthFlag(str, Enum):
    HEALTHY = "healthy"
    WATCH = "watch"
    CONCERNING = "concerning"
    NOT_APPLICABLE = "not_applicable"  # e.g. leverage ratios for a bank


class RatioResult(BaseModel):
    name: str = Field(description="e.g. 'current_ratio'")
    category: RatioCategory
    formula: str = Field(description="Human-readable formula, e.g. 'current_assets / current_liabilities'")
    value: Optional[float] = Field(default=None, description="None if not computable")
    source_line_items: list[SourceRef] = Field(
        default_factory=list,
        description="One SourceRef per input line item used in the formula.",
    )
    computable: bool = True
    note: Optional[str] = Field(
        default=None,
        description="Why it's not computable, or a company-type caveat "
                    "(e.g. 'debt-to-equity is not meaningful for bank holding companies').",
    )
    health_flag: HealthFlag = HealthFlag.NOT_APPLICABLE
    narrative: Optional[str] = Field(
        default=None, description="Threshold-based human-readable framing for the memo, "
                                   "e.g. 'Current ratio below 1.0 may indicate liquidity pressure.'"
    )


# --------------------------------------------------------------------------- #
# Sentiment
# --------------------------------------------------------------------------- #

class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class SentimentSegment(str, Enum):
    NEWS = "news"
    TRANSCRIPT_PREPARED_REMARKS = "transcript_prepared_remarks"
    TRANSCRIPT_QA = "transcript_qa"


class SentimentResult(BaseModel):
    segment: SentimentSegment
    label: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    excerpt: str = Field(description="The exact text scored, truncated for readability")
    source: SourceRef
    model_name: str = "ProsusAI/finbert"


class AggregateSentiment(BaseModel):
    ticker: str
    overall_label: SentimentLabel
    overall_score: float = Field(description="Weighted average, -1.0 (very negative) to +1.0 (very positive)")
    trend: str = Field(description="'improving' / 'declining' / 'stable', based on recency-weighted trajectory")
    component_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Per-segment breakdown, e.g. {'news': 0.2, 'transcript_qa': -0.1}",
    )
    sample_size: dict[str, int] = Field(default_factory=dict)
    limitations_note: str = (
        "FinBERT is known to underperform on sarcasm, heavily hedged "
        "forward-looking statements, and dense financial jargon; treat "
        "scores near the neutral boundary with caution."
    )


# --------------------------------------------------------------------------- #
# Competitor comparison
# --------------------------------------------------------------------------- #

class PeerSnapshot(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    ratios: list[RatioResult] = Field(default_factory=list)
    sentiment: Optional[AggregateSentiment] = None
    data_available: bool = True
    unavailable_reason: Optional[str] = None


class CompetitorComparison(BaseModel):
    primary_ticker: str
    peers: list[PeerSnapshot]
    peer_selection_method: str = Field(
        description="How peers were chosen, e.g. 'same GICS sub-industry via yfinance sector/industry fields'"
    )
    comparison_table: dict[str, dict[str, Optional[float]]] = Field(
        description="ratio_name -> {ticker: value}, includes primary_ticker as one of the keys"
    )


# --------------------------------------------------------------------------- #
# Top-level analysis report -- what Role 3 actually consumes
# --------------------------------------------------------------------------- #

class AnalysisReport(BaseModel):
    ticker: str
    generated_at: datetime
    ratios: list[RatioResult]
    sentiment: AggregateSentiment
    competitors: Optional[CompetitorComparison] = None
    known_limitations: list[str] = Field(default_factory=list)
