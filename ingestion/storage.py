"""
Storage layer.

Choice: PostgreSQL over MongoDB.

Justification -- this pipeline's data is NOT uniformly unstructured, and
that's the deciding factor:
  - Financial statements and key stats are genuinely tabular/structured
    (fixed line items, numeric values) -- a natural fit for relational
    columns, and Role 2's ratio agent will want to query/join/aggregate
    these numerically (e.g. "average current ratio across peers"), which
    Postgres does far more naturally than Mongo's aggregation pipeline.
  - Filing sections, transcript utterances, and news articles are
    semi-structured text blobs, but Postgres's JSONB columns handle that
    fine while still letting the CitationMetadata fields (ticker, url,
    section_id, retrieved_at) live as real indexed columns -- so "find
    every section from AAPL's most recent 10-K" is a normal indexed query,
    not a full collection scan.
  - Postgres full-text search (tsvector) covers the "search across filing
    text / news snippets" need without introducing a second datastore.
  - A single relational schema is easier for Role 2 and Role 3 to reason
    about when reconstructing a citation across statement + filing +
    transcript + news in one query, which is exactly the join-heavy
    access pattern this pipeline needs.

MongoDB would be the better call if the data were mostly free-form
documents with no numeric analysis burden -- it isn't, here.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .schemas import FilingDocument, FinancialStatement, NewsArticle, TranscriptDocument

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None


DDL = """
CREATE TABLE IF NOT EXISTS financial_statements (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    statement_type TEXT NOT NULL,
    fiscal_period TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    retrieved_at TIMESTAMPTZ NOT NULL,
    line_items JSONB NOT NULL,
    missing_fields JSONB NOT NULL,
    UNIQUE (ticker, statement_type, fiscal_period)
);
CREATE INDEX IF NOT EXISTS idx_fin_stmt_ticker ON financial_statements (ticker);

CREATE TABLE IF NOT EXISTS filing_sections (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    filing_type TEXT NOT NULL,
    accession_number TEXT NOT NULL,
    filed_date TIMESTAMPTZ NOT NULL,
    section_name TEXT NOT NULL,
    section_id TEXT NOT NULL,
    paragraph_index INT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    text TEXT NOT NULL,
    text_search tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    UNIQUE (ticker, accession_number, section_id)
);
CREATE INDEX IF NOT EXISTS idx_filing_ticker ON filing_sections (ticker, filing_type);
CREATE INDEX IF NOT EXISTS idx_filing_text_search ON filing_sections USING GIN (text_search);

CREATE TABLE IF NOT EXISTS transcript_utterances (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    fiscal_quarter TEXT,
    call_date TIMESTAMPTZ,
    available BOOLEAN NOT NULL,
    unavailable_reason TEXT,
    speaker TEXT,
    section TEXT,
    sequence INT,
    section_id TEXT,
    source_url TEXT,
    retrieved_at TIMESTAMPTZ,
    text TEXT
);
CREATE INDEX IF NOT EXISTS idx_transcript_ticker ON transcript_utterances (ticker, fiscal_quarter);

CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    title TEXT NOT NULL,
    source_publication TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    url TEXT NOT NULL,
    snippet TEXT,
    dedupe_key TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    UNIQUE (dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_articles (ticker, published_at);
"""


class Storage:
    def __init__(self, dsn: str):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is not installed in this environment")
        self.conn = psycopg2.connect(dsn)
        self.conn.autocommit = True

    def init_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(DDL)

    def write_financial_statement(self, stmt: FinancialStatement) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO financial_statements
                    (ticker, statement_type, fiscal_period, source_name, source_url,
                     retrieved_at, line_items, missing_fields)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, statement_type, fiscal_period) DO UPDATE SET
                    line_items = EXCLUDED.line_items,
                    missing_fields = EXCLUDED.missing_fields,
                    retrieved_at = EXCLUDED.retrieved_at
                """,
                (
                    stmt.metadata.ticker,
                    stmt.statement_type.value,
                    stmt.fiscal_period,
                    stmt.metadata.source_name,
                    stmt.metadata.source_url,
                    stmt.metadata.retrieved_at,
                    json.dumps([li.model_dump(mode="json") for li in stmt.line_items]),
                    json.dumps(stmt.missing_fields),
                ),
            )

    def write_filing(self, filing: FilingDocument) -> None:
        with self.conn.cursor() as cur:
            rows = [
                (
                    filing.ticker,
                    filing.filing_type,
                    filing.accession_number,
                    filing.filed_date,
                    section.section_name,
                    section.metadata.section_id,
                    section.paragraph_index,
                    section.metadata.source_url,
                    section.metadata.retrieved_at,
                    section.text,
                )
                for section in filing.sections
            ]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO filing_sections
                    (ticker, filing_type, accession_number, filed_date, section_name,
                     section_id, paragraph_index, source_url, retrieved_at, text)
                VALUES %s
                ON CONFLICT (ticker, accession_number, section_id) DO NOTHING
                """,
                rows,
            )

    def write_transcript(self, transcript: TranscriptDocument) -> None:
        with self.conn.cursor() as cur:
            if not transcript.available:
                cur.execute(
                    """
                    INSERT INTO transcript_utterances
                        (ticker, fiscal_quarter, call_date, available, unavailable_reason)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (transcript.ticker, transcript.fiscal_quarter, transcript.call_date,
                     False, transcript.unavailable_reason),
                )
                return
            rows = [
                (
                    transcript.ticker, transcript.fiscal_quarter, transcript.call_date, True, None,
                    u.speaker, u.section.value, u.sequence, u.metadata.section_id,
                    u.metadata.source_url, u.metadata.retrieved_at, u.text,
                )
                for u in transcript.utterances
            ]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO transcript_utterances
                    (ticker, fiscal_quarter, call_date, available, unavailable_reason,
                     speaker, section, sequence, section_id, source_url, retrieved_at, text)
                VALUES %s
                """,
                rows,
            )

    def write_news(self, articles: list[NewsArticle]) -> None:
        if not articles:
            return
        with self.conn.cursor() as cur:
            rows = [
                (
                    a.metadata.ticker, a.title, a.source_publication, a.published_at,
                    a.url, a.snippet, a.dedupe_key, a.metadata.retrieved_at,
                )
                for a in articles
            ]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO news_articles
                    (ticker, title, source_publication, published_at, url, snippet,
                     dedupe_key, retrieved_at)
                VALUES %s
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                rows,
            )

    def reconstruct_citation(self, table: str, row_id: int) -> dict[str, Any] | None:
        """Sanity-check helper: given any row, return enough fields to build
        a full citation (source, section, date, URL). Used in tests to prove
        nothing was dropped between agent output and storage."""
        allowed = {"financial_statements", "filing_sections", "transcript_utterances", "news_articles"}
        if table not in allowed:
            raise ValueError(f"unknown table {table}")
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT * FROM {table} WHERE id = %s", (row_id,))  # noqa: S608 -- table is allow-listed above
            return cur.fetchone()
