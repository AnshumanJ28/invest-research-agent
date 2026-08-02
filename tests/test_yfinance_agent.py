"""Tests for the Financial Statements Agent. Mocks yfinance -- no live network."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
from ingestion import yfinance_agent as agent  # noqa: E402
from ingestion.schemas import StatementType  # noqa: E402


def _mock_ticker(income_df, balance_df, cashflow_df, info, history_df):
    tk = MagicMock()
    tk.financials = income_df
    tk.balance_sheet = balance_df
    tk.cashflow = cashflow_df
    tk.info = info
    tk.history.return_value = history_df
    return tk


def test_full_data_normalizes_correctly():
    income_df = pd.DataFrame({pd.Timestamp("2025-09-30"): {"Total Revenue": 391035000000, "Net Income": 93736000000}})
    balance_df = pd.DataFrame({pd.Timestamp("2025-09-30"): {"Total Assets": 364980000000}})
    cashflow_df = pd.DataFrame({pd.Timestamp("2025-09-30"): {"Operating Cash Flow": 118254000000}})
    info = {"marketCap": 3_400_000_000_000, "trailingPE": 32.1}
    history_df = pd.DataFrame({"Open": [220.0], "High": [222.0], "Low": [219.0], "Close": [221.0], "Volume": [5e7]},
                               index=[pd.Timestamp("2026-07-31")])

    with patch.object(agent, "_fetch_ticker_obj", return_value=_mock_ticker(income_df, balance_df, cashflow_df, info, history_df)):
        results = agent.fetch_financial_statements("AAPL", use_cache=False)

    by_type = {r.statement_type: r for r in results}
    assert by_type[StatementType.INCOME_STATEMENT].line_items[0].value == 391035000000
    assert "total_revenue" not in by_type[StatementType.INCOME_STATEMENT].missing_fields
    assert by_type[StatementType.KEY_STATS].line_items[0].name == "market_cap"


def test_missing_fields_degrade_gracefully_not_exception():
    empty = pd.DataFrame()
    with patch.object(agent, "_fetch_ticker_obj", return_value=_mock_ticker(empty, empty, empty, {}, empty)):
        results = agent.fetch_financial_statements("TINYCAP", use_cache=False)

    # Must not raise, and every statement must explicitly list its gaps
    for stmt in results:
        assert isinstance(stmt.missing_fields, list)
    income = next(r for r in results if r.statement_type == StatementType.INCOME_STATEMENT)
    assert "total_revenue" in income.missing_fields
    assert all(li.value is None for li in income.line_items)


def test_every_statement_carries_citation_metadata():
    empty = pd.DataFrame()
    with patch.object(agent, "_fetch_ticker_obj", return_value=_mock_ticker(empty, empty, empty, {}, empty)):
        results = agent.fetch_financial_statements("MSFT", use_cache=False)
    for stmt in results:
        assert stmt.metadata.ticker == "MSFT"
        assert stmt.metadata.source_name == "yfinance"
