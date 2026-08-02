"""
Interpretation / threshold layer.

Turns raw ratio values into memo-ready narrative framing (`health_flag` +
`narrative` on each RatioResult), so Role 3 doesn't have to invent its own
"is 1.8 good?" logic per ratio. Thresholds below are conventional
rules-of-thumb, not universal truths -- they're explicitly generic
(industry-agnostic) and should be treated as a starting default a human
analyst can override per sector, not a hard verdict.
"""

from __future__ import annotations

from .schemas import HealthFlag, RatioResult

# (low_concerning, low_watch, high_watch, high_concerning) -- None means no
# bound on that side. A value between low_watch and high_watch is "healthy".
_THRESHOLDS: dict[str, tuple[float | None, float | None, float | None, float | None]] = {
    "current_ratio":       (1.0, 1.2, 3.0, 5.0),
    "quick_ratio":         (0.5, 0.8, None, None),
    "gross_margin":        (0.10, 0.20, None, None),
    "net_margin":          (0.0, 0.05, None, None),
    "roe":                 (0.0, 0.08, 0.30, 0.50),   # very high ROE can flag high leverage, not just strength
    "roa":                 (0.0, 0.03, None, None),
    "debt_to_equity":      (None, None, 1.5, 3.0),
    "interest_coverage":   (1.5, 3.0, None, None),
    "pe_ratio":            (None, None, 40.0, 80.0),
    "pb_ratio":            (None, None, 8.0, 15.0),
    "ev_to_ebitda":        (None, None, 15.0, 25.0),
    "peg_ratio":           (None, None, 2.0, 3.0),
}

_NARRATIVES: dict[str, dict[HealthFlag, str]] = {
    "current_ratio": {
        HealthFlag.CONCERNING: "Current ratio below 1.0 may indicate liquidity pressure -- current liabilities exceed current assets.",
        HealthFlag.WATCH: "Current ratio is on the lower side; worth monitoring alongside cash flow trends.",
        HealthFlag.HEALTHY: "Current ratio suggests adequate short-term liquidity.",
    },
    "quick_ratio": {
        HealthFlag.CONCERNING: "Quick ratio well below 1.0 suggests the company may struggle to cover near-term obligations without selling inventory.",
        HealthFlag.WATCH: "Quick ratio is somewhat low; liquidity relies more heavily on inventory conversion.",
        HealthFlag.HEALTHY: "Quick ratio indicates the company can cover near-term liabilities without relying on inventory.",
    },
    "gross_margin": {
        HealthFlag.CONCERNING: "Gross margin is thin, leaving limited buffer to absorb cost increases.",
        HealthFlag.WATCH: "Gross margin is moderate relative to typical benchmarks.",
        HealthFlag.HEALTHY: "Gross margin suggests solid pricing power or cost control.",
    },
    "net_margin": {
        HealthFlag.CONCERNING: "Net margin is negative or near zero -- the company isn't converting revenue into bottom-line profit.",
        HealthFlag.WATCH: "Net margin is positive but modest.",
        HealthFlag.HEALTHY: "Net margin indicates healthy bottom-line profitability.",
    },
    "roe": {
        HealthFlag.CONCERNING: "Return on equity is low, suggesting weak returns generated on shareholder capital.",
        HealthFlag.WATCH: "ROE is unusually high, which can reflect either strong profitability or elevated leverage amplifying returns -- worth checking debt-to-equity alongside this.",
        HealthFlag.HEALTHY: "Return on equity is within a typically healthy range.",
    },
    "roa": {
        HealthFlag.CONCERNING: "Return on assets is low, suggesting inefficient use of the asset base to generate profit.",
        HealthFlag.WATCH: "ROA is modest.",
        HealthFlag.HEALTHY: "Return on assets indicates efficient use of the company's asset base.",
    },
    "debt_to_equity": {
        HealthFlag.CONCERNING: "Debt-to-equity is elevated, indicating significant reliance on debt financing relative to equity.",
        HealthFlag.WATCH: "Debt-to-equity is moderately elevated -- worth watching alongside interest coverage.",
        HealthFlag.HEALTHY: "Debt-to-equity suggests a conservative capital structure.",
    },
    "interest_coverage": {
        HealthFlag.CONCERNING: "Interest coverage is low, meaning operating income barely covers interest expense -- a red flag if earnings soften.",
        HealthFlag.WATCH: "Interest coverage provides some but not ample cushion over interest obligations.",
        HealthFlag.HEALTHY: "Interest coverage indicates ample cushion to service debt from operating income.",
    },
    "pe_ratio": {
        HealthFlag.CONCERNING: "P/E ratio is very high relative to historical norms, pricing in aggressive growth expectations.",
        HealthFlag.WATCH: "P/E ratio is elevated relative to broad-market norms.",
        HealthFlag.HEALTHY: "P/E ratio is within a range typical of the broader market.",
    },
    "pb_ratio": {
        HealthFlag.CONCERNING: "Price-to-book is very high, implying the market values the company well above its accounting net worth.",
        HealthFlag.WATCH: "Price-to-book is elevated.",
        HealthFlag.HEALTHY: "Price-to-book is within a typical range.",
    },
    "ev_to_ebitda": {
        HealthFlag.CONCERNING: "EV/EBITDA is very high relative to typical benchmarks, suggesting a rich valuation.",
        HealthFlag.WATCH: "EV/EBITDA is somewhat elevated.",
        HealthFlag.HEALTHY: "EV/EBITDA is within a typical range.",
    },
    "peg_ratio": {
        HealthFlag.CONCERNING: "PEG ratio above 2 suggests the stock may be priced well ahead of its expected growth rate.",
        HealthFlag.WATCH: "PEG ratio is somewhat elevated relative to the classic '1.0 is fair value' rule of thumb.",
        HealthFlag.HEALTHY: "PEG ratio suggests valuation is broadly in line with expected growth.",
    },
}


def _classify(name: str, value: float) -> HealthFlag:
    bounds = _THRESHOLDS.get(name)
    if bounds is None:
        return HealthFlag.NOT_APPLICABLE
    low_concern, low_watch, high_watch, high_concern = bounds

    if low_concern is not None and value < low_concern:
        return HealthFlag.CONCERNING
    if low_watch is not None and value < low_watch:
        return HealthFlag.WATCH
    if high_concern is not None and value > high_concern:
        return HealthFlag.CONCERNING
    if high_watch is not None and value > high_watch:
        return HealthFlag.WATCH
    return HealthFlag.HEALTHY


def interpret(ratios: list[RatioResult]) -> list[RatioResult]:
    """Returns new RatioResult objects with `health_flag` and `narrative`
    populated. Ratios that were `computable=False` pass through unchanged
    (flag stays NOT_APPLICABLE) -- interpretation never fabricates a
    judgment about a number that doesn't exist."""
    interpreted = []
    for r in ratios:
        if not r.computable or r.value is None:
            interpreted.append(r)
            continue
        flag = _classify(r.name, r.value)
        narrative = _NARRATIVES.get(r.name, {}).get(flag)
        interpreted.append(r.model_copy(update={"health_flag": flag, "narrative": narrative}))
    return interpreted


if __name__ == "__main__":
    from .schemas import RatioCategory
    sample = [
        RatioResult(name="current_ratio", category=RatioCategory.LIQUIDITY,
                    formula="current_assets / current_liabilities", value=0.87, computable=True),
        RatioResult(name="debt_to_equity", category=RatioCategory.LEVERAGE,
                    formula="total_debt / stockholders_equity", value=1.72, computable=True),
    ]
    for r in interpret(sample):
        print(r.name, r.health_flag, "--", r.narrative)
