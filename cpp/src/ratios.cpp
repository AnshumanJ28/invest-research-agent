#include "ratios.h"
#include <cmath>
#include <algorithm>
#include <unordered_map>
#include "fast_ratios.h"

namespace {

    // ── Threshold classification (ported from analysis/interpretation.py) ──
    // Each tuple: (low_concern, low_watch, high_watch, high_concern)
    // -1e308 is used as a sentinel for "no bound" (None in Python).
    constexpr double NO_BOUND = -1e308;

    struct ThresholdBounds {
        double low_concern;
        double low_watch;
        double high_watch;
        double high_concern;
    };

    static const std::unordered_map<std::string, ThresholdBounds> THRESHOLDS = {
        {"current_ratio",     {1.0,   1.2,   3.0,   5.0}},
        {"quick_ratio",       {0.5,   0.8,   NO_BOUND, NO_BOUND}},
        {"gross_margin",      {0.10,  0.20,  NO_BOUND, NO_BOUND}},
        {"net_margin",        {0.0,   0.05,  NO_BOUND, NO_BOUND}},
        {"roe",               {0.0,   0.08,  0.30,  0.50}},
        {"roa",               {0.0,   0.03,  NO_BOUND, NO_BOUND}},
        {"debt_to_equity",    {NO_BOUND, NO_BOUND, 1.5, 3.0}},
        {"interest_coverage", {1.5,   3.0,   NO_BOUND, NO_BOUND}},
        {"pe_ratio",          {NO_BOUND, NO_BOUND, 40.0, 80.0}},
        {"pb_ratio",          {NO_BOUND, NO_BOUND, 8.0,  15.0}},
        {"ev_to_ebitda",      {NO_BOUND, NO_BOUND, 15.0, 25.0}},
        {"peg_ratio",         {NO_BOUND, NO_BOUND, 2.0,  3.0}},
        {"dupont_net_margin", {0.0,   0.05,  NO_BOUND, NO_BOUND}},
        {"dupont_asset_turnover", {0.2, 0.5, NO_BOUND, NO_BOUND}},
        {"dupont_equity_multiplier", {NO_BOUND, NO_BOUND, 2.5, 4.0}},
        {"altman_z_score",    {1.8,   3.0,   NO_BOUND, NO_BOUND}},
    };

    struct NarrativeSet {
        std::string concerning;
        std::string watch;
        std::string healthy;
    };

    static const std::unordered_map<std::string, NarrativeSet> NARRATIVES = {
        {"current_ratio", {
            "Current ratio below 1.0 may indicate liquidity pressure -- current liabilities exceed current assets.",
            "Current ratio is on the lower side; worth monitoring alongside cash flow trends.",
            "Current ratio suggests adequate short-term liquidity."}},
        {"quick_ratio", {
            "Quick ratio well below 1.0 suggests the company may struggle to cover near-term obligations without selling inventory.",
            "Quick ratio is somewhat low; liquidity relies more heavily on inventory conversion.",
            "Quick ratio indicates the company can cover near-term liabilities without relying on inventory."}},
        {"gross_margin", {
            "Gross margin is thin, leaving limited buffer to absorb cost increases.",
            "Gross margin is moderate relative to typical benchmarks.",
            "Gross margin suggests solid pricing power or cost control."}},
        {"net_margin", {
            "Net margin is negative or near zero -- the company isn't converting revenue into bottom-line profit.",
            "Net margin is positive but modest.",
            "Net margin indicates healthy bottom-line profitability."}},
        {"roe", {
            "Return on equity is low, suggesting weak returns generated on shareholder capital.",
            "ROE is unusually high, which can reflect either strong profitability or elevated leverage amplifying returns -- worth checking debt-to-equity alongside this.",
            "Return on equity is within a typically healthy range."}},
        {"roa", {
            "Return on assets is low, suggesting inefficient use of the asset base to generate profit.",
            "ROA is modest.",
            "Return on assets indicates efficient use of the company's asset base."}},
        {"debt_to_equity", {
            "Debt-to-equity is elevated, indicating significant reliance on debt financing relative to equity.",
            "Debt-to-equity is moderately elevated -- worth watching alongside interest coverage.",
            "Debt-to-equity suggests a conservative capital structure."}},
        {"interest_coverage", {
            "Interest coverage is low, meaning operating income barely covers interest expense -- a red flag if earnings soften.",
            "Interest coverage provides some but not ample cushion over interest obligations.",
            "Interest coverage indicates ample cushion to service debt from operating income."}},
        {"pe_ratio", {
            "P/E ratio is very high relative to historical norms, pricing in aggressive growth expectations.",
            "P/E ratio is elevated relative to broad-market norms.",
            "P/E ratio is within a range typical of the broader market."}},
        {"pb_ratio", {
            "Price-to-book is elevated, suggesting a premium valuation or highly intangible asset base.",
            "P/B ratio is above typical market averages.",
            "P/B ratio sits within a standard value-to-growth range."}},
        {"ev_to_ebitda", {
            "EV/EBITDA multiple is very high, leaving little room for execution missteps.",
            "Valuation on an EV/EBITDA basis is somewhat stretched.",
            "EV/EBITDA multiple suggests a reasonable valuation relative to cash generation."}},
        {"peg_ratio", {
            "PEG ratio implies growth is heavily priced in, increasing valuation risk.",
            "PEG ratio is moderately high.",
            "PEG ratio indicates growth is available at a reasonable price (GARP)."}},
        {"dupont_net_margin", {
            "Net margin component of ROE is negative or near zero.",
            "Net margin component of ROE is positive but modest.",
            "Net margin component of ROE is a strong contributor to returns."}},
        {"dupont_asset_turnover", {
            "Asset turnover is low, indicating inefficient asset utilization.",
            "Asset turnover is moderate.",
            "Asset turnover reflects highly efficient use of the asset base."}},
        {"dupont_equity_multiplier", {
            "Equity multiplier is very high, indicating ROE is heavily dependent on leverage.",
            "Equity multiplier shows moderate use of financial leverage.",
            "Equity multiplier indicates ROE is achieved without excessive leverage."}},
        {"altman_z_score", {
            "Altman Z-Score is below 1.8, placing the company in the distress zone with elevated bankruptcy risk.",
            "Altman Z-Score is in the grey zone (1.8 - 3.0); financial health warrants monitoring.",
            "Altman Z-Score is above 3.0, indicating the company is in the safe zone."}}
    };

    std::string health_flag_to_string(HealthFlag flag) {
        switch (flag) {
            case HealthFlag::CONCERNING:     return "CONCERNING";
            case HealthFlag::WATCH:          return "WATCH";
            case HealthFlag::HEALTHY:        return "HEALTHY";
            case HealthFlag::NOT_APPLICABLE: return "NOT_APPLICABLE";
        }
        return "NOT_APPLICABLE";
    }

    HealthFlag classify(const std::string& name, double value) {
        auto it = THRESHOLDS.find(name);
        if (it == THRESHOLDS.end()) return HealthFlag::NOT_APPLICABLE;
        const auto& b = it->second;

        if (b.low_concern != NO_BOUND && value < b.low_concern) return HealthFlag::CONCERNING;
        if (b.low_watch   != NO_BOUND && value < b.low_watch)   return HealthFlag::WATCH;
        if (b.high_concern != NO_BOUND && value > b.high_concern) return HealthFlag::CONCERNING;
        if (b.high_watch  != NO_BOUND && value > b.high_watch)  return HealthFlag::WATCH;
        return HealthFlag::HEALTHY;
    }

    std::string get_narrative(const std::string& name, HealthFlag flag) {
        auto it = NARRATIVES.find(name);
        if (it == NARRATIVES.end()) return "";
        switch (flag) {
            case HealthFlag::CONCERNING: return it->second.concerning;
            case HealthFlag::WATCH:      return it->second.watch;
            case HealthFlag::HEALTHY:    return it->second.healthy;
            default:                     return "";
        }
    }

    // ── Core helpers ──

    std::optional<double> get_line_item(const FinancialStatement* stmt, const std::string& name) {
        if (!stmt) return std::nullopt;
        for (const auto& item : stmt->line_items) {
            if (item.name == name) {
                return item.value;
            }
        }
        return std::nullopt;
    }
    
    const FinancialLineItem* get_line_item_full(const FinancialStatement* stmt, const std::string& name) {
        if (!stmt) return nullptr;
        for (const auto& item : stmt->line_items) {
            if (item.name == name) {
                return &item;
            }
        }
        return nullptr;
    }

    std::optional<double> safe_divide(std::optional<double> num, std::optional<double> den) {
        if (!num.has_value() || !den.has_value() || den.value() == 0.0) {
            return std::nullopt;
        }
        return num.value() / den.value();
    }
    
    static const std::unordered_map<std::string, double> _FX_TO_USD = {
        {"USD", 1.0},
        {"INR", 83.5},
        {"EUR", 0.92},
        {"GBP", 0.78},
        {"JPY", 155.0},
        {"CAD", 1.36},
        {"AUD", 1.50}
    };

    double convert_currency(double val, std::string from_curr, std::string to_curr) {
        std::transform(from_curr.begin(), from_curr.end(), from_curr.begin(), ::toupper);
        std::transform(to_curr.begin(), to_curr.end(), to_curr.begin(), ::toupper);
        if (from_curr == to_curr || from_curr.empty() || to_curr.empty()) return val;
        
        double from_rate = 1.0;
        if (_FX_TO_USD.find(from_curr) != _FX_TO_USD.end()) from_rate = _FX_TO_USD.at(from_curr);
        double to_rate = 1.0;
        if (_FX_TO_USD.find(to_curr) != _FX_TO_USD.end()) to_rate = _FX_TO_USD.at(to_curr);
        
        return (val / from_rate) * to_rate;
    }

    RatioResult make_ratio(
        const std::string& name,
        const std::string& category,
        const std::string& formula,
        std::optional<double> value,
        bool not_applicable = false,
        const std::string& na_note = "",
        const std::string& missing_reason = ""
    ) {
        RatioResult r;
        r.name = name;
        r.category = category;
        r.formula = formula;
        
        if (not_applicable) {
            r.value = std::nullopt;
            r.computable = false;
            r.note = na_note.empty() ? (name + " is not meaningful for this company type.") : na_note;
            r.health_flag = health_flag_to_string(HealthFlag::NOT_APPLICABLE);
            r.status = CalculationStatus::NOT_APPLICABLE;
        } else if (!missing_reason.empty()) {
            r.value = std::nullopt;
            r.computable = false;
            r.note = "DATA_MISSING: " + missing_reason;
            r.health_flag = health_flag_to_string(HealthFlag::NOT_APPLICABLE);
            r.status = CalculationStatus::DATA_MISSING;
        } else if (!value.has_value()) {
            r.value = std::nullopt;
            r.computable = false;
            r.note = "NOT_COMPUTABLE: Denominator zero or missing required derived field.";
            r.health_flag = health_flag_to_string(HealthFlag::NOT_APPLICABLE);
            r.status = CalculationStatus::NOT_COMPUTABLE;
        } else {
            // Round to 4 decimal places
            double rounded = std::round(value.value() * 10000.0) / 10000.0;
            r.value = rounded;
            r.computable = true;
            // Classify and attach narrative
            HealthFlag flag = classify(name, rounded);
            r.health_flag = health_flag_to_string(flag);
            r.narrative = get_narrative(name, flag);
            r.status = CalculationStatus::CALCULATED;
        }
        return r;
    }
}

std::vector<RatioResult> RatioAgent::compute_ratios(
    const std::vector<FinancialStatement>& statements, 
    const std::string& company_type
) {
    bool is_financial = false;
    std::string type_label = "banks/financials";

    std::string norm_type = company_type;
    std::transform(norm_type.begin(), norm_type.end(), norm_type.begin(), ::tolower);
    
    if (norm_type == "bank" || norm_type == "nbfc" || norm_type == "housing_finance" || 
        norm_type == "insurance" || norm_type == "diversified_financial") {
        is_financial = true;
        type_label = norm_type;
    }

    const FinancialStatement* income = nullptr;
    const FinancialStatement* balance = nullptr;
    const FinancialStatement* key_stats = nullptr;

    for (const auto& s : statements) {
        if (s.statement_type == "INCOME_STATEMENT" || s.statement_type == "income_statement") income = &s;
        else if (s.statement_type == "BALANCE_SHEET" || s.statement_type == "balance_sheet") balance = &s;
        else if (s.statement_type == "KEY_STATS" || s.statement_type == "Key Statistics" || s.statement_type == "key_stats") key_stats = &s;
    }

    auto bs = [&](const std::string& name) { return get_line_item(balance, name); };
    auto inc = [&](const std::string& name) { return get_line_item(income, name); };
    auto stat = [&](const std::string& name) { return get_line_item(key_stats, name); };

    // --- Delegate Fallbacks to C Math Engine ---
    auto safe_val = [](std::optional<double> opt) {
        return opt.has_value() ? opt.value() : NAN;
    };

    FinancialInputs c_inputs;
    c_inputs.revenue = safe_val(inc("total_revenue"));
    c_inputs.net_income = safe_val(inc("net_income"));
    c_inputs.operating_income = safe_val(inc("operating_income"));
    c_inputs.ebit = safe_val(inc("ebit"));
    c_inputs.gross_profit = safe_val(inc("gross_profit"));
    c_inputs.operating_expenses = safe_val(inc("operating_expenses"));
    c_inputs.total_assets = safe_val(bs("total_assets"));
    c_inputs.total_equity = safe_val(bs("stockholders_equity"));
    c_inputs.current_assets = safe_val(bs("current_assets"));
    c_inputs.current_liabilities = safe_val(bs("current_liabilities"));
    c_inputs.total_liabilities = safe_val(bs("total_liabilities"));
    c_inputs.retained_earnings = safe_val(bs("retained_earnings"));
    c_inputs.market_cap = safe_val(stat("market_cap"));
    c_inputs.total_debt = safe_val(bs("total_debt"));
    c_inputs.long_term_debt = safe_val(bs("long_term_debt"));
    c_inputs.short_term_debt = safe_val(bs("short_term_debt"));

    apply_financial_fallbacks(&c_inputs);

    auto from_c = [](double v) -> std::optional<double> {
        if (std::isnan(v)) return std::nullopt;
        return v;
    };

    std::optional<double> total_revenue = from_c(c_inputs.revenue);
    std::optional<double> operating_income = from_c(c_inputs.operating_income);
    std::optional<double> total_debt = from_c(c_inputs.total_debt);
    std::optional<double> total_liabilities = from_c(c_inputs.total_liabilities);

    std::vector<RatioResult> results;

    // Liquidity
    results.push_back(make_ratio(
        "current_ratio", "LIQUIDITY", "current_assets / current_liabilities",
        safe_divide(bs("current_assets"), bs("current_liabilities")),
        is_financial,
        "Current ratio is not meaningful for " + type_label
    ));

    std::optional<double> quick_assets = std::nullopt;
    if (bs("current_assets").has_value()) {
        double inv = bs("inventory").value_or(0.0);
        quick_assets = bs("current_assets").value() - inv;
    }

    results.push_back(make_ratio(
        "quick_ratio", "LIQUIDITY", "(current_assets - inventory) / current_liabilities",
        safe_divide(quick_assets, bs("current_liabilities")),
        is_financial,
        "Quick ratio is not meaningful for " + type_label
    ));

    // Profitability
    results.push_back(make_ratio(
        "gross_margin", "PROFITABILITY", "gross_profit / total_revenue",
        safe_divide(inc("gross_profit"), total_revenue),
        is_financial, "Gross margin is not meaningful for " + type_label,
        (!inc("gross_profit").has_value() || !total_revenue.has_value() ? "Missing gross profit or revenue" : "")
    ));
    results.push_back(make_ratio(
        "net_margin", "PROFITABILITY", "net_income / total_revenue",
        safe_divide(inc("net_income"), total_revenue),
        false, "", (!inc("net_income").has_value() || !total_revenue.has_value() ? "Missing net income or revenue" : "")
    ));
    results.push_back(make_ratio(
        "roe", "PROFITABILITY", "net_income / stockholders_equity",
        safe_divide(inc("net_income"), bs("stockholders_equity")),
        false, "", (!inc("net_income").has_value() || !bs("stockholders_equity").has_value() ? "Missing net income or equity" : "")
    ));
    results.push_back(make_ratio(
        "roa", "PROFITABILITY", "net_income / total_assets",
        safe_divide(inc("net_income"), bs("total_assets")),
        false, "", (!inc("net_income").has_value() || !bs("total_assets").has_value() ? "Missing net income or assets" : "")
    ));

    // Leverage
    results.push_back(make_ratio(
        "debt_to_equity", "LEVERAGE", "total_debt / stockholders_equity",
        safe_divide(total_debt, bs("stockholders_equity")),
        is_financial,
        "Standard debt-to-equity is not meaningful for " + type_label,
        (!total_debt.has_value() || !bs("stockholders_equity").has_value() ? "Missing debt or equity" : "")
    ));
    results.push_back(make_ratio(
        "interest_coverage", "LEVERAGE", "operating_income / interest_expense",
        safe_divide(operating_income, inc("interest_expense")),
        is_financial, "Interest coverage is not meaningful for " + type_label,
        (!operating_income.has_value() || !inc("interest_expense").has_value() ? "Missing EBIT or interest exp" : "")
    ));

    // Valuation
    results.push_back(make_ratio(
        "pe_ratio", "VALUATION", "market_cap / net_income (trailing)",
        stat("trailing_pe"),
        false, "", (!stat("trailing_pe").has_value() ? "Missing trailing P/E" : "")
    ));
    results.push_back(make_ratio(
        "pb_ratio", "VALUATION", "market_cap / stockholders_equity",
        stat("price_to_book"),
        false, "", (!stat("price_to_book").has_value() ? "Missing Price to Book" : "")
    ));

    auto ev_item = get_line_item_full(key_stats, "enterprise_value");
    auto ebitda_item = get_line_item_full(key_stats, "ebitda");
    if (!ebitda_item) ebitda_item = get_line_item_full(income, "ebitda");

    std::optional<double> ev_val = ev_item ? ev_item->value : std::nullopt;
    std::optional<double> ebitda_val = ebitda_item ? ebitda_item->value : std::nullopt;

    if (ev_val && ebitda_val) {
        std::string ev_unit = ev_item->unit.empty() ? "USD" : ev_item->unit;
        std::string ebitda_unit = ebitda_item->unit.empty() ? "USD" : ebitda_item->unit;
        ev_val = convert_currency(ev_val.value(), ev_unit, "USD");
        ebitda_val = convert_currency(ebitda_val.value(), ebitda_unit, "USD");
    }

    results.push_back(make_ratio(
        "ev_to_ebitda", "VALUATION", "enterprise_value / ebitda",
        safe_divide(ev_val, ebitda_val),
        is_financial, "EV to EBITDA is not meaningful for " + type_label,
        (!ev_val.has_value() || !ebitda_val.has_value() ? "Missing EV or EBITDA" : "")
    ));
    results.push_back(make_ratio(
        "peg_ratio", "VALUATION", "pe_ratio / expected_earnings_growth_rate",
        stat("peg_ratio"),
        false, "", (!stat("peg_ratio").has_value() ? "Missing PEG ratio" : "")
    ));

    // ==========================================
    // ADVANCED QUANTS (Product Grade)
    // ==========================================

    // 1. DuPont Analysis (ROE Decomposition)
    // ROE = Net Margin * Asset Turnover * Equity Multiplier
    std::optional<double> net_margin = safe_divide(inc("net_income"), total_revenue);
    std::optional<double> asset_turnover = safe_divide(total_revenue, bs("total_assets"));
    std::optional<double> equity_multiplier = safe_divide(bs("total_assets"), bs("stockholders_equity"));

    results.push_back(make_ratio("dupont_net_margin", "DUPONT", "net_income / total_revenue", net_margin, false, "", (!inc("net_income").has_value() || !total_revenue.has_value() ? "Missing net income or revenue" : "")));
    results.push_back(make_ratio("dupont_asset_turnover", "DUPONT", "total_revenue / total_assets", asset_turnover, is_financial, "Asset turnover not typically used for financials", (!total_revenue.has_value() || !bs("total_assets").has_value() ? "Missing revenue or assets" : "")));
    results.push_back(make_ratio("dupont_equity_multiplier", "DUPONT", "total_assets / stockholders_equity", equity_multiplier, is_financial, "Equity multiplier not used for financials", (!bs("total_assets").has_value() || !bs("stockholders_equity").has_value() ? "Missing assets or equity" : "")));

    return results;
}
