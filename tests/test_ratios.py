import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.ratios import compute_ratios  # noqa: E402
from analysis.interpretation import interpret  # noqa: E402
from analysis.schemas import HealthFlag  # noqa: E402


def _meta(ticker="TEST"):
    return SimpleNamespace(ticker=ticker, document_type=SimpleNamespace(value="financial_statement"),
                            source_url="https://example.com", section_id=None, as_of_date=None)


def _stmt(statement_type, line_items, ticker="TEST"):
    return SimpleNamespace(
        statement_type=SimpleNamespace(value=statement_type),
        metadata=_meta(ticker),
        line_items=[SimpleNamespace(name=k, value=v) for k, v in line_items.items()],
    )


def test_full_data_computes_all_categories_with_source_trace():
    statements = [
        _stmt("income_statement", {"total_revenue": 1000, "gross_profit": 400, "net_income": 100,
                                    "operating_income": 150, "interest_expense": 10, "ebitda": None}),
        _stmt("balance_sheet", {"current_assets": 500, "current_liabilities": 300, "inventory": 50,
                                 "total_debt": 200, "stockholders_equity": 400, "total_assets": 900}),
        _stmt("key_stats", {"trailing_pe": 20.0, "price_to_book": 3.0,
                             "enterprise_value": 5000, "ebitda": 300, "peg_ratio": 1.5}),
    ]
    ratios = compute_ratios(statements)
    by_name = {r.name: r for r in ratios}

    assert by_name["current_ratio"].value == round(500 / 300, 4)
    assert by_name["gross_margin"].value == round(400 / 1000, 4)
    assert by_name["debt_to_equity"].value == round(200 / 400, 4)
    assert by_name["pe_ratio"].value == 20.0

    # Every computable ratio must trace back to at least one source
    for r in ratios:
        if r.computable:
            assert len(r.source_line_items) > 0
            assert r.source_line_items[0].ticker == "TEST"


def test_missing_line_item_degrades_gracefully_not_exception():
    statements = [
        _stmt("income_statement", {"total_revenue": None, "gross_profit": 400, "net_income": 100,
                                    "operating_income": 150, "interest_expense": 10, "ebitda": None}),
        _stmt("balance_sheet", {"current_assets": 500, "current_liabilities": 300, "inventory": 50,
                                 "total_debt": 200, "stockholders_equity": 400, "total_assets": 900}),
    ]
    ratios = compute_ratios(statements)
    gross_margin = next(r for r in ratios if r.name == "gross_margin")
    assert gross_margin.computable is False
    assert gross_margin.value is None
    assert gross_margin.note is not None


def test_zero_denominator_does_not_crash():
    statements = [
        _stmt("income_statement", {"total_revenue": 1000, "gross_profit": 400, "net_income": 100,
                                    "operating_income": 150, "interest_expense": 0, "ebitda": None}),
        _stmt("balance_sheet", {"current_assets": 500, "current_liabilities": 300, "inventory": 50,
                                 "total_debt": 200, "stockholders_equity": 400, "total_assets": 900}),
    ]
    ratios = compute_ratios(statements)
    interest_coverage = next(r for r in ratios if r.name == "interest_coverage")
    assert interest_coverage.computable is False  # zero denominator -> None, not inf/crash


def test_financial_company_flags_not_applicable_ratios():
    statements = [
        _stmt("income_statement", {"total_revenue": 1000, "gross_profit": 400, "net_income": 100,
                                    "operating_income": 150, "interest_expense": 10, "ebitda": None}),
        _stmt("balance_sheet", {"current_assets": 500, "current_liabilities": 300, "inventory": 50,
                                 "total_debt": 200, "stockholders_equity": 400, "total_assets": 900}),
    ]
    ratios = compute_ratios(statements, is_financial_company=True)
    by_name = {r.name: r for r in ratios}
    assert by_name["current_ratio"].computable is False
    assert by_name["current_ratio"].health_flag == HealthFlag.NOT_APPLICABLE
    assert "bank" in by_name["current_ratio"].note.lower()
    # Profitability ratios should still compute normally for a financial company
    assert by_name["net_margin"].computable is True


def test_interpretation_flags_concerning_liquidity():
    statements = [
        _stmt("balance_sheet", {"current_assets": 200, "current_liabilities": 500, "inventory": 10,
                                 "total_debt": 100, "stockholders_equity": 300, "total_assets": 800}),
    ]
    ratios = compute_ratios(statements)
    interpreted = interpret(ratios)
    current_ratio = next(r for r in interpreted if r.name == "current_ratio")
    assert current_ratio.health_flag == HealthFlag.CONCERNING
    assert current_ratio.narrative is not None
