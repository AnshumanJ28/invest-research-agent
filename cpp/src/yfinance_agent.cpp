#include "yfinance_agent.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <thread>
#include <chrono>

using json = nlohmann::json;

std::vector<FinancialStatement> YFinanceAgent::fetch_financial_statements(const std::string& ticker) {
    std::vector<FinancialStatement> statements;
    
    std::string out_path = "json/yf_temp.json";
    std::string cmd = "python python/ingestion/yfinance_json.py " + ticker + " > " + out_path;
    
    // Exponential backoff for API rate limits (e.g. Yahoo Finance 429)
    int ret = -1;
    int max_retries = 3;
    int base_wait_ms = 1000;
    
    for (int attempt = 0; attempt < max_retries; ++attempt) {
        ret = std::system(cmd.c_str());
        if (ret == 0) break;
        
        std::cerr << "  [WARN] Python yfinance script failed (attempt " << (attempt + 1) << "/" << max_retries << "). Retrying..." << std::endl;
        std::this_thread::sleep_for(std::chrono::milliseconds(base_wait_ms * (1 << attempt))); // 1s, 2s, 4s
    }

    if (ret != 0) {
        std::cerr << "[ERROR] Circuit breaker tripped. Failed to execute Python yfinance script after retries." << std::endl;
        return statements;
    }

    std::ifstream file(out_path);
    if (!file.is_open()) {
        std::cerr << "[ERROR] Could not read output from Python yfinance script." << std::endl;
        return statements;
    }

    try {
        json j;
        file >> j;
        
        if (j.is_object() && j.contains("error")) {
            std::cerr << "[ERROR] Python yfinance script returned error: " << j["error"] << std::endl;
            return statements;
        }

        if (j.is_array()) {
            for (const auto& item : j) {
                FinancialStatement stmt;
                stmt.statement_type = item.value("statement_type", "");
                stmt.fiscal_period = item.value("fiscal_period", "");
                
                if (item.contains("missing_fields")) {
                    for (const auto& mf : item["missing_fields"]) {
                        stmt.missing_fields.push_back(mf.get<std::string>());
                    }
                }

                if (item.contains("line_items")) {
                    for (const auto& li : item["line_items"]) {
                        FinancialLineItem fli;
                        fli.name = li.value("name", "");
                        fli.unit = li.value("unit", "");
                        if (li["value"].is_number()) {
                            fli.value = li["value"].get<double>();
                        } else {
                            fli.value = std::nullopt;
                        }
                        stmt.line_items.push_back(fli);
                    }
                }
                statements.push_back(stmt);
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Failed to parse yfinance JSON: " << e.what() << std::endl;
    }

    // Clean up temp file
    std::remove(out_path.c_str());

    return statements;
}
