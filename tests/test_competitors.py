import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.competitors import build_peer_snapshot, compare_peers, select_peers  # noqa: E402
from analysis.ratios import compute_ratios  # noqa: E402


def _stmt(statement_type, line_items):
    return SimpleNamespace(
        statement_type=SimpleNamespace(value=statement_type),
        metadata=SimpleNamespace(ticker="X", document_type=SimpleNamespace(value="financial_statement"),
                                  source_url=None, section_id=None, as_of_date=None),
        line_items=[SimpleNamespace(name=k, value=v) for k, v in line_items.items()],
    )


def _sample_statements():
    return [
        _stmt("income_statement", {"total_revenue": 1000, "gross_profit": 400, "net_income": 100,
                                    "operating_income": 150, "interest_expense": 10, "ebitda": None}),
        _stmt("balance_sheet", {"current_assets": 500, "current_liabilities": 300, "inventory": 50,
                                 "total_debt": 200, "stockholders_equity": 400, "total_assets": 900}),
        _stmt("key_stats", {"trailing_pe": 20.0, "price_to_book": 3.0,
                             "enterprise_value": 5000, "ebitda": 300, "peg_ratio": 1.5}),
    ]


def test_select_peers_filters_by_industry():
    pool = [
        {"ticker": "AAA", "industry": "Software"},
        {"ticker": "BBB", "industry": "Software"},
        {"ticker": "CCC", "industry": "Semiconductors"},
        {"ticker": "DDD", "industry": "Software"},
    ]
    peers = select_peers("Software", pool, max_peers=2)
    assert peers == ["AAA", "BBB"]


def test_build_peer_snapshot_handles_missing_ingestion_function():
    snapshot = build_peer_snapshot("PEER", fetch_statements=None)
    assert snapshot.data_available is False
    assert "No ingestion function" in snapshot.unavailable_reason


def test_build_peer_snapshot_handles_ingestion_failure_gracefully():
    def failing_fetch(ticker):
        raise ConnectionError("network unreachable")

    snapshot = build_peer_snapshot("PEER", fetch_statements=failing_fetch)
    assert snapshot.data_available is False
    assert "Ingestion call failed" in snapshot.unavailable_reason


def test_build_peer_snapshot_success_computes_ratios():
    snapshot = build_peer_snapshot("PEER", fetch_statements=lambda t: _sample_statements())
    assert snapshot.data_available is True
    assert any(r.name == "current_ratio" for r in snapshot.ratios)


def test_compare_peers_one_missing_does_not_break_the_table():
    def fetch(ticker):
        if ticker == "MISSING":
            raise RuntimeError("ingestion not yet run for this ticker")
        return _sample_statements()

    primary_ratios = compute_ratios(_sample_statements())
    comparison = compare_peers("PRIMARY", primary_ratios, ["OK_PEER", "MISSING"], fetch)

    peer_status = {p.ticker: p.data_available for p in comparison.peers}
    assert peer_status["OK_PEER"] is True
    assert peer_status["MISSING"] is False

    # The comparison table must still include a row for every ratio, with
    # None (not a crash, not a dropped key) for the missing peer's column
    assert comparison.comparison_table["current_ratio"]["MISSING"] is None
    assert comparison.comparison_table["current_ratio"]["OK_PEER"] is not None
    assert comparison.comparison_table["current_ratio"]["PRIMARY"] is not None
