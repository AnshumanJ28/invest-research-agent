"""Command-line runner for Role 3 RAG and memo generation."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter
from pathlib import Path

from .chunking import load_financial_facts, load_filing_chunks, load_news_chunks, load_transcript_chunks
from .config import ConfigError, RAGConfig, configure_logging, load_config, validate_db_path
from .embeddings import EmbeddingService
from .llm_client import GeminiClientError, GeminiLLMClient, MissingGeminiAPIKey
from .memo_generator import MemoGenerationError, MemoGenerator
from .retrieval import Retriever
from .schemas import InvestmentMemo, VerificationStatus
from .verification import LLMClaimVerifier, VerificationService, save_verification_outputs

LOGGER = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a cited investment memo from local SQLite evidence.")
    parser.add_argument("ticker", help="Ticker to generate, for example RELIANCE.NS")
    parser.add_argument("--retrieval-only", action="store_true", help="Build the FAISS index and run smoke queries only.")
    parser.add_argument("--verify-existing", action="store_true", help="Verify an existing memo.json without regenerating.")
    args = parser.parse_args(argv)

    configure_logging()
    try:
        config = load_config(args.ticker)
        validate_db_path(config.db_path)
        return run_pipeline(config, retrieval_only=args.retrieval_only, verify_existing=args.verify_existing)
    except ConfigError as exc:
        LOGGER.error("[CONFIG] %s", exc)
        return 2
    except (MissingGeminiAPIKey, GeminiClientError, MemoGenerationError) as exc:
        LOGGER.error("[RAG] %s", exc)
        return 1


def run_pipeline(config: RAGConfig, *, retrieval_only: bool = False, verify_existing: bool = False) -> int:
    LOGGER.info("[1/6] Loading evidence from %s", config.db_path)
    filing_chunks = [chunk for chunk in load_filing_chunks(config.db_path) if chunk.ticker.upper() == config.ticker]
    news_chunks = [chunk for chunk in load_news_chunks(config.db_path) if chunk.ticker.upper() == config.ticker]
    transcript_chunks = [chunk for chunk in load_transcript_chunks(config.db_path) if chunk.ticker.upper() == config.ticker]
    chunks = [*filing_chunks, *news_chunks, *transcript_chunks]
    facts = [fact for fact in load_financial_facts(config.db_path) if fact.ticker.upper() == config.ticker]

    if not chunks:
        raise ConfigError(f"No narrative evidence chunks found for {config.ticker}.")
    if not filing_chunks:
        raise ConfigError(f"No filing sections found for {config.ticker}.")

    LOGGER.info("Evidence chunks: %s filing, %s news, %s transcript", len(filing_chunks), len(news_chunks), len(transcript_chunks))
    LOGGER.info("Financial facts: %s", len(facts))

    LOGGER.info("[2/6] Building local embeddings and FAISS index")
    embedding_service = EmbeddingService(model_name=config.embedding_model)
    retriever = Retriever(chunks, embedding_service=embedding_service)
    LOGGER.info("Embedding model: %s", config.embedding_model)
    LOGGER.info("FAISS index: %s, metric: %s, dimension: %s", retriever.index_type, retriever.metric, retriever.dimension)

    _print_retrieval_smoke(retriever, config)
    if retrieval_only:
        LOGGER.info("[DONE] Retrieval-only check complete.")
        return 0

    generator = MemoGenerator(
        retriever=retriever,
        llm_client=GeminiLLMClient(model=config.gemini_model),
        db_path=config.db_path,
        top_k=config.top_k,
    )

    if verify_existing:
        LOGGER.info("[3/6] Loading existing memo")
        memo, json_path, md_path = _load_existing_memo(config)
    else:
        LOGGER.info("[3/6] Retrieving evidence and generating cited memo")
        memo = generator.generate(config.ticker)
        json_path, md_path = generator.save_outputs(memo, config.output_root)

    verification_paths: tuple[Path, Path, Path] | None = None
    verified = None
    if config.enable_verification:
        LOGGER.info("[4/6] Verifying generated claims against cited evidence")
        _refresh_invalid_citation_ids(memo, financial_fact_count=min(len(facts), generator.max_facts))
        verification_service = VerificationService(
            claim_verifier=LLMClaimVerifier(GeminiLLMClient(model=config.gemini_model)),
            financial_facts=facts[: generator.max_facts],
        )
        verified = verification_service.verify_memo(memo)
        verification_paths = save_verification_outputs(verified, config.output_root)
    else:
        LOGGER.info("[4/6] Verification disabled by ENABLE_VERIFICATION=false")

    LOGGER.info("[5/6] Writing outputs under %s", config.ticker_output_dir)
    LOGGER.info("[6/6] Complete")
    _print_final_summary(config, memo, json_path, md_path, verified, verification_paths)
    return 0


def _load_existing_memo(config: RAGConfig) -> tuple[InvestmentMemo, Path, Path]:
    json_path = config.ticker_output_dir / "memo.json"
    md_path = config.ticker_output_dir / "memo.md"
    if not json_path.exists():
        legacy = config.output_root / f"{config.ticker}_memo.json"
        if legacy.exists():
            json_path = legacy
            md_path = config.output_root / f"{config.ticker}_memo.md"
        else:
            raise ConfigError(f"Existing memo not found at {json_path}. Run without --verify-existing first.")
    return InvestmentMemo.model_validate_json(json_path.read_text(encoding="utf-8")), json_path, md_path


def _print_retrieval_smoke(retriever: Retriever, config: RAGConfig) -> None:
    queries = [
        "What are the major risks faced by the company?",
        "How is the company performing financially?",
        "What recent developments are mentioned?",
    ]
    for query in queries:
        results = retriever.search(query=query, ticker=config.ticker, top_k=min(3, config.top_k))
        LOGGER.info("Smoke query: %s", query)
        for result in results[:2]:
            chunk = result.chunk
            LOGGER.info(
                "  rank=%s score=%.4f source=%s section=%s source_id=%s preview=%s",
                result.rank,
                result.score,
                chunk.source_type,
                chunk.section or chunk.title or chunk.speaker,
                chunk.source_id,
                chunk.text[:140].replace("\n", " "),
            )


def _print_final_summary(
    config: RAGConfig,
    memo: InvestmentMemo,
    json_path: Path,
    md_path: Path,
    verified,
    verification_paths: tuple[Path, Path, Path] | None,
) -> None:
    unavailable = [section.name for section in memo.sections if "unavailable" in section.content.lower()]
    claim_count = sum(len(section.claims) for section in memo.sections)

    print("\n=== Role 3 RAG Memo Summary ===")
    print(f"Ticker: {config.ticker}")
    print(f"Database: {config.db_path}")
    print(f"Memo sections: {len(memo.sections)} ({len(unavailable)} unavailable)")
    print(f"Claims: {claim_count}")
    print(f"Citations supplied: {len(memo.citations)}")
    print(f"Invalid citation IDs: {len(memo.invalid_citation_ids)}")

    if verified is not None:
        status_counts = Counter(v.status for v in verified.verifications)
        print("Verification:")
        for status in VerificationStatus:
            print(f"  {status.value}: {status_counts.get(status, 0)}")
        print(f"  overall_status: {verified.overall_status}")
        print(f"  api_calls: {verified.verification_api_calls}")

    print("Outputs:")
    print(f"  memo_json: {json_path}")
    print(f"  memo_md: {md_path}")
    if verification_paths:
        verification_path, verified_json_path, verified_md_path = verification_paths
        print(f"  verification_json: {verification_path}")
        print(f"  verified_memo_json: {verified_json_path}")
        print(f"  verified_memo_md: {verified_md_path}")


def _refresh_invalid_citation_ids(memo: InvestmentMemo, *, financial_fact_count: int) -> None:
    valid_ids = {citation.citation_id for citation in memo.citations}
    valid_ids.update(f"[F{idx}]" for idx in range(1, financial_fact_count + 1))
    used_ids = set()
    for section in memo.sections:
        used_ids.update(re.findall(r"\[[SF]\d+\]", section.content))
        for claim in section.claims:
            used_ids.update(_normalize_citation_id(citation_id) for citation_id in claim.citation_ids)
    memo.invalid_citation_ids = sorted(used_ids - valid_ids)


def _normalize_citation_id(citation_id: str) -> str:
    citation_id = citation_id.strip()
    if re.fullmatch(r"[SF]\d+", citation_id):
        return f"[{citation_id}]"
    return citation_id


if __name__ == "__main__":
    sys.exit(main())
