"""Claim-to-source verification for generated investment memos."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from .llm_client import GeminiClientError
from .memo_generator import render_markdown
from .prompts import build_verification_prompt
from .schemas import (
    Citation,
    ClaimVerification,
    FinancialFact,
    InvestmentMemo,
    MemoClaim,
    MemoSection,
    VerificationStatus,
    VerifiedMemo,
)


class ClaimVerifier(Protocol):
    model_name: str | None
    api_call_count: int

    def verify(self, claim: MemoClaim, evidence_text: str) -> ClaimVerification:
        ...


class LLMClaimVerifier:
    """Gemini-backed verifier for one claim and its cited evidence."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.model_name = getattr(llm_client, "model", None)
        self.api_call_count = 0

    def verify(self, claim: MemoClaim, evidence_text: str) -> ClaimVerification:
        prompt = build_verification_prompt(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            evidence_text=evidence_text,
        )
        self.api_call_count += 1
        try:
            raw = self.llm_client.generate_json(prompt)
            data = json.loads(_strip_code_fence(raw))
            status = VerificationStatus(str(data.get("status", "")).upper())
            confidence = float(data.get("confidence", 0.0))
            explanation = str(data.get("explanation", "")).strip() or "No explanation returned."
        except (GeminiClientError, json.JSONDecodeError, ValueError, TypeError) as exc:
            return ClaimVerification(
                claim_id=claim.claim_id,
                claim_text=claim.text,
                citation_ids=claim.citation_ids,
                status=VerificationStatus.UNSUPPORTED,
                confidence=0.0,
                explanation=f"Semantic verification failed: {exc}",
                evidence_excerpt=evidence_text[:700],
            )

        return ClaimVerification(
            claim_id=claim.claim_id,
            claim_text=claim.text,
            citation_ids=claim.citation_ids,
            status=status,
            confidence=max(0.0, min(confidence, 1.0)),
            explanation=explanation,
            evidence_excerpt=evidence_text[:700],
        )


class VerificationService:
    """Deterministic citation checks first, semantic verification second."""

    def __init__(
        self,
        *,
        claim_verifier: ClaimVerifier,
        financial_facts: list[FinancialFact] | None = None,
        include_partial_in_verified_memo: bool = True,
    ):
        self.claim_verifier = claim_verifier
        self.financial_facts = financial_facts or []
        self.include_partial_in_verified_memo = include_partial_in_verified_memo

    def verify_memo(self, memo: InvestmentMemo) -> VerifiedMemo:
        evidence_map = self._evidence_map(memo)
        verifications: list[ClaimVerification] = []

        for section in memo.sections:
            for claim in section.claims:
                deterministic = self._deterministic_check(memo, claim, evidence_map)
                if deterministic is not None:
                    verifications.append(deterministic)
                    continue
                evidence_text = _combined_evidence_text(claim.citation_ids, evidence_map)
                verifications.append(self.claim_verifier.verify(claim, evidence_text))

        verified_memo = build_verified_memo(
            memo,
            verifications,
            include_partial=self.include_partial_in_verified_memo,
        )
        unsupported = sum(v.status == VerificationStatus.UNSUPPORTED for v in verifications)
        contradicted = sum(v.status == VerificationStatus.CONTRADICTED for v in verifications)
        partial = sum(v.status == VerificationStatus.PARTIAL for v in verifications)
        overall_status = "NEEDS_REVIEW" if unsupported or contradicted or partial else "SUPPORTED"

        return VerifiedMemo(
            original_memo=memo,
            verified_memo=verified_memo,
            verifications=verifications,
            unsupported_claim_count=unsupported,
            contradicted_claim_count=contradicted,
            overall_status=overall_status,
            verifier_model=self.claim_verifier.model_name,
            verification_api_calls=self.claim_verifier.api_call_count,
        )

    def _evidence_map(self, memo: InvestmentMemo) -> dict[str, "_Evidence"]:
        evidence: dict[str, _Evidence] = {}
        for citation in memo.citations:
            evidence[_normalize_citation_id(citation.citation_id)] = _Evidence(
                citation_id=_normalize_citation_id(citation.citation_id),
                ticker=citation.ticker,
                text=citation.text_excerpt,
                source_descriptor=_describe_citation(citation),
            )
        for idx, fact in enumerate(self.financial_facts, start=1):
            evidence[f"[F{idx}]"] = _Evidence(
                citation_id=f"[F{idx}]",
                ticker=fact.ticker,
                text=f"{fact.statement_type} {fact.fiscal_period}: {fact.name} = {fact.value} {fact.unit or ''}".strip(),
                source_descriptor=f"financial_statements row {fact.statement_id}",
            )
        return evidence

    def _deterministic_check(
        self,
        memo: InvestmentMemo,
        claim: MemoClaim,
        evidence_map: dict[str, "_Evidence"],
    ) -> ClaimVerification | None:
        if not claim.text.strip():
            return _unsupported(claim, "Claim text is empty.", None)
        if not claim.citation_ids:
            return _unsupported(claim, "Claim has no citation IDs.", None)

        for citation_id in claim.citation_ids:
            normalized = _normalize_citation_id(citation_id)
            evidence = evidence_map.get(normalized)
            if evidence is None:
                return _unsupported(claim, f"Citation ID {citation_id} does not exist.", None)
            if evidence.ticker.upper() != memo.ticker.upper():
                return _unsupported(
                    claim,
                    f"Citation ID {citation_id} belongs to {evidence.ticker}, not {memo.ticker}.",
                    evidence.text,
                )
            if not evidence.text.strip():
                return _unsupported(claim, f"Citation ID {citation_id} has empty evidence text.", None)
        return None


def build_verified_memo(
    memo: InvestmentMemo,
    verifications: list[ClaimVerification],
    *,
    include_partial: bool = True,
) -> InvestmentMemo:
    """Return a filtered memo while leaving the original memo untouched."""

    memo_copy = deepcopy(memo)
    status_by_claim = {v.claim_id: v for v in verifications}
    safe_sections: list[MemoSection] = []

    for section in memo_copy.sections:
        if not section.claims:
            safe_sections.append(section)
            continue

        kept_claims = []
        lines = []
        for claim in section.claims:
            verification = status_by_claim.get(claim.claim_id)
            if verification is None:
                continue
            if verification.status == VerificationStatus.SUPPORTED:
                kept_claims.append(claim)
                lines.append(_claim_line(claim))
            elif verification.status == VerificationStatus.PARTIAL and include_partial:
                kept_claims.append(claim)
                lines.append(f"[Partial support; review recommended] {_claim_line(claim)}")

        safe_sections.append(
            MemoSection(
                name=section.name,
                content="\n".join(lines) if lines else f"{section.name} has no fully supported claims after verification.",
                claims=kept_claims,
            )
        )

    memo_copy.sections = safe_sections
    return memo_copy


def save_verification_outputs(
    verified: VerifiedMemo,
    output_dir: str | Path = "rag/output",
) -> tuple[Path, Path, Path]:
    output_path = Path(output_dir) / verified.original_memo.ticker
    output_path.mkdir(parents=True, exist_ok=True)
    verification_path = output_path / "verification.json"
    verified_json_path = output_path / "verified_memo.json"
    verified_md_path = output_path / "verified_memo.md"

    verification_path.write_text(verified.model_dump_json(indent=2), encoding="utf-8")
    verified_json_path.write_text(verified.verified_memo.model_dump_json(indent=2), encoding="utf-8")
    verified_md_path.write_text(render_markdown(verified.verified_memo), encoding="utf-8")
    return verification_path, verified_json_path, verified_md_path


class _Evidence:
    def __init__(self, *, citation_id: str, ticker: str, text: str, source_descriptor: str):
        self.citation_id = citation_id
        self.ticker = ticker
        self.text = text
        self.source_descriptor = source_descriptor


def _unsupported(claim: MemoClaim, explanation: str, evidence_excerpt: str | None) -> ClaimVerification:
    return ClaimVerification(
        claim_id=claim.claim_id,
        claim_text=claim.text,
        citation_ids=claim.citation_ids,
        status=VerificationStatus.UNSUPPORTED,
        confidence=1.0,
        explanation=explanation,
        evidence_excerpt=evidence_excerpt,
    )


def _combined_evidence_text(citation_ids: list[str], evidence_map: dict[str, _Evidence]) -> str:
    blocks = []
    for citation_id in citation_ids:
        normalized = _normalize_citation_id(citation_id)
        evidence = evidence_map[normalized]
        blocks.append(f"{normalized}\nSOURCE: {evidence.source_descriptor}\nEVIDENCE: {evidence.text}")
    return "\n\n".join(blocks)


def _describe_citation(citation: Citation) -> str:
    detail = citation.title or citation.section or citation.speaker or citation.source_type
    return f"{citation.source_type}; {detail}; source_id={citation.source_id}; url={citation.source_url}"


def _normalize_citation_id(citation_id: str) -> str:
    citation_id = citation_id.strip()
    if re.fullmatch(r"[SF]\d+", citation_id):
        return f"[{citation_id}]"
    return citation_id


def _claim_line(claim: MemoClaim) -> str:
    citations = " ".join(_normalize_citation_id(c) for c in claim.citation_ids)
    return f"{claim.text} {citations}".strip()


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped
