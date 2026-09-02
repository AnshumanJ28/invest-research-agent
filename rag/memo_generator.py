"""Cited memo generation orchestration for Role 3 Part 4."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import DEFAULT_DB_PATH, load_financial_facts, load_news_chunks, load_transcript_chunks
from .prompts import DISCLAIMER, MEMO_SECTION_NAMES, build_memo_prompt
from .retrieval import MEMO_TOPIC_QUERIES, Retriever
from .schemas import Citation, FinancialFact, InvestmentMemo, MemoClaim, MemoSection, RetrievalResult


class MemoGenerationError(RuntimeError):
    """Raised when memo generation produces invalid or unusable output."""


class MemoGenerator:
    def __init__(
        self,
        *,
        retriever: Retriever,
        llm_client,
        db_path: str | Path = DEFAULT_DB_PATH,
        top_k: int = 5,
        max_facts: int = 25,
    ):
        self.retriever = retriever
        self.llm_client = llm_client
        self.db_path = Path(db_path)
        self.top_k = top_k
        self.max_facts = max_facts

    def generate(self, ticker: str) -> InvestmentMemo:
        if not ticker:
            raise MemoGenerationError("Ticker is required.")
        ticker = ticker.upper()

        financial_facts = [
            fact for fact in load_financial_facts(self.db_path)
            if fact.ticker.upper() == ticker
        ][: self.max_facts]
        limitations = self._dataset_limitations(ticker)
        evidence_by_section, citations = self._retrieve_evidence(ticker)

        prompt = build_memo_prompt(
            ticker=ticker,
            evidence_by_section=evidence_by_section,
            financial_facts=financial_facts,
            limitations=limitations,
        )
        raw_json = self.llm_client.generate_json(prompt)
        memo = self._parse_memo_response(
            ticker=ticker,
            raw_json=raw_json,
            citations=citations,
            financial_fact_count=len(financial_facts),
            limitations=limitations,
        )
        return memo

    def save_outputs(self, memo: InvestmentMemo, output_dir: str | Path = "rag/output") -> tuple[Path, Path]:
        output_path = Path(output_dir) / memo.ticker
        output_path.mkdir(parents=True, exist_ok=True)
        json_path = output_path / "memo.json"
        md_path = output_path / "memo.md"

        json_path.write_text(memo.model_dump_json(indent=2), encoding="utf-8")
        md_path.write_text(render_markdown(memo), encoding="utf-8")
        return json_path, md_path

    def _retrieve_evidence(self, ticker: str) -> tuple[OrderedDict[str, list[Citation]], list[Citation]]:
        search_plan = OrderedDict(
            [
                ("Executive Summary", MEMO_TOPIC_QUERIES["executive_summary"]),
                ("Financial Overview", MEMO_TOPIC_QUERIES["financial_overview"]),
                ("Risk Factors", MEMO_TOPIC_QUERIES["risk_factors"]),
                ("Sentiment & News Analysis", MEMO_TOPIC_QUERIES["sentiment_news"]),
                ("Competitor Comparison", MEMO_TOPIC_QUERIES["competitor_comparison"]),
            ]
        )
        evidence_by_section: OrderedDict[str, list[Citation]] = OrderedDict()
        citations_by_chunk: OrderedDict[str, Citation] = OrderedDict()

        for section_name, query in search_plan.items():
            results = self.retriever.search(query, ticker=ticker, top_k=self.top_k)
            section_citations = []
            for result in results:
                chunk = result.chunk
                if chunk.chunk_id not in citations_by_chunk:
                    citation = _citation_from_result(len(citations_by_chunk) + 1, result)
                    citations_by_chunk[chunk.chunk_id] = citation
                section_citations.append(citations_by_chunk[chunk.chunk_id])
            evidence_by_section[section_name] = section_citations

        return evidence_by_section, list(citations_by_chunk.values())

    def _dataset_limitations(self, ticker: str) -> list[str]:
        limitations: list[str] = []
        news_chunks = [chunk for chunk in load_news_chunks(self.db_path) if chunk.ticker.upper() == ticker]
        transcript_chunks = [
            chunk for chunk in load_transcript_chunks(self.db_path)
            if chunk.ticker.upper() == ticker
        ]
        if not news_chunks:
            limitations.append("Recent news analysis is unavailable from the current dataset.")
        if not transcript_chunks:
            limitations.append("Earnings-call transcript evidence is unavailable from the current dataset.")
        limitations.append("Financial ratios are computed elsewhere but are not persisted in SQLite for this RAG layer.")
        limitations.append("Competitor comparison is unavailable from the current dataset.")
        return limitations

    def _parse_memo_response(
        self,
        *,
        ticker: str,
        raw_json: str,
        citations: list[Citation],
        limitations: list[str],
        financial_fact_count: int = 0,
    ) -> InvestmentMemo:
        try:
            data = json.loads(_strip_code_fence(raw_json))
        except json.JSONDecodeError as exc:
            raise MemoGenerationError(f"LLM returned malformed JSON: {exc}") from exc

        valid_ids = {citation.citation_id for citation in citations}
        valid_ids.update(f"[F{idx}]" for idx in range(1, financial_fact_count + 1))
        sections = [_section_from_dict(item) for item in data.get("sections", [])]
        sections = _ensure_required_sections(sections)
        disclaimer = data.get("disclaimer") or DISCLAIMER
        if disclaimer != DISCLAIMER:
            disclaimer = DISCLAIMER

        response_limitations = [str(item) for item in data.get("limitations", [])]
        combined_limitations = _dedupe([*limitations, *response_limitations])
        invalid_ids = sorted(_extract_citation_ids(sections) - valid_ids)
        invalid_ids.extend(
            sorted(
                {
                    citation_id
                    for section in sections
                    for claim in section.claims
                    for citation_id in claim.citation_ids
                    if citation_id not in valid_ids
                }
            )
        )
        invalid_ids = sorted(set(invalid_ids))
        if invalid_ids:
            combined_limitations.append(
                "Generated memo contained invalid citation IDs that were not supplied: "
                + ", ".join(invalid_ids)
            )

        return InvestmentMemo(
            ticker=ticker,
            generated_at=datetime.now(timezone.utc),
            sections=sections,
            citations=citations,
            limitations=combined_limitations,
            disclaimer=disclaimer,
            invalid_citation_ids=invalid_ids,
        )


def render_markdown(memo: InvestmentMemo) -> str:
    lines = [f"# Investment Research Memo: {memo.ticker}", ""]
    for section in memo.sections:
        lines.extend([f"## {section.name}", "", section.content, ""])
    lines.extend(["## Citations", ""])
    for citation in memo.citations:
        label = citation.citation_id
        descriptor = citation.title or citation.section or citation.speaker or citation.source_type
        lines.append(f"- {label}: {citation.source_type}, {descriptor}, source_id={citation.source_id}, url={citation.source_url}")
    lines.extend(["", "## Limitations", ""])
    for limitation in memo.limitations:
        lines.append(f"- {limitation}")
    lines.extend(["", memo.disclaimer, ""])
    return "\n".join(lines)


def _citation_from_result(index: int, result: RetrievalResult) -> Citation:
    chunk = result.chunk
    return Citation(
        citation_id=f"[S{index}]",
        chunk_id=chunk.chunk_id,
        source_type=chunk.source_type,
        source_id=chunk.source_id,
        ticker=chunk.ticker,
        title=chunk.title,
        section=chunk.section,
        speaker=chunk.speaker,
        source_url=chunk.source_url,
        published_at=chunk.published_at,
        text_excerpt=chunk.text[:900],
    )


def _section_from_dict(data: dict[str, Any]) -> MemoSection:
    return MemoSection(
        name=str(data.get("name", "Untitled Section")),
        content=str(data.get("content", "")),
        claims=[
            MemoClaim(
                claim_id=str(claim.get("claim_id", f"CLM-{idx:03d}")),
                text=str(claim.get("text", "")),
                citation_ids=[str(citation_id) for citation_id in claim.get("citation_ids", [])],
            )
            for idx, claim in enumerate(data.get("claims", []), start=1)
        ],
    )


def _ensure_required_sections(sections: list[MemoSection]) -> list[MemoSection]:
    by_name = {section.name: section for section in sections}
    return [
        by_name.get(name)
        or MemoSection(
            name=name,
            content=DISCLAIMER if name == "Disclaimer" else f"{name} is unavailable from the current dataset.",
            claims=[],
        )
        for name in MEMO_SECTION_NAMES
    ]


def _extract_citation_ids(sections: list[MemoSection]) -> set[str]:
    ids: set[str] = set()
    for section in sections:
        ids.update(re.findall(r"\[[SF]\d+\]", section.content))
    return ids


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
