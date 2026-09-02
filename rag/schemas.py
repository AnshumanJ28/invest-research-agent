"""Pydantic schemas for Role 3 RAG inputs.

These models describe the data shape consumed by retrieval and later citation
generation. They intentionally do not duplicate the larger ingestion/analysis
schemas; instead they keep the citable fields that are actually present in the
SQLite database, with optional slots for richer metadata when future pipeline
runs populate it.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceType = Literal["filing", "news", "transcript"]


class Chunk(BaseModel):
    """One citable narrative unit prepared from SQLite source tables."""

    chunk_id: str = Field(description="Deterministic identifier for this chunk.")
    ticker: str
    text: str
    source_type: SourceType
    source_id: str = Field(description="Original SQLite table row id or durable source id.")
    section: str | None = None
    title: str | None = None
    speaker: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinancialFact(BaseModel):
    """One deterministic financial line item from `financial_statements`.

    Financial facts are kept separate from narrative chunks so memo generation
    can cite structured numbers without pretending they were retrieved prose.
    """

    fact_id: str
    ticker: str
    statement_id: int
    statement_type: str
    fiscal_period: str
    name: str
    value: float | None = None
    unit: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """A ranked retrieval hit with the original chunk and similarity score."""

    chunk: Chunk
    score: float
    rank: int


class Citation(BaseModel):
    """Citation label mapped to one retrieved source chunk."""

    citation_id: str
    chunk_id: str
    source_type: SourceType
    source_id: str
    ticker: str
    title: str | None = None
    section: str | None = None
    speaker: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    text_excerpt: str


class MemoClaim(BaseModel):
    claim_id: str
    text: str
    citation_ids: list[str] = Field(default_factory=list)


class MemoSection(BaseModel):
    name: str
    content: str
    claims: list[MemoClaim] = Field(default_factory=list)


class InvestmentMemo(BaseModel):
    ticker: str
    generated_at: datetime
    sections: list[MemoSection]
    citations: list[Citation]
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = "This is a research aid, not financial advice."
    invalid_citation_ids: list[str] = Field(default_factory=list)


class VerificationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"


class ClaimVerification(BaseModel):
    claim_id: str
    claim_text: str
    citation_ids: list[str] = Field(default_factory=list)
    status: VerificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    evidence_excerpt: str | None = None


class VerifiedMemo(BaseModel):
    original_memo: InvestmentMemo
    verified_memo: InvestmentMemo
    verifications: list[ClaimVerification]
    unsupported_claim_count: int
    contradicted_claim_count: int
    overall_status: str
    verifier_model: str | None = None
    verification_api_calls: int = 0
