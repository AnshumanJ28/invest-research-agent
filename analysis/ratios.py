"""
Financial Ratio Agent.

Computes liquidity, profitability, leverage, and valuation ratios from
ingested financial statements. Every RatioResult carries `formula`,
`value`, and `source_line_items` (one SourceRef per input) so a memo claim
citing the ratio can be verified back to specific line items/documents.

--- Note on India support ---
The formulas below are country-agnostic by construction: they operate on
the *canonical* line-item names (`total_revenue`, `stockholders_equity`,
etc.) produced by the ingestion layer, not on raw statement labels. That
means the Ind-AS-vs-US-GAAP label differences (e.g. "Operating Revenue" vs
"Total Revenue") are already resolved upstream in
`ingestion/yfinance_agent.py`'s alias maps -- this module never sees the
raw label, so it needs no changes to compute the same ratios for an NSE/BSE
ticker as for a US one. If an Ind AS field isn't mapped upstream (or simply
isn't reported for a given ticker), `line_item_value()` returns None, the
ratio degrades to `computable=False` via the existing missing-denominator
path below, and no formula-level special-casing is required here.

The one place country *does* matter to this module is company-type
classification for the liquidity/leverage NA-flags (see
`is_financial_company` / `company_type` below) -- India's listed financial
sector is broader than "bank": NBFCs (e.g. Bajaj Finance), housing finance
companies (e.g. LIC Housing Finance), and insurers are common on NSE/BSE
and share the same balance-sheet-structure caveat as banks.

Company-type caveats (flagged via `note`, not silently applied):
  - Banks/financials (including NBFCs, housing finance companies, and
    insurers): current ratio, quick ratio, and standard debt-to-equity are
    not meaningful -- these entities' balance sheets aren't structured
    around a current/non-current split or conventional leverage the way
    the formulas assume (deposits/policy liabilities/borrowings-for-lending
    are the business, not leverage risk in the ordinary sense). This agent
    flags these as `computable=False` / `health_flag=NOT_APPLICABLE` with
    an explanatory note when the company is identified as financial,
    rather than computing a number that would mislead a reader.
  - Zero or missing denominators (e.g. a debt-free company's interest
    coverage, or a missing/unmapped line item for a small-cap or a
    thinly-covered Indian ticker) degrade to `computable=False`, never a
    crash or a fabricated 0.0.
"""

from __future__ import annotations

from typing import Any

from .schemas import HealthFlag, RatioCategory, RatioResult
from .utils import line_item_value, safe_divide, to_source_ref

# Company types (beyond plain "bank") whose balance-sheet structure makes
# current ratio / quick ratio / standard debt-to-equity non-meaningful.
# Indian markets list a wide range of these under one "financials" umbrella
# on NSE/BSE, so callers can pass the specific type instead of just a bool.
FINANCIAL_COMPANY_TYPES = {
    "bank",
    "nbfc",  # Non-Banking Financial Company -- e.g. Bajaj Finance, Muthoot Finance
    "housing_finance",  # e.g. LIC Housing Finance, PNB Housing
    "insurance",
    "diversified_financial",
}


def _make_ratio(
    name: str,
    category: RatioCategory,
    formula: str,
    value: float | None,
    sources: list[Any],
    not_applicable: bool = False,
    na_note: str | None = None,
) -> RatioResult:
    if not_applicable:
        return RatioResult(
            name=name, category=category, formula=formula, value=None,
            source_line_items=[], computable=False,
            note=na_note or f"{name} is not meaningful for this company type.",
            health_flag=HealthFlag.NOT_APPLICABLE,
        )
    if value is None:
        return RatioResult(
            name=name, category=category, formula=formula, value=None,
            source_line_items=[to_source_ref(s.metadata) for s in sources if _has_metadata(s)],
            computable=False,
            note="One or more required line items were missing or the denominator was zero.",
            health_flag=HealthFlag.NOT_APPLICABLE,
        )
    return RatioResult(
        name=name, category=category, formula=formula, value=round(value, 4),
        source_line_items=[to_source_ref(s.metadata) for s in sources if _has_metadata(s)],
        computable=True,
    )


def _has_metadata(stmt: Any) -> bool:
    return hasattr(stmt, "metadata") and stmt.metadata is not None


def _find_stmt(statements: list[Any], statement_type: str) -> Any | None:
    for s in statements:
        st = s.statement_type
        st_val = st.value if hasattr(st, "value") else st
        if st_val == statement_type:
            return s
    return None


def _resolve_is_financial(is_financial_company: bool, company_type: str | None) -> tuple[bool, str | None]:
    """Combines the legacy bool flag with the newer, India-aware
    `company_type` string. Returns (is_financial, matched_type_label)."""
    if company_type:
        normalized = company_type.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in FINANCIAL_COMPANY_TYPES:
            return True, normalized
        if normalized in {"bank", "banking"}:
            return True, "bank"
    if is_financial_company:
        return True, "bank"  # legacy callers only ever meant "bank"
    return False, None
_FX_TO_USD = {
    "USD": 1.0,
    "INR": 83.5,
    "EUR": 0.92,
    "GBP": 0.78,
    "JPY": 155.0,
    "CAD": 1.36,
    "AUD": 1.50,
}


def _convert_currency(val: float, from_curr: str, to_curr: str) -> float:
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()
    if from_curr == to_curr:
        return val
    # Convert from_curr to USD, then USD to to_curr
    usd_val = val / _FX_TO_USD.get(from_curr, 1.0)
    return usd_val * _FX_TO_USD.get(to_curr, 1.0)



def compute_ratios(
    statements: list[Any],
    is_financial_company: bool = False,
    company_type: str | None = None,
) -> list[RatioResult]:
    """
    `statements` is the list[FinancialStatement] produced by
    ingestion.yfinance_agent.fetch_financial_statements(ticker).

    Args:
        is_financial_company: legacy flag, kept for backward compatibility.
            True is treated the same as company_type="bank".
        company_type: optional, more specific classification. One of
            "bank", "nbfc", "housing_finance", "insurance",
            "diversified_financial" (see FINANCIAL_COMPANY_TYPES). Useful
            for Indian tickers where "financial" covers more than banks --
            e.g. company_type="nbfc" for Bajaj Finance, "housing_finance"
            for LIC Housing Finance. If both this and is_financial_company
            are given, either being truthy is sufficient to trigger the NA
            flags below.
    """
    is_financial, matched_type = _resolve_is_financial(is_financial_company, company_type)

    income = _find_stmt(statements, "income_statement")
    balance = _find_stmt(statements, "balance_sheet")
    key_stats = _find_stmt(statements, "key_stats")

    results: list[RatioResult] = []

    def bs(name: str) -> float | None:
        return line_item_value(balance.line_items, name) if balance else None

    def inc(name: str) -> float | None:
        return line_item_value(income.line_items, name) if income else None

    def stat(name: str) -> float | None:
        return line_item_value(key_stats.line_items, name) if key_stats else None

    relevant_stmts = [s for s in (income, balance, key_stats) if s is not None]

    type_label = {
        "bank": "banks",
        "nbfc": "NBFCs",
        "housing_finance": "housing finance companies",
        "insurance": "insurers",
        "diversified_financial": "diversified financial companies",
    }.get(matched_type, "banks/financials")

    # ---------------- Liquidity ----------------
    results.append(_make_ratio(
        "current_ratio", RatioCategory.LIQUIDITY, "current_assets / current_liabilities",
        safe_divide(bs("current_assets"), bs("current_liabilities")), relevant_stmts,
        not_applicable=is_financial,
        na_note=f"Current ratio is not meaningful for {type_label} -- their balance sheets aren't structured around a current/non-current split in the way this ratio assumes.",
    ))
    quick_assets = None
    if bs("current_assets") is not None:
        inv = bs("inventory") or 0.0
        quick_assets = bs("current_assets") - inv
    results.append(_make_ratio(
        "quick_ratio", RatioCategory.LIQUIDITY, "(current_assets - inventory) / current_liabilities",
        safe_divide(quick_assets, bs("current_liabilities")), relevant_stmts,
        not_applicable=is_financial,
        na_note=f"Quick ratio is not meaningful for {type_label}.",
    ))

    # ---------------- Profitability ----------------
    results.append(_make_ratio(
        "gross_margin", RatioCategory.PROFITABILITY, "gross_profit / total_revenue",
        safe_divide(inc("gross_profit"), inc("total_revenue")), relevant_stmts,
    ))
    results.append(_make_ratio(
        "net_margin", RatioCategory.PROFITABILITY, "net_income / total_revenue",
        safe_divide(inc("net_income"), inc("total_revenue")), relevant_stmts,
    ))
    results.append(_make_ratio(
        "roe", RatioCategory.PROFITABILITY, "net_income / stockholders_equity",
        safe_divide(inc("net_income"), bs("stockholders_equity")), relevant_stmts,
    ))
    results.append(_make_ratio(
        "roa", RatioCategory.PROFITABILITY, "net_income / total_assets",
        safe_divide(inc("net_income"), bs("total_assets")), relevant_stmts,
    ))

    # ---------------- Leverage ----------------
    results.append(_make_ratio(
        "debt_to_equity", RatioCategory.LEVERAGE, "total_debt / stockholders_equity",
        safe_divide(bs("total_debt"), bs("stockholders_equity")), relevant_stmts,
        not_applicable=is_financial,
        na_note=f"Standard debt-to-equity conflates deposits/policy liabilities/borrowings-for-lending with leverage for {type_label}; use a regulatory capital ratio (e.g. Tier 1, or RBI-prescribed capital adequacy for Indian NBFCs) instead.",
    ))
    results.append(_make_ratio(
        "interest_coverage", RatioCategory.LEVERAGE, "operating_income / interest_expense",
        safe_divide(inc("operating_income"), inc("interest_expense")), relevant_stmts,
    ))

    # ---------------- Valuation ----------------
    results.append(_make_ratio(
        "pe_ratio", RatioCategory.VALUATION, "market_cap / net_income (trailing)",
        stat("trailing_pe"), relevant_stmts,
    ))
    results.append(_make_ratio(
        "pb_ratio", RatioCategory.VALUATION, "market_cap / stockholders_equity",
        stat("price_to_book"), relevant_stmts,
    ))

    # Currency-adjusted EV/EBITDA calculation
    ev = stat("enterprise_value")

    ebitda_val = stat("ebitda")
    ebitda_stmt = key_stats

    if ebitda_val is None:
        ebitda_val = inc("ebitda")
        ebitda_stmt = income

    if ev is not None and ebitda_val is not None:
        # Find the units (currency) of EV and EBITDA
        ev_unit = "USD"
        ebitda_unit = "USD"
        if key_stats:
            for item in key_stats.line_items:
                if item.name == "enterprise_value" and getattr(item, "unit", None):
                    ev_unit = item.unit.upper()
                    break
        if ebitda_stmt:
            for item in ebitda_stmt.line_items:
                if item.name == "ebitda" and getattr(item, "unit", None):
                    ebitda_unit = item.unit.upper()
                    break
        # Convert ebitda to EV's currency if they differ
        ebitda_val = _convert_currency(ebitda_val, ebitda_unit, ev_unit)
    else:
        ebitda_val = None

    results.append(_make_ratio(
        "ev_to_ebitda", RatioCategory.VALUATION, "enterprise_value / ebitda",
        safe_divide(ev, ebitda_val), relevant_stmts,
    ))
    results.append(_make_ratio(
        "peg_ratio", RatioCategory.VALUATION, "pe_ratio / expected_earnings_growth_rate",
        stat("peg_ratio"), relevant_stmts,
    ))

    return results


if __name__ == "__main__":
    # Manual smoke test with synthetic data (no live ingestion call required)
    from types import SimpleNamespace

    def stmt(statement_type, line_items):
        return SimpleNamespace(
            statement_type=SimpleNamespace(value=statement_type),
            metadata=SimpleNamespace(
                ticker="AAPL", document_type=SimpleNamespace(value="financial_statement"),
                source_url="https://example.com", section_id=None, as_of_date=None,
            ),
            line_items=[SimpleNamespace(name=k, value=v) for k, v in line_items.items()],
        )

    sample = [
        stmt("income_statement", {"total_revenue": 391035, "gross_profit": 180683,
                                   "net_income": 93736, "operating_income": 123216,
                                   "interest_expense": 3933, "ebitda": None}),
        stmt("balance_sheet", {"current_assets": 152987, "current_liabilities": 176392,
                                "inventory": 7286, "total_debt": 106629,
                                "stockholders_equity": 62146, "total_assets": 364980}),
        stmt("key_stats", {"trailing_pe": 32.1, "price_to_book": 48.2,
                            "enterprise_value": 3450000, "ebitda": 130000, "peg_ratio": 2.8}),
    ]
    print("--- Standard company (AAPL) ---")
    for r in compute_ratios(sample):
        print(f"{r.name:20s} {r.value} computable={r.computable} note={r.note}")

    print("\n--- Indian NBFC example (company_type='nbfc') ---")
    for r in compute_ratios(sample, company_type="nbfc"):
        print(f"{r.name:20s} {r.value} computable={r.computable} note={r.note}")