"""SQLite source loading and source-aware chunking for Role 3.

This module only prepares chunk objects and deterministic financial facts. It
does not create embeddings, run retrieval, call an LLM, or modify SQLite.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from .schemas import Chunk, FinancialFact, SourceType

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "cpp_pipeline" / "invest.sqlite"
DEFAULT_MAX_CHARS = 2400


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the SQLite database in read-only style from the caller's path."""

    conn = sqlite3.connect(Path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_filing_chunks(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Load filing section rows and convert each natural section unit to chunks."""

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, filing_type, filed_date, section_name, text
            FROM filing_sections
            ORDER BY ticker, filed_date, id
            """
        ).fetchall()

    chunks: list[Chunk] = []
    for row in rows:
        metadata = {
            "source_table": "filing_sections",
            "filing_type": row["filing_type"],
            "filed_date": row["filed_date"],
            "section_name": row["section_name"],
        }
        chunks.extend(
            _chunks_from_text(
                text=row["text"],
                source_type="filing",
                source_id=str(row["id"]),
                ticker=row["ticker"],
                section=row["section_name"],
                title=None,
                speaker=None,
                source_url=None,
                published_at=_parse_datetime(row["filed_date"]),
                metadata=metadata,
                max_chars=max_chars,
            )
        )
    return chunks


def load_news_chunks(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Load news rows; returns [] cleanly when the table is empty."""

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, title, source_publication, published_at, url, snippet
            FROM news_articles
            ORDER BY ticker, published_at DESC, id
            """
        ).fetchall()

    chunks: list[Chunk] = []
    for row in rows:
        text = _join_present([row["title"], row["snippet"]])
        metadata = {
            "source_table": "news_articles",
            "source_publication": row["source_publication"],
        }
        chunks.extend(
            _chunks_from_text(
                text=text,
                source_type="news",
                source_id=str(row["id"]),
                ticker=row["ticker"],
                section=None,
                title=row["title"],
                speaker=None,
                source_url=row["url"],
                published_at=_parse_datetime(row["published_at"]),
                metadata=metadata,
                max_chars=max_chars,
            )
        )
    return chunks


def load_transcript_chunks(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Load transcript speaker turns; returns [] cleanly when the table is empty."""

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, speaker, section, text
            FROM transcript_utterances
            ORDER BY ticker, id
            """
        ).fetchall()

    chunks: list[Chunk] = []
    for row in rows:
        metadata = {
            "source_table": "transcript_utterances",
            "section": row["section"],
        }
        chunks.extend(
            _chunks_from_text(
                text=row["text"],
                source_type="transcript",
                source_id=str(row["id"]),
                ticker=row["ticker"],
                section=row["section"],
                title=None,
                speaker=row["speaker"],
                source_url=None,
                published_at=None,
                metadata=metadata,
                max_chars=max_chars,
            )
        )
    return chunks


def build_all_chunks(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Load all narrative evidence chunks from source-specific tables."""

    return [
        *load_filing_chunks(db_path, max_chars=max_chars),
        *load_news_chunks(db_path, max_chars=max_chars),
        *load_transcript_chunks(db_path, max_chars=max_chars),
    ]


def load_financial_facts(db_path: str | Path = DEFAULT_DB_PATH) -> list[FinancialFact]:
    """Return financial statement line items as structured deterministic facts."""

    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, statement_type, fiscal_period, line_items
            FROM financial_statements
            ORDER BY ticker, statement_type, fiscal_period, id
            """
        ).fetchall()

    facts: list[FinancialFact] = []
    for row in rows:
        line_items = json.loads(row["line_items"])
        for idx, item in enumerate(line_items, start=1):
            name = item.get("name", f"line_item_{idx}")
            facts.append(
                FinancialFact(
                    fact_id=_make_id(
                        "financial",
                        row["ticker"],
                        row["id"],
                        row["statement_type"],
                        row["fiscal_period"],
                        name,
                    ),
                    ticker=row["ticker"],
                    statement_id=row["id"],
                    statement_type=row["statement_type"],
                    fiscal_period=row["fiscal_period"],
                    name=name,
                    value=item.get("value"),
                    unit=item.get("unit"),
                    metadata={
                        "source_table": "financial_statements",
                        "line_item_index": idx,
                    },
                )
            )
    return facts


def _chunks_from_text(
    *,
    text: str | None,
    source_type: SourceType,
    source_id: str,
    ticker: str,
    section: str | None,
    title: str | None,
    speaker: str | None,
    source_url: str | None,
    published_at: datetime | None,
    metadata: dict[str, Any],
    max_chars: int,
) -> list[Chunk]:
    clean_text = _normalize_text(text)
    if not clean_text:
        return []

    parts = split_long_text(clean_text, max_chars=max_chars)
    total_parts = len(parts)
    chunks: list[Chunk] = []
    for idx, part in enumerate(parts, start=1):
        part_metadata = {
            **metadata,
            "split_index": idx,
            "split_count": total_parts,
        }
        chunks.append(
            Chunk(
                chunk_id=_make_id(source_type, ticker, source_id, section, title, speaker, idx),
                ticker=ticker,
                text=part,
                source_type=source_type,
                source_id=source_id,
                section=section,
                title=title,
                speaker=speaker,
                source_url=source_url,
                published_at=published_at,
                metadata=part_metadata,
            )
        )
    return chunks


def split_long_text(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Split only when needed, preferring paragraphs and sentence boundaries."""

    text = _normalize_text(text)
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    current = ""
    for unit in _natural_units(text):
        if len(unit) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.extend(_split_oversized_unit(unit, max_chars=max_chars))
            continue
        candidate = f"{current} {unit}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = unit
    if current:
        parts.append(current)
    return parts


def _natural_units(text: str) -> Iterable[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _split_oversized_unit(text: str, *, max_chars: int) -> list[str]:
    words = text.split()
    parts: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = word
    if current:
        parts.append(current)
    return parts


def _make_id(*parts: object) -> str:
    raw = "_".join(str(p) for p in parts if p not in (None, ""))
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", raw)).strip("_").lower()


def _normalize_text(text: str | None) -> str:
    if text is None:
        return ""
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()


def _join_present(parts: Iterable[str | None]) -> str:
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
