#pragma once
#include <string>
#include <vector>
#include <optional>
#include "yfinance_agent.h"
enum class HealthFlag {
    NOT_APPLICABLE,
    CONCERNING,
    WATCH,
    HEALTHY
};
enum class CalculationStatus {
    CALCULATED,
    NOT_APPLICABLE,
    DATA_MISSING,
    NOT_COMPUTABLE
};
struct RatioResult {
    std::string name;
    std::string category;
    std::string formula;
    std::optional<double> value;
    bool computable;
    std::string note;
    std::string health_flag; 
    std::string narrative;   
    CalculationStatus status = CalculationStatus::CALCULATED;
};
class RatioAgent {
public:
    RatioAgent() = default;
    std::vector<RatioResult> compute_ratios(
        const std::vector<FinancialStatement>& statements, 
        const std::string& company_type = ""
    );
};
