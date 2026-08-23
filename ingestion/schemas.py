"""
Shared output schemas for the Data Ingestion layer.

Every ingestion agent (yfinance_agent, edgar_agent, transcript_agent, news_agent)
MUST normalize its output into these models. The one rule that isn't optional:

    Every citable unit of data carries its OWN CitationMetadata.

Not "one metadata block per filing" -- every section, every line item, every
utterance, every article gets its own `metadata` field. That's what lets Role 2
(analysis) and Role 3 (RAG/memo) trace a claim like "current ratio is 1.8" back
to a specific document, section, and retrieval time, instead of just "some 10-K
somewhere."
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class DocumentType(str, Enum):
    FINANCIAL_STATEMENT = "financial_statement"
    SEC_FILING_10K = "sec_filing_10k"
    SEC_FILING_10Q = "sec_filing_10q"
    EARNINGS_TRANSCRIPT = "earnings_transcript"
    NEWS_ARTICLE = "news_article"


class StatementType(str, Enum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    KEY_STATS = "key_stats"
    HISTORICAL_PRICE = "historical_price"


class TranscriptSection(str, Enum):
    PREPARED_REMARKS = "prepared_remarks"
    QA = "qa"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Citation metadata -- attached to every citable unit, not just the parent doc
# --------------------------------------------------------------------------- #

class CitationMetadata(BaseModel):
    """The minimum needed to reconstruct a citation for any single data point."""

    ticker: str
    document_type: DocumentType
    source_url: Optional[str] = Field(
        default=None,
        description="Resolvable URL. None only when a provider has no stable "
                    "per-item URL (e.g. some yfinance fields) -- in that case "
                    "the provider name + retrieval time must substitute.",
    )
    source_name: str = Field(description="e.g. 'yfinance', 'SEC EDGAR', 'NewsAPI'")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    section_id: Optional[str] = Field(
        default=None,
        description="Chunk/section identifier, e.g. 'risk_factors#3' or "
                    "'qa#12'. Required for anything long-form (filings, "
                    "transcripts) so citations can point below document level.",
    )
    as_of_date: Optional[datetime] = Field(
        default=None, description="The date the underlying data/document itself "
                                   "pertains to (filing date, publish date, period end)."
    )

    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v: str) -> str:
        return v.strip().upper()


# --------------------------------------------------------------------------- #
# Financial statements (yfinance agent)
# --------------------------------------------------------------------------- #

class FinancialLineItem(BaseModel):
    """One line item, e.g. 'total_revenue': 391035000000."""

    name: str
    value: Optional[float] = Field(
        default=None, description="None (not 0, not omitted) when the source "
                                   "did not report this field."
    )
    unit: str = Field(default="USD")
    period_end: Optional[datetime] = None
    is_estimated: bool = False


class FinancialStatement(BaseModel):
    metadata: CitationMetadata
    statement_type: StatementType
    fiscal_period: str = Field(description="e.g. 'FY2025', 'Q3-2025'")
    line_items: list[FinancialLineItem] = Field(default_factory=list)
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Fields we tried to pull but yfinance didn't have, so "
                    "downstream consumers know it's an intentional gap, not a bug.",
    )


# --------------------------------------------------------------------------- #
# SEC filings (edgar agent)
# --------------------------------------------------------------------------- #

class FilingSection(BaseModel):
    """A single citable chunk of a filing, e.g. one 'Risk Factors' paragraph."""

    metadata: CitationMetadata
    section_name: str = Field(description="e.g. 'Risk Factors', 'MD&A', 'Item 1 Business'")
    paragraph_index: int = Field(description="Position within the section, 0-indexed")
    text: str


class FilingDocument(BaseModel):
    ticker: str
    cik: str
    filing_type: str = Field(description="'10-K' or '10-Q'")
    filed_date: datetime
    accession_number: str
    sections: list[FilingSection] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Earnings call transcripts (transcript agent)
# --------------------------------------------------------------------------- #

class TranscriptUtterance(BaseModel):
    metadata: CitationMetadata
    speaker: str
    speaker_title: Optional[str] = None
    section: TranscriptSection
    sequence: int = Field(description="Order within the call")
    text: str


class TranscriptDocument(BaseModel):
    ticker: str
    fiscal_quarter: Optional[str] = None
    call_date: Optional[datetime] = None
    available: bool = Field(
        description="False if no transcript could be found for this ticker's "
                    "most recent quarter -- explicit, not an exception."
    )
    unavailable_reason: Optional[str] = None
    utterances: list[TranscriptUtterance] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# News (news agent)
# --------------------------------------------------------------------------- #

class NewsArticle(BaseModel):
    metadata: CitationMetadata
    title: str
    source_publication: str
    published_at: datetime
    url: str
    snippet: str
    dedupe_key: str = Field(description="Normalized title+domain hash used for dedup")


# --------------------------------------------------------------------------- #
# Convenience union for storage layer
# --------------------------------------------------------------------------- #

IngestedDocument = FinancialStatement | FilingDocument | TranscriptDocument | NewsArticle
