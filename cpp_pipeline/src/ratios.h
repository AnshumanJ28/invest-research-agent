#pragma once

#include <string>
#include <vector>
#include <optional>
#include "yfinance_agent.h"

struct RatioResult {
    std::string name;
    std::string category;
    std::string formula;
    std::optional<double> value;
    bool computable;
    std::string note;
};

class RatioAgent {
public:
    RatioAgent() = default;
    
    // Computes all financial ratios from the given statements
    std::vector<RatioResult> compute_ratios(
        const std::vector<FinancialStatement>& statements, 
        const std::string& company_type = ""
    );
};
