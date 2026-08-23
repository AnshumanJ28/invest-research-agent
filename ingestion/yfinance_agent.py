"""
Financial Statements Agent.

Pulls income statement, balance sheet, cash flow, key stats, and historical
price data via yfinance, normalized into schemas.FinancialStatement.

yfinance's biggest failure mode isn't exceptions -- it's silently returning
empty DataFrames or NaN-filled rows for illiquid/small-cap tickers. Every
pull below is defensive: missing fields go into `missing_fields`, not into
a crash, and a company with literally nothing returned still produces a
valid (mostly-empty) FinancialStatement rather than None.

--- India support (NSE/BSE) ---
yfinance addresses Indian equities with a suffix on the raw ticker:
  - NSE: RELIANCE.NS, TCS.NS, INFY.NS
  - BSE: RELIANCE.BO, TCS.BO, INFY.BO
Callers can either pass the suffix directly (e.g. "RELIANCE.NS") or pass a
bare symbol plus exchange="NSE" / exchange="BSE" and let `_normalize_ticker`
append it. US tickers are unaffected (exchange=None, no suffix logic).

Two things are NOT solved by suffixing alone, and are handled explicitly
below:
  1. Currency -- Indian tickers report in INR, not USD. Key-stat and price
     line items now carry the currency yfinance reports (`info["currency"]`
     / `info["financialCurrency"]`) instead of an assumed "USD"/"ratio_or_usd".
  2. Field coverage -- Ind AS filings surface some line items under
     different labels than US GAAP filings (and some fields, like EBITDA,
     are frequently absent for NSE/BSE tickers in yfinance's data). The
     alias lists below have extra Ind-AS-flavored aliases added, but per
     the project notes these are best-effort and NOT yet verified against
     real Indian tickers -- treat `missing_fields` output as the source of
     truth until that verification pass happens.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .schemas import (
    CitationMetadata,
    DocumentType,
    FinancialLineItem,
    FinancialStatement,
    StatementType,
)
from .utils import PRICE_CACHE, retry, safe_get

try:
    import yfinance as yf
except ImportError:  # keeps this module importable/testable without the dep installed
    yf = None


# Exchange -> yfinance ticker suffix. None/omitted means "assume US-listed,
# no suffix" (NYSE/NASDAQ, the original scope).
INDIAN_EXCHANGE_SUFFIXES = {
    "NSE": ".NS",
    "BSE": ".BO",
}


# Field names we expect on the income statement / balance sheet / cash flow.
# yfinance's DataFrame index labels vary by ticker/vintage, hence the alias
# lists. Entries marked "Ind AS (unverified)" are best-guess additions for
# Indian filings and have not yet been checked against live NSE/BSE data --
# see module docstring.
INCOME_STATEMENT_FIELDS = {
    "total_revenue": ["Total Revenue", "Operating Revenue"],  # Operating Revenue: Ind AS (unverified)
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],  # Ind AS (unverified)
    "net_income": ["Net Income", "Net Income Common Stockholders", "Net Income Applicable To Common Shares"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],  # often absent for NSE/BSE tickers in yfinance
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],  # Ind AS (unverified)
    "pretax_income": ["Pretax Income"],
}

BALANCE_SHEET_FIELDS = {
    "total_assets": ["Total Assets"],
    "total_liabilities": ["Total Liabilities Net Minority Interest", "Total Liab"],
    "current_assets": ["Current Assets", "Total Current Assets"],
    "current_liabilities": ["Current Liabilities", "Total Current Liabilities"],
    "inventory": ["Inventory"],
    "total_debt": ["Total Debt"],
    "stockholders_equity": ["Stockholders Equity", "Total Stockholder Equity", "Total Equity Gross Minority Interest"],
    "cash_and_equivalents": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
}

CASH_FLOW_FIELDS = {
    "operating_cash_flow": ["Operating Cash Flow", "Total Cash From Operating Activities"],
    "capital_expenditures": ["Capital Expenditure"],
    "free_cash_flow": ["Free Cash Flow"],
}

KEY_STATS_FIELDS = {
    "market_cap": "marketCap",
    "trailing_pe": "trailingPE",
    "forward_pe": "forwardPE",
    "price_to_book": "priceToBook",
    "peg_ratio": "pegRatio",
    "enterprise_value": "enterpriseValue",
    "ebitda": "ebitda",
    "beta": "beta",
    "dividend_yield": "dividendYield",
    "fifty_two_week_high": "fiftyTwoWeekHigh",
    "fifty_two_week_low": "fiftyTwoWeekLow",
}

# Which KEY_STATS_FIELDS are pure ratios/multiples (currency-agnostic) vs.
# absolute monetary amounts (need a currency unit attached).
KEY_STATS_RATIO_FIELDS = {"trailing_pe", "forward_pe", "price_to_book", "peg_ratio", "beta", "dividend_yield"}


def _normalize_ticker(ticker: str, exchange: str | None = None) -> str:
    """Uppercase/strip a ticker and, if `exchange` is given, ensure the
    correct yfinance suffix is present.

    exchange=None            -> no suffix logic (US-listed, original scope)
    exchange="NSE"/"BSE"     -> appends .NS / .BO if not already present
    Also tolerates a ticker the caller already suffixed themselves (e.g.
    "RELIANCE.NS") passed alongside exchange="NSE" -- it won't double-suffix.
    """
    ticker = ticker.upper().strip()
    if exchange is None:
        return ticker

    exchange = exchange.upper().strip()
    suffix = INDIAN_EXCHANGE_SUFFIXES.get(exchange)
    if suffix is None:
        raise ValueError(
            f"Unknown exchange '{exchange}'; expected one of "
            f"{list(INDIAN_EXCHANGE_SUFFIXES)} or None for US-listed tickers"
        )

    if ticker.endswith(suffix):
        return ticker
    # Strip any other exchange suffix the caller may have mistakenly included
    # (e.g. passed "RELIANCE.BO" with exchange="NSE") before appending ours.
    base = ticker.split(".")[0]
    return f"{base}{suffix}"


def _resolve_currency(info: dict[str, Any]) -> str:
    """Best available currency code for a ticker's monetary fields.
    Falls back to USD only when yfinance gives us nothing to go on."""
    return safe_get(info, "financialCurrency") or safe_get(info, "currency") or "USD"


def _source_meta(ticker: str, as_of: datetime | None = None) -> CitationMetadata:
    # Yahoo Finance's web UI accepts suffixed tickers (RELIANCE.NS, TCS.BO)
    # directly in the quote URL, so no special-casing needed here.
    return CitationMetadata(
        ticker=ticker,
        document_type=DocumentType.FINANCIAL_STATEMENT,
        source_name="yfinance",
        source_url=f"https://finance.yahoo.com/quote/{ticker.upper()}",
        as_of_date=as_of,
    )


def _extract_from_df(df, field_map: dict[str, list[str]], period_label: str, unit: str = "USD") -> tuple[list[FinancialLineItem], list[str]]:
    """Pull the most recent column of a yfinance statement DataFrame into
    FinancialLineItem objects. Returns (items, missing_field_names)."""
    items: list[FinancialLineItem] = []
    missing: list[str] = []

    if df is None or df.empty:
        return items, list(field_map.keys())

    most_recent_col = df.columns[0]
    period_end = most_recent_col if isinstance(most_recent_col, datetime) else None

    for canonical_name, aliases in field_map.items():
        value = None
        for alias in aliases:
            if alias in df.index:
                raw = df.loc[alias, most_recent_col]
                try:
                    value = float(raw) if raw is not None else None
                    if value != value:  # NaN check without importing math here
                        value = None
                except (TypeError, ValueError):
                    value = None
                if value is not None:
                    break
        if value is None:
            missing.append(canonical_name)
        items.append(
            FinancialLineItem(
                name=canonical_name,
                value=value,
                unit=unit,
                period_end=period_end,
            )
        )
    return items, missing


def _fetch_ticker_obj(ticker: str):
    if yf is None:
        raise RuntimeError("yfinance is not installed in this environment")
    return yf.Ticker(ticker)


def fetch_financial_statements(
    ticker: str,
    use_cache: bool = True,
    exchange: str | None = None,
) -> list[FinancialStatement]:
    """
    Returns a list of FinancialStatement objects: income statement, balance
    sheet, cash flow, key stats, and historical price summary. Never raises
    on missing data -- a delisted or thin ticker just yields statements with
    populated `missing_fields`.

    Args:
        ticker: Raw symbol. For US tickers, pass as-is (e.g. "AAPL"). For
            Indian tickers you may either pass the bare NSE/BSE symbol with
            `exchange` set, or pass an already-suffixed symbol directly
            (e.g. "RELIANCE.NS") with exchange left as None.
        exchange: None (default, US-listed / no suffix), "NSE", or "BSE".
    """
    ticker = _normalize_ticker(ticker, exchange=exchange)
    cache_key = f"financials::{ticker}"
    if use_cache:
        cached = PRICE_CACHE.get(cache_key)
        if cached is not None:
            return cached

    tk = _fetch_ticker_obj(ticker)
    fiscal_period = f"FY{datetime.now(timezone.utc).year}"

    import concurrent.futures

    def fetch_one(name):
        try:
            if name == "financials":
                return tk.financials
            elif name == "balance_sheet":
                return tk.balance_sheet
            elif name == "cashflow":
                return tk.cashflow
            elif name == "info":
                return tk.info or {}
            elif name == "history":
                return tk.history(period="1y", interval="1d")
        except Exception as e:
            return e

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        names = ["financials", "balance_sheet", "cashflow", "info", "history"]
        futures = {executor.submit(fetch_one, name): name for name in names}
        fetched = {}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                res = future.result()
                if isinstance(res, Exception):
                    fetched[name] = None
                else:
                    fetched[name] = res
            except Exception:
                fetched[name] = None

    income_df = fetched.get("financials")
    balance_df = fetched.get("balance_sheet")
    cashflow_df = fetched.get("cashflow")
    info = fetched.get("info") or {}
    hist = fetched.get("history")

    fin_currency = info.get("financialCurrency") or info.get("currency") or "USD"
    list_currency = info.get("currency") or "USD"
    results: list[FinancialStatement] = []

    # --- Income statement ---
    items, missing = _extract_from_df(income_df, INCOME_STATEMENT_FIELDS, fiscal_period, unit=fin_currency)
    results.append(FinancialStatement(
        metadata=_source_meta(ticker),
        statement_type=StatementType.INCOME_STATEMENT,
        fiscal_period=fiscal_period,
        line_items=items,
        missing_fields=missing,
    ))

    # --- Balance sheet ---
    items, missing = _extract_from_df(balance_df, BALANCE_SHEET_FIELDS, fiscal_period, unit=fin_currency)
    results.append(FinancialStatement(
        metadata=_source_meta(ticker),
        statement_type=StatementType.BALANCE_SHEET,
        fiscal_period=fiscal_period,
        line_items=items,
        missing_fields=missing,
    ))

    # --- Cash flow ---
    items, missing = _extract_from_df(cashflow_df, CASH_FLOW_FIELDS, fiscal_period, unit=fin_currency)
    results.append(FinancialStatement(
        metadata=_source_meta(ticker),
        statement_type=StatementType.CASH_FLOW,
        fiscal_period=fiscal_period,
        line_items=items,
        missing_fields=missing,
    ))

    # --- Key stats (from .info, which is itself unreliable per-ticker) ---
    stat_items = []
    missing_stats = []
    for canonical_name, raw_key in KEY_STATS_FIELDS.items():
        val = safe_get(info, raw_key)
        if val is None:
            missing_stats.append(canonical_name)
        if canonical_name in KEY_STATS_RATIO_FIELDS:
            unit = "ratio"
        elif canonical_name == "ebitda":
            unit = fin_currency
        else:
            unit = list_currency
        stat_items.append(FinancialLineItem(name=canonical_name, value=val, unit=unit))
    results.append(FinancialStatement(
        metadata=_source_meta(ticker),
        statement_type=StatementType.KEY_STATS,
        fiscal_period="current",
        line_items=stat_items,
        missing_fields=missing_stats,
    ))

    # --- Historical price (delayed, per scope constraints -- no intraday) ---
    price_items = []
    if hist is not None and not hist.empty:
        try:
            last_row = hist.iloc[-1]
            for field in ("Open", "High", "Low", "Close", "Volume"):
                unit = list_currency if field != "Volume" else "shares"
                price_items.append(FinancialLineItem(
                    name=field.lower(),
                    value=float(last_row[field]) if field in last_row else None,
                    unit=unit,
                    period_end=hist.index[-1].to_pydatetime() if hasattr(hist.index[-1], "to_pydatetime") else None,
                ))
        except Exception:  # noqa: BLE001
            pass
    missing_price = [] if price_items else ["all_price_fields"]

    results.append(FinancialStatement(
        metadata=_source_meta(ticker),
        statement_type=StatementType.HISTORICAL_PRICE,
        fiscal_period="trailing_1y_delayed",
        line_items=price_items,
        missing_fields=missing_price,
    ))

    if use_cache:
        PRICE_CACHE.set(cache_key, results)
    return results


if __name__ == "__main__":
    # Manual smoke test:
    #   python -m ingestion.yfinance_agent AAPL
    #   python -m ingestion.yfinance_agent RELIANCE NSE
    #   python -m ingestion.yfinance_agent TCS.BO
    import sys
    tk_symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    tk_exchange = sys.argv[2] if len(sys.argv) > 2 else None
    statements = fetch_financial_statements(tk_symbol, exchange=tk_exchange)
    for s in statements:
        print(f"\n=== {s.statement_type.value} ({s.fiscal_period}) ===")
        print(f"missing fields: {s.missing_fields}")
        for li in s.line_items[:5]:
            print(f"  {li.name}: {li.value} {getattr(li, 'unit', '')}")