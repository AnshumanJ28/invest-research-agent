"""
Competitor Comparison Agent.

Peer identification: uses yfinance's `sector` / `industry` fields (already
pulled via ingestion) rather than a hardcoded ticker->peer mapping, which
would go stale the moment a company changes segments or a new competitor
IPOs. This is a genuine dependency on ingestion having already run for
candidate peers -- see the Loop 3 Observation in the source prompt: if
ingestion hasn't been run for a peer ticker, this agent must degrade
gracefully (`PeerSnapshot(data_available=False, ...)`), not assume the data
will always be there.

Peer CANDIDATE discovery (same industry, different ticker) still needs an
external list to choose from -- this agent accepts a `candidate_tickers`
argument rather than inventing a scraper for "who are Apple's competitors,"
since that's exactly the kind of fragile mapping this design is trying to
avoid. In production, Role 3/orchestration would supply this list (e.g.
from a sector/industry lookup service or a maintained watchlist), which is
flagged as an explicit upstream dependency below.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .ratios import compute_ratios
from .schemas import CompetitorComparison, PeerSnapshot
from .sentiment import aggregate_sentiment, score_news_batch, score_transcript


def select_peers(
    primary_industry: str,
    candidate_pool: list[dict[str, Any]],
    max_peers: int = 3,
) -> list[str]:
    """
    `candidate_pool` is a list of {"ticker": str, "industry": str} dicts --
    e.g. pre-fetched via yfinance .info["industry"] for a watchlist universe.
    Selects up to `max_peers` tickers sharing the primary ticker's industry.

    KNOWN DEPENDENCY: this function does NOT crawl for candidates itself --
    it expects `candidate_pool` to already exist (built from ingestion runs
    or a maintained universe list). Flagged explicitly per Loop 3's
    Observation rather than assumed away.
    """
    matches = [c["ticker"] for c in candidate_pool if c.get("industry") == primary_industry]
    return matches[:max_peers]


def build_peer_snapshot(
    ticker: str,
    fetch_statements: Callable[[str], list[Any]] | None,
    is_financial_company: bool = False,
) -> PeerSnapshot:
    """
    `fetch_statements` should be ingestion.yfinance_agent.fetch_financial_statements
    (injected as a callable so this module doesn't hard-import ingestion,
    keeping analysis testable in isolation -- see README_analysis.md).

    If `fetch_statements` is None, or raises, or returns nothing usable,
    this returns PeerSnapshot(data_available=False, ...) rather than letting
    a single missing peer crash the whole comparison.
    """
    if fetch_statements is None:
        return PeerSnapshot(ticker=ticker, data_available=False,
                             unavailable_reason="No ingestion function was provided for peer data.")
    try:
        statements = fetch_statements(ticker)
    except Exception as exc:  # noqa: BLE001
        return PeerSnapshot(ticker=ticker, data_available=False,
                             unavailable_reason=f"Ingestion call failed: {exc}")
    if not statements:
        return PeerSnapshot(ticker=ticker, data_available=False,
                             unavailable_reason="Ingestion returned no statements for this ticker.")

    ratios = compute_ratios(statements, is_financial_company=is_financial_company)
    return PeerSnapshot(ticker=ticker, ratios=ratios, data_available=True)


def compare_peers(
    primary_ticker: str,
    primary_ratios: list[Any],
    peer_tickers: list[str],
    fetch_statements: Callable[[str], list[Any]] | None,
    peer_selection_method: str = "same yfinance industry classification",
    is_financial_company: bool = False,
) -> CompetitorComparison:
    peers = [
        build_peer_snapshot(t, fetch_statements, is_financial_company=is_financial_company)
        for t in peer_tickers
    ]

    ratio_names = {r.name for r in primary_ratios}
    for p in peers:
        ratio_names |= {r.name for r in p.ratios}

    table: dict[str, dict[str, Optional[float]]] = {}
    for name in sorted(ratio_names):
        row: dict[str, Optional[float]] = {}
        primary_match = next((r for r in primary_ratios if r.name == name), None)
        row[primary_ticker] = primary_match.value if primary_match else None
        for p in peers:
            if not p.data_available:
                row[p.ticker] = None
                continue
            peer_match = next((r for r in p.ratios if r.name == name), None)
            row[p.ticker] = peer_match.value if peer_match else None
        table[name] = row

    return CompetitorComparison(
        primary_ticker=primary_ticker,
        peers=peers,
        peer_selection_method=peer_selection_method,
        comparison_table=table,
    )


if __name__ == "__main__":
    # Smoke test: primary has data, one peer has data, one peer is unavailable
    from types import SimpleNamespace

    def stmt(statement_type, line_items):
        return SimpleNamespace(
            statement_type=SimpleNamespace(value=statement_type),
            metadata=SimpleNamespace(ticker="X", document_type=SimpleNamespace(value="financial_statement"),
                                      source_url=None, section_id=None, as_of_date=None),
            line_items=[SimpleNamespace(name=k, value=v) for k, v in line_items.items()],
        )

    def fake_fetch(ticker: str):
        if ticker == "PEERB":
            raise RuntimeError("ingestion not yet run for this ticker")
        return [
            stmt("income_statement", {"total_revenue": 1000, "gross_profit": 400, "net_income": 100,
                                       "operating_income": 150, "interest_expense": 10, "ebitda": None}),
            stmt("balance_sheet", {"current_assets": 500, "current_liabilities": 300, "inventory": 50,
                                    "total_debt": 200, "stockholders_equity": 400, "total_assets": 900}),
            stmt("key_stats", {"trailing_pe": 20.0, "price_to_book": 3.0,
                                "enterprise_value": 5000, "ebitda": 300, "peg_ratio": 1.5}),
        ]

    primary_stmts = fake_fetch("PRIMARY")
    primary_ratios = compute_ratios(primary_stmts)
    comparison = compare_peers("PRIMARY", primary_ratios, ["PEERA", "PEERB"], fake_fetch)
    print("peers data_available:", [(p.ticker, p.data_available, p.unavailable_reason) for p in comparison.peers])
    print("current_ratio row:", comparison.comparison_table["current_ratio"])
