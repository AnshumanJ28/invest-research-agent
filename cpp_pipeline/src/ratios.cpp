#include "ratios.h"
#include <cmath>
#include <algorithm>

namespace {
    std::optional<double> get_line_item(const FinancialStatement* stmt, const std::string& name) {
        if (!stmt) return std::nullopt;
        for (const auto& item : stmt->line_items) {
            if (item.name == name) {
                return item.value;
            }
        }
        return std::nullopt;
    }

    std::optional<double> safe_divide(std::optional<double> num, std::optional<double> den) {
        if (!num.has_value() || !den.has_value() || den.value() == 0.0) {
            return std::nullopt;
        }
        return num.value() / den.value();
    }

    RatioResult make_ratio(
        const std::string& name,
        const std::string& category,
        const std::string& formula,
        std::optional<double> value,
        bool not_applicable = false,
        const std::string& na_note = ""
    ) {
        RatioResult r;
        r.name = name;
        r.category = category;
        r.formula = formula;
        
        if (not_applicable) {
            r.value = std::nullopt;
            r.computable = false;
            r.note = na_note.empty() ? (name + " is not meaningful for this company type.") : na_note;
        } else if (!value.has_value()) {
            r.value = std::nullopt;
            r.computable = false;
            r.note = "One or more required line items were missing or the denominator was zero.";
        } else {
            // Round to 4 decimal places
            r.value = std::round(value.value() * 10000.0) / 10000.0;
            r.computable = true;
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
        if (s.statement_type == "income_statement") income = &s;
        else if (s.statement_type == "balance_sheet") balance = &s;
        else if (s.statement_type == "Key Statistics" || s.statement_type == "key_stats") key_stats = &s;
    }

    auto bs = [&](const std::string& name) { return get_line_item(balance, name); };
    auto inc = [&](const std::string& name) { return get_line_item(income, name); };
    auto stat = [&](const std::string& name) { return get_line_item(key_stats, name); };

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
        safe_divide(inc("gross_profit"), inc("total_revenue"))
    ));
    results.push_back(make_ratio(
        "net_margin", "PROFITABILITY", "net_income / total_revenue",
        safe_divide(inc("net_income"), inc("total_revenue"))
    ));
    results.push_back(make_ratio(
        "roe", "PROFITABILITY", "net_income / stockholders_equity",
        safe_divide(inc("net_income"), bs("stockholders_equity"))
    ));
    results.push_back(make_ratio(
        "roa", "PROFITABILITY", "net_income / total_assets",
        safe_divide(inc("net_income"), bs("total_assets"))
    ));

    // Leverage
    results.push_back(make_ratio(
        "debt_to_equity", "LEVERAGE", "total_debt / stockholders_equity",
        safe_divide(bs("total_debt"), bs("stockholders_equity")),
        is_financial,
        "Standard debt-to-equity is not meaningful for " + type_label
    ));
    results.push_back(make_ratio(
        "interest_coverage", "LEVERAGE", "operating_income / interest_expense",
        safe_divide(inc("operating_income"), inc("interest_expense"))
    ));

    // Valuation
    results.push_back(make_ratio(
        "pe_ratio", "VALUATION", "market_cap / net_income (trailing)",
        stat("trailing_pe")
    ));
    results.push_back(make_ratio(
        "pb_ratio", "VALUATION", "market_cap / stockholders_equity",
        stat("price_to_book")
    ));

    std::optional<double> ev = stat("enterprise_value");
    std::optional<double> ebitda_val = stat("ebitda");
    if (!ebitda_val.has_value()) {
        ebitda_val = inc("ebitda");
    }

    results.push_back(make_ratio(
        "ev_to_ebitda", "VALUATION", "enterprise_value / ebitda",
        safe_divide(ev, ebitda_val)
    ));
    results.push_back(make_ratio(
        "peg_ratio", "VALUATION", "pe_ratio / expected_earnings_growth_rate",
        stat("peg_ratio")
    ));

    return results;
}
