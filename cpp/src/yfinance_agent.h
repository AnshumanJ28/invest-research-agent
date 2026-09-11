#pragma once
#include <string>
#include <vector>
#include <map>
#include <optional>
struct FinancialLineItem {
    std::string name;
    std::optional<double> value;
    std::string unit;
};
struct FinancialStatement {
    std::string statement_type; 
    std::string fiscal_period;
    std::vector<FinancialLineItem> line_items;
    std::vector<std::string> missing_fields;
};
class YFinanceAgent {
public:
    YFinanceAgent() = default;
    std::vector<FinancialStatement> fetch_financial_statements(const std::string& ticker);
};
