"""Prompt construction for cited investment memo generation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .schemas import Citation, FinancialFact

DISCLAIMER = "This is a research aid, not financial advice."

MEMO_SECTION_NAMES = [
    "Executive Summary",
    "Financial Overview",
    "Risk Factors",
    "Sentiment & News Analysis",
    "Competitor Comparison",
    "Key Limitations",
    "Disclaimer",
]


def build_memo_prompt(
    *,
    ticker: str,
    evidence_by_section: Mapping[str, Sequence[Citation]],
    financial_facts: Sequence[FinancialFact],
    limitations: Sequence[str],
) -> str:
    citation_ids = [c.citation_id for citations in evidence_by_section.values() for c in citations]
    facts_block = "\n".join(_format_fact(i, fact) for i, fact in enumerate(financial_facts[:40], start=1))
    evidence_block = "\n\n".join(
        _format_evidence_section(name, citations)
        for name, citations in evidence_by_section.items()
    )
    limitations_block = "\n".join(f"- {item}" for item in limitations) or "- None"

    return f"""You are writing an investment research memo for ticker {ticker}.

Rules:
- Use ONLY the supplied evidence and structured financial facts.
- Do not use your own knowledge about the company.
- Do not infer missing numerical values.
- Do not calculate ratios unless a ratio is explicitly supplied.
- Do not make price predictions.
- Do not issue BUY, HOLD, or SELL recommendations.
- Every important factual claim must include one or more provided citation IDs.
- Use only these citation IDs: {", ".join(citation_ids) if citation_ids else "none"}.
- Never invent citation IDs.
- If evidence does not support a requested section, state that data is unavailable.
- Distinguish factual evidence from neutral interpretation.
- Keep financial interpretation conservative.
- The final disclaimer must be exactly: {DISCLAIMER}

Required sections:
{chr(10).join(f"- {name}" for name in MEMO_SECTION_NAMES)}

Known data limitations:
{limitations_block}

Available evidence:
{evidence_block or "No narrative evidence was retrieved."}

Structured financial facts:
{facts_block or "No structured financial facts were supplied."}

Return valid JSON only, matching this shape:
{{
  "sections": [
    {{
      "name": "Executive Summary",
      "content": "Short section text with citations like [S1].",
      "claims": [
        {{
          "claim_id": "CLM-001",
          "text": "One factual claim from the section.",
          "citation_ids": ["S1"]
        }}
      ]
    }}
  ],
  "limitations": ["Limitation text"],
  "disclaimer": "{DISCLAIMER}"
}}
"""


def build_verification_prompt(*, claim_id: str, claim_text: str, evidence_text: str) -> str:
    return f"""You are a strict financial evidence verifier.

Evaluate ONLY whether the supplied evidence supports the supplied claim.

Do not use outside knowledge.
Do not assume missing facts.
Do not judge whether the company is good or bad.
Do not rewrite the claim.
A topically related source is NOT automatically supporting evidence.

Return SUPPORTED only when the cited evidence directly entails all material parts of the claim.
If the claim contains a numerical value, direction, date, comparison, or named fact that differs from the source, classify it appropriately.

Status definitions:
- SUPPORTED: the evidence directly supports all material parts of the claim.
- PARTIAL: the evidence supports only part of the claim, or the claim is stronger than the source.
- UNSUPPORTED: the cited evidence does not establish the claim.
- CONTRADICTED: the evidence explicitly conflicts with the claim.

CLAIM ID:
{claim_id}

CLAIM:
{claim_text}

CITED EVIDENCE:
{evidence_text}

Return strict JSON only:
{{
  "claim_id": "{claim_id}",
  "status": "SUPPORTED | PARTIAL | UNSUPPORTED | CONTRADICTED",
  "confidence": 0.0,
  "explanation": "short reason"
}}
"""


def _format_evidence_section(name: str, citations: Sequence[Citation]) -> str:
    if not citations:
        return f"## {name}\nNo retrieved evidence."
    return "\n\n".join(
        f"{c.citation_id}\n"
        f"Source Type: {c.source_type}\n"
        f"Ticker: {c.ticker}\n"
        f"Section: {c.section}\n"
        f"Title: {c.title}\n"
        f"Speaker: {c.speaker}\n"
        f"Date: {c.published_at.isoformat() if c.published_at else None}\n"
        f"URL: {c.source_url}\n"
        f"Evidence: {c.text_excerpt}"
        for c in citations
    ).join([f"## {name}\n", ""])


def _format_fact(index: int, fact: FinancialFact) -> str:
    return (
        f"[F{index}] {fact.ticker} {fact.statement_type} {fact.fiscal_period}: "
        f"{fact.name} = {fact.value} {fact.unit or ''}".strip()
    )
