#include <iostream>
#include <string>
#include <cstdlib>
#include <cctype>
#include "news_agent.h"
#include "yfinance_agent.h"
#include "ratios.h"
#include "sentiment.h"
#include "storage.h"
#include "cache_utils.h"
#include "fast_ratios.h"
#include "json_snapshot_writer.h"

// Simple .env parser for C++
#include <fstream>
#include <sstream>
#include <map>
#include <future>
#include <thread>
#include <chrono>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

std::string trim(const std::string& str) {
    size_t first = str.find_first_not_of(" \r\n\t");
    if (first == std::string::npos) return "";
    size_t last = str.find_last_not_of(" \r\n\t");
    return str.substr(first, (last - first + 1));
}

std::map<std::string, std::string> load_env(const std::string& path) {
    std::map<std::string, std::string> env;
    std::ifstream file(path);
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        auto pos = line.find('=');
        if (pos != std::string::npos) {
            std::string key = trim(line.substr(0, pos));
            std::string val = trim(line.substr(pos + 1));
            env[key] = val;
        }
    }
    return env;
}

bool is_safe_ticker(const std::string& ticker) {
    if (ticker.empty() || ticker.size() > 25) return false;
    for (char ch : ticker) {
        unsigned char uch = static_cast<unsigned char>(ch);
        if (!std::isalnum(uch) && ch != '.' && ch != '_' && ch != '-') {
            return false;
        }
    }
    return true;
}

bool env_flag_enabled(const std::map<std::string, std::string>& env, const std::string& name) {
    auto found = env.find(name);
    if (found == env.end()) return false;
    std::string value = found->second;
    for (char& ch : value) {
        ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    }
    return value == "1" || value == "true" || value == "yes" || value == "on";
}

// ── Locate project root relative to CWD ──
std::string find_project_root() {
    // Try common CWD positions: project_root, cpp/, cpp/build*/
    for (const auto& candidate : {".", "..", "../..", "../../.."}) {
        std::string test = std::string(candidate) + "/.env";
        if (std::ifstream(test).good()) return candidate;
    }
    return ".."; // fallback
}

std::string find_env_path() {
    for (const auto& candidate : {".env", "../.env", "../../.env"}) {
        if (std::ifstream(candidate).good()) return candidate;
    }
    return "../.env"; // fallback
}

// ── Parse unified fetch JSON into C++ structs ──
std::vector<FinancialStatement> parse_yfinance_json(const json& root_json) {
    std::vector<FinancialStatement> statements;
    if (!root_json.is_object() || !root_json.contains("quoteSummary") || !root_json["quoteSummary"].contains("result") || !root_json["quoteSummary"]["result"].is_array() || root_json["quoteSummary"]["result"].empty()) {
        return statements;
    }
    auto result = root_json["quoteSummary"]["result"][0];

    auto extract_items = [](const json& report, const std::map<std::string, std::vector<std::string>>& field_map, const std::string& type, std::vector<FinancialStatement>& stmts) {
        if (!report.is_object()) return;
        FinancialStatement stmt;
        stmt.statement_type = type;
        stmt.fiscal_period = report.contains("endDate") && report["endDate"].is_object() && report["endDate"].contains("fmt") ? report["endDate"]["fmt"].get<std::string>() : "";
        
        for (const auto& pair : field_map) {
            std::string canonical = pair.first;
            bool found = false;
            for (const std::string& yf_key : pair.second) {
                if (report.contains(yf_key) && report[yf_key].is_object() && report[yf_key].contains("raw")) {
                    // Skip fields where fmt is null — Yahoo Finance uses {raw: 0, fmt: null}
                    // to indicate the data point is genuinely missing (e.g. Gross Profit for banks).
                    if (report[yf_key].contains("fmt") && report[yf_key]["fmt"].is_null()) {
                        // Treat as DATA_MISSING: do not push into line_items
                        break;
                    }
                    stmt.line_items.push_back({canonical, report[yf_key]["raw"].get<double>(), "USD"});
                    found = true;
                    break;
                }
            }
            if (!found) {
                stmt.missing_fields.push_back(canonical);
            }
        }
        stmts.push_back(stmt);
    };

    auto extract_modern = [](const json& root, const std::string& key, const std::map<std::string, std::vector<std::string>>& field_map, const std::string& type, std::vector<FinancialStatement>& stmts) -> bool {
        if (!root.contains(key) || !root[key].is_object() || root[key].empty()) return false;
        
        // Grab the first date column (most recent)
        auto first_date = root[key].begin();
        const json& report = first_date.value();
        if (!report.is_object()) return false;

        FinancialStatement stmt;
        stmt.statement_type = type;
        stmt.fiscal_period = first_date.key(); // The unix timestamp string

        for (const auto& pair : field_map) {
            std::string canonical = pair.first;
            bool found = false;
            for (const std::string& yf_key : pair.second) {
                if (report.contains(yf_key) && report[yf_key].is_number()) {
                    stmt.line_items.push_back({canonical, report[yf_key].get<double>(), "USD"});
                    found = true;
                    break;
                }
            }
            if (!found) stmt.missing_fields.push_back(canonical);
        }
        stmts.push_back(stmt);
        return true;
    };

    bool has_inc = extract_modern(root_json, "modern_income_stmt", {
        {"total_revenue", {"Total Revenue", "Operating Revenue"}},
        {"gross_profit", {"Gross Profit"}},
        {"operating_income", {"Operating Income", "EBIT"}},
        {"net_income", {"Net Income", "Net Income Common Stockholders"}},
        {"ebitda", {"EBITDA", "Normalized EBITDA"}},
        {"interest_expense", {"Interest Expense", "Interest Expense Non Operating"}},
        {"pretax_income", {"Pretax Income"}}
    }, "INCOME_STATEMENT", statements);

    if (!has_inc && result.contains("incomeStatementHistory") && result["incomeStatementHistory"].contains("incomeStatementHistory")) {
        auto history = result["incomeStatementHistory"]["incomeStatementHistory"];
        if (history.is_array() && !history.empty()) {
            std::map<std::string, std::vector<std::string>> cmap = {
                {"total_revenue", {"totalRevenue", "operatingRevenue"}},
                {"gross_profit", {"grossProfit"}},
                {"operating_income", {"operatingIncome", "ebit"}},
                {"net_income", {"netIncome", "netIncomeApplicableToCommonShares"}},
                {"ebitda", {"ebitda"}},
                {"interest_expense", {"interestExpense", "interestExpenseNonOperating"}},
                {"pretax_income", {"incomeBeforeTax"}}
            };
            extract_items(history[0], cmap, "INCOME_STATEMENT", statements);
        }
    }
    
    bool has_bs = extract_modern(root_json, "modern_balance_sheet", {
        {"total_assets", {"Total Assets"}},
        {"total_liabilities", {"Total Liabilities Net Minority Interest"}},
        {"current_assets", {"Current Assets"}},
        {"current_liabilities", {"Current Liabilities"}},
        {"inventory", {"Inventory"}},
        {"total_debt", {"Total Debt"}},
        {"stockholders_equity", {"Stockholders Equity", "Common Stock Equity"}},
        {"retained_earnings", {"Retained Earnings"}},
        {"cash_and_equivalents", {"Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"}}
    }, "BALANCE_SHEET", statements);

    if (!has_bs && result.contains("balanceSheetHistory") && result["balanceSheetHistory"].contains("balanceSheetStatements")) {
        auto history = result["balanceSheetHistory"]["balanceSheetStatements"];
        if (history.is_array() && !history.empty()) {
            std::map<std::string, std::vector<std::string>> cmap = {
                {"total_assets", {"totalAssets"}},
                {"total_liabilities", {"totalLiab"}},
                {"current_assets", {"totalCurrentAssets"}},
                {"current_liabilities", {"totalCurrentLiabilities"}},
                {"inventory", {"inventory"}},
                {"total_debt", {"shortLongTermDebtTotal", "longTermDebt"}},
                {"stockholders_equity", {"totalStockholderEquity"}},
                {"retained_earnings", {"retainedEarnings"}},
                {"cash_and_equivalents", {"cash"}}
            };
            extract_items(history[0], cmap, "BALANCE_SHEET", statements);
        }
    }
    
    bool has_cf = extract_modern(root_json, "modern_cashflow", {
        {"operating_cash_flow", {"Operating Cash Flow"}},
        {"capital_expenditures", {"Capital Expenditure"}},
        {"free_cash_flow", {"Free Cash Flow"}} 
    }, "CASH_FLOW", statements);

    if (!has_cf && result.contains("cashflowStatementHistory") && result["cashflowStatementHistory"].contains("cashflowStatements")) {
        auto history = result["cashflowStatementHistory"]["cashflowStatements"];
        if (history.is_array() && !history.empty()) {
            std::map<std::string, std::vector<std::string>> cmap = {
                {"operating_cash_flow", {"totalCashFromOperatingActivities"}},
                {"capital_expenditures", {"capitalExpenditures"}},
                {"free_cash_flow", {"freeCashFlow"}} 
            };
            extract_items(history[0], cmap, "CASH_FLOW", statements);
        }
    }
    
    // --- ALPHA VANTAGE FALLBACK ---
    if (!has_inc && root_json.contains("alpha_vantage")) {
        auto av = root_json["alpha_vantage"];
        
        // Income Statement
        if (av.contains("INCOME_STATEMENT") && av["INCOME_STATEMENT"].contains("annualReports")) {
            auto arr = av["INCOME_STATEMENT"]["annualReports"];
            if (arr.is_array() && !arr.empty()) {
                auto report = arr[0];
                FinancialStatement fs;
                fs.statement_type = "INCOME_STATEMENT";
                fs.fiscal_period = "annual";
                std::map<std::string, std::string> mapping = {
                    {"total_revenue", "totalRevenue"},
                    {"gross_profit", "grossProfit"},
                    {"operating_income", "operatingIncome"},
                    {"net_income", "netIncome"},
                    {"ebitda", "ebitda"},
                    {"interest_expense", "interestAndDebtExpense"},
                    {"pretax_income", "incomeBeforeTax"}
                };
                for (const auto& kv : mapping) {
                    if (report.contains(kv.second) && report[kv.second].is_string() && report[kv.second] != "None") {
                        try { fs.line_items.push_back({kv.first, std::stod(report[kv.second].get<std::string>()), "raw"}); } catch(...) {}
                    }
                }
                statements.push_back(fs);
            }
        }
        
        // Balance Sheet
        if (av.contains("BALANCE_SHEET") && av["BALANCE_SHEET"].contains("annualReports")) {
            auto arr = av["BALANCE_SHEET"]["annualReports"];
            if (arr.is_array() && !arr.empty()) {
                auto report = arr[0];
                FinancialStatement fs;
                fs.statement_type = "BALANCE_SHEET";
                fs.fiscal_period = "annual";
                std::map<std::string, std::string> mapping = {
                    {"total_assets", "totalAssets"},
                    {"total_liabilities", "totalLiabilities"},
                    {"current_assets", "totalCurrentAssets"},
                    {"current_liabilities", "totalCurrentLiabilities"},
                    {"inventory", "inventory"},
                    {"total_debt", "shortLongTermDebtTotal"},
                    {"stockholders_equity", "totalShareholderEquity"},
                    {"retained_earnings", "retainedEarnings"},
                    {"cash_and_equivalents", "cashAndCashEquivalentsAtCarryingValue"}
                };
                for (const auto& kv : mapping) {
                    if (report.contains(kv.second) && report[kv.second].is_string() && report[kv.second] != "None") {
                        try { fs.line_items.push_back({kv.first, std::stod(report[kv.second].get<std::string>()), "raw"}); } catch(...) {}
                    }
                }
                statements.push_back(fs);
            }
        }
        
        // Cash Flow
        if (av.contains("CASH_FLOW") && av["CASH_FLOW"].contains("annualReports")) {
            auto arr = av["CASH_FLOW"]["annualReports"];
            if (arr.is_array() && !arr.empty()) {
                auto report = arr[0];
                FinancialStatement fs;
                fs.statement_type = "CASH_FLOW";
                fs.fiscal_period = "annual";
                std::map<std::string, std::string> mapping = {
                    {"operating_cash_flow", "operatingCashflow"},
                    {"capital_expenditures", "capitalExpenditures"}
                };
                for (const auto& kv : mapping) {
                    if (report.contains(kv.second) && report[kv.second].is_string() && report[kv.second] != "None") {
                        try { fs.line_items.push_back({kv.first, std::stod(report[kv.second].get<std::string>()), "raw"}); } catch(...) {}
                    }
                }
                statements.push_back(fs);
            }
        }
    }
    // ------------------------------
    
    FinancialStatement key_stats;
    key_stats.statement_type = "KEY_STATS";
    key_stats.fiscal_period = "current";
    if (result.contains("defaultKeyStatistics") || result.contains("summaryDetail")) {
        std::vector<json> sources;
        if (result.contains("defaultKeyStatistics")) sources.push_back(result["defaultKeyStatistics"]);
        if (result.contains("summaryDetail")) sources.push_back(result["summaryDetail"]);
        
        std::map<std::string, std::string> cmap = {
            {"trailing_pe", "trailingPE"}, {"forward_pe", "forwardPE"},
            {"price_to_book", "priceToBook"}, {"peg_ratio", "pegRatio"},
            {"enterprise_value", "enterpriseValue"}, {"beta", "beta"},
            {"current_price", "currentPrice"}, {"target_price", "targetMeanPrice"},
            {"revenue_growth", "revenueGrowth"}, {"earnings_growth", "earningsGrowth"},
            {"dividend_yield", "dividendYield"}, {"52_week_high", "fiftyTwoWeekHigh"},
            {"52_week_low", "fiftyTwoWeekLow"}, {"held_percent_institutions", "heldPercentInstitutions"},
            {"held_percent_insiders", "heldPercentInsiders"}
        };
        for (const auto& pair : cmap) {
            std::string canonical = pair.first;
            std::string yf_key = pair.second;
            for (const auto& source : sources) {
                if (source.contains(yf_key) && source[yf_key].is_object() && source[yf_key].contains("raw")) {
                    key_stats.line_items.push_back({canonical, source[yf_key]["raw"].get<double>(), "mixed"});
                    break;
                }
            }
        }
    }
    if (result.contains("price")) {
        auto p = result["price"];
        if (p.contains("marketCap") && p["marketCap"].is_object() && p["marketCap"].contains("raw")) {
            key_stats.line_items.push_back({"market_cap", p["marketCap"]["raw"].get<double>(), "USD"});
        }
    }
    statements.push_back(key_stats);
    return statements;
}


std::string detect_company_type(const std::string& industry) {
    std::string ind_lower = industry;
    std::transform(ind_lower.begin(), ind_lower.end(), ind_lower.begin(), ::tolower);
    if (ind_lower.find("bank") != std::string::npos) return "bank";
    if (ind_lower.find("insurance") != std::string::npos) return "insurance";
    if (ind_lower.find("financial") != std::string::npos ||
        ind_lower.find("credit") != std::string::npos ||
        ind_lower.find("capital market") != std::string::npos) return "diversified_financial";
    return "";
}


int main(int argc, char* argv[]) {
    auto pipeline_start = std::chrono::steady_clock::now();

    std::string ticker = "INFY.NS";
    std::string generation_id = "";
    bool skip_rag = false;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--skip-rag") {
            skip_rag = true;
        } else if (arg == "--gen-id" && i + 1 < argc) {
            generation_id = argv[++i];
        } else {
            ticker = arg;
        }
    }

    if (generation_id.empty()) {
        generation_id = std::to_string(std::time(nullptr)); // fallback for manual runs
    }

    if (!is_safe_ticker(ticker)) {
        std::cerr << "[ERROR] Invalid ticker. Use letters, numbers, '.', '_', or '-' only." << std::endl;
        return 1;
    }
    
    std::cout << "=== Running C++ Analysis Pipeline for " << ticker << " ===" << std::endl;

    auto env = load_env(find_env_path());
    if (env.find("NEWSAPI_KEY") == env.end()) {
        std::cerr << "[ERROR] Could not find NEWSAPI_KEY in .env file." << std::endl;
    }
    std::string news_api_key = env["NEWSAPI_KEY"];

    std::string project_root = find_project_root();
    std::string db_path = project_root + "/cpp/invest.sqlite";
    Storage storage(db_path);
    storage.init_schema();
    std::cout << "[INFO] Initialized local SQLite database: " << db_path << std::endl;

    // ── Phase 1: Unified data fetch (single Python process + cache) ──
    std::cout << "\n--- Fetching Data ---" << std::endl;
    
    std::string cache_file = cache::cache_path(ticker, "unified_fetch");
    std::string unified_json_str;
    
    // Check if Java generated the temp files
    std::string yf_file = "json/" + generation_id + "_yf_temp.json";
    std::ifstream yf_f(yf_file);
    if (yf_f.good()) {
        std::cout << "  [JAVA ORCHESTRATOR] Found pre-fetched Java I/O data for " << ticker << std::endl;
        json unified;
        try { unified["yfinance"] = json::parse(yf_f); } catch(...) {}
        yf_f.close();
        
        std::string news_file = "json/" + generation_id + "_news_temp.json";
        std::ifstream news_f(news_file);
        if (news_f.is_open()) {
            try { unified["news"] = json::parse(news_f); } catch(...) {}
            news_f.close();
        }
        
        unified_json_str = unified.dump();
        
        // Cleanup intermediate files
        std::remove(yf_file.c_str());
        // news_file is deleted later after NewsAgent parses it
    }
    
    else if (cache::has_valid_unified_cache(ticker)) {
        std::cout << "  [CACHE HIT] Loading cached data for " << ticker << std::endl;
        unified_json_str = cache::read_cache(cache_file);
    } else {
        std::cout << "  [CACHE MISS] Running unified fetch for " << ticker << "..." << std::endl;
        std::string fetch_output = "unified_out_" + ticker + ".json";
        std::string py_script = project_root + "/python/ingestion/unified_fetch.py";
        
#ifdef _WIN32
        std::string cmd = "py -3.10 \"" + py_script + "\" " + ticker + " " + fetch_output;
#else
        std::string cmd = "python3 \"" + py_script + "\" " + ticker + " " + fetch_output;
#endif
        int ret = std::system(cmd.c_str());
        if (ret != 0) {
            std::cerr << "[ERROR] Unified fetch script failed with status " << ret << std::endl;
        }
        
        std::ifstream f(fetch_output);
        if (f.is_open()) {
            unified_json_str = std::string((std::istreambuf_iterator<char>(f)),
                                            std::istreambuf_iterator<char>());
            f.close();
            // Save to cache
            cache::write_cache(cache_file, unified_json_str);
        }
        std::remove(fetch_output.c_str());
    }

    // Parse unified JSON
    std::vector<FinancialStatement> statements;
    std::string company_type;

    if (!unified_json_str.empty()) {
        try {
            json unified = json::parse(unified_json_str);
            
            if (unified.contains("yfinance") && !unified["yfinance"].is_null()) {
                statements = parse_yfinance_json(unified["yfinance"]);
                
                // Extract industry for bank detection
                try {
                    auto result = unified["yfinance"]["quoteSummary"]["result"][0];
                    if (result.contains("defaultKeyStatistics") && result["defaultKeyStatistics"].contains("industry")) {
                        auto ind = result["defaultKeyStatistics"]["industry"];
                        if (ind.is_string()) {
                            company_type = detect_company_type(ind.get<std::string>());
                        } else if (ind.is_object() && ind.contains("fmt") && ind["fmt"].is_string()) {
                            company_type = detect_company_type(ind["fmt"].get<std::string>());
                        }
                    }
                } catch(...) {}
            }

        } catch (const std::exception& e) {
            std::cerr << "[ERROR] Failed to parse unified fetch JSON: " << e.what() << std::endl;
        }
    }

    // News is already a direct C++ HTTP call — run it concurrently during parse
    auto future_news = std::async(std::launch::async, [&]() {
        NewsAgent news_agent(news_api_key);
        return news_agent.fetch_news(ticker, generation_id);
    });
    auto articles = future_news.get();
    
    // Safely delete the news file now that it's parsed
    std::string temp_news_file = "json/" + generation_id + "_news_temp.json";
    std::remove(temp_news_file.c_str());

    // ── Write all data to SQLite ──
    if (articles.empty()) {
        std::cout << "No news found or API failed." << std::endl;
    } else {
        storage.clear_ticker_data(ticker, {"news_articles"});
        storage.write_news(ticker, articles);
        for (const auto& a : articles) {
            std::cout << " - [" << a.published_at << "] " << a.title << " (" << a.source << ")" << std::endl;
        }
    }

    if (statements.empty()) {
        std::cout << "No financial data found." << std::endl;
    } else {
        storage.clear_ticker_data(ticker, {"financial_statements"});
        for (const auto& stmt : statements) {
            storage.write_financial_statement(ticker, stmt);
            std::cout << "  " << stmt.statement_type << " (" << stmt.fiscal_period << ")" << std::endl;
        }
    }


    // ── Phase 2: Compute Ratios ──
    std::cout << "\n--- Computing Financial Ratios ---" << std::endl;
    if (!company_type.empty()) {
        std::cout << "  Detected company_type: " << company_type << std::endl;
    }

    RatioAgent r_agent;
    auto ratios = r_agent.compute_ratios(statements, company_type);
    storage.clear_ticker_data(ticker, {"financial_ratios", "aggregate_sentiment", "sentiment_excerpts"});
    if (ratios.empty()) {
        std::cout << "  No ratios computed." << std::endl;
    } else {
        storage.write_ratios(ticker, ratios);
        for (const auto& r : ratios) {
            std::cout << "  " << r.name << " (" << r.category << "): ";
            if (r.computable && r.value.has_value()) {
                std::cout << r.value.value() << std::endl;
            } else {
                std::cout << "N/A (" << r.note << ")" << std::endl;
            }
        }
    }

    std::cout << "\n--- Scoring Sentiment (FinBERT Offline Bridge) ---" << std::endl;
    SentimentAgent s_agent;
    std::vector<SentimentInput> batch_items;
    
    // Score News
    for (const auto& a : articles) {
        SentimentInput si;
        si.text = a.title + ". " + a.snippet;
        si.segment = "NEWS";
        si.source_url = a.url;
        si.title = a.title;
        si.published_at = a.published_at;
        si.ticker = ticker;
        batch_items.push_back(si);
    }


    std::vector<SentimentResult> all_sentiments = s_agent.score_batch(batch_items);
    AggregateSentiment agg = s_agent.aggregate_sentiment(ticker, all_sentiments);
    
    storage.write_aggregate_sentiment(ticker, agg);
    storage.write_sentiment_excerpts(ticker, all_sentiments);

    std::cout << "  Overall Label: " << agg.overall_label << " (Score: " << agg.overall_score << ")" << std::endl;
    for (const auto& [seg, score] : agg.component_scores) {
        std::cout << "    " << seg << " [" << agg.sample_size[seg] << " items]: " << score << std::endl;
    }

    std::cout << "\n--- Peer Benchmarking & Composite Score ---" << std::endl;
    std::vector<PeerBenchmark> peer_benchmarks;
    std::string peers_file = "json/" + generation_id + "_peers_temp.json";
    std::ifstream peers_f(peers_file);
    if (peers_f.good()) {
        try {
            json peers_json = json::parse(peers_f);
            peers_f.close();
            std::remove(peers_file.c_str());
            for (auto& el : peers_json.items()) {
                std::string peer_ticker = el.key();
                json peer_data;
                peer_data["quoteSummary"] = el.value()["quoteSummary"];
                auto stmts = parse_yfinance_json(peer_data);
                auto peer_ratios = r_agent.compute_ratios(stmts, company_type);
                for (const auto& pr : peer_ratios) {
                    if (pr.name == "pe_ratio" || pr.name == "pb_ratio" || pr.name == "ev_to_ebitda" || pr.name == "roe" || pr.name == "net_margin") {
                        if (pr.computable && pr.value.has_value()) {
                            double t_val = 0.0;
                            bool found = false;
                            for (const auto& tr : ratios) {
                                if (tr.name == pr.name && tr.computable && tr.value.has_value()) {
                                    t_val = tr.value.value();
                                    found = true;
                                    break;
                                }
                            }
                            if (found && pr.value.value() != 0.0) {
                                double prem_disc = calculate_peer_premium_discount(t_val, pr.value.value());
                                if (!std::isnan(prem_disc)) {
                                    peer_benchmarks.push_back({ticker, peer_ticker, pr.name, t_val, pr.value.value(), prem_disc});
                                }
                            }
                        }
                    }
                }
            }
        } catch(...) {}
        peers_f.close();
    }
    storage.clear_ticker_data(ticker, {"peer_benchmarks", "investment_assessment"});
    storage.write_peer_benchmarks(peer_benchmarks);

    // ── Composite Score with explicit missing-component handling ──
    // Track which components have actual data (never default to 5.0)
    bool has_health = false, has_val = false, has_risk = false;
    double health_score = 5.0, val_score = 5.0, risk_score = 5.0;
    int health_adjustments = 0, val_adjustments = 0, risk_adjustments = 0;

    for (const auto& r : ratios) {
        if (!r.computable) continue;
        double adjust = (r.health_flag == "HEALTHY") ? 1.0 : (r.health_flag == "CONCERNING" ? -1.0 : 0.0);
        if (r.category == "PROFITABILITY" || r.category == "LIQUIDITY") {
            health_score += adjust * 0.5;
            health_adjustments++;
            has_health = true;
        }
        if (r.category == "VALUATION") {
            val_score += adjust * 1.0;
            val_adjustments++;
            has_val = true;
        }
        if (r.category == "LEVERAGE" || r.category == "RISK_MODEL") {
            risk_score += adjust * 1.0;
            risk_adjustments++;
            has_risk = true;
        }
    }
    if (has_health) health_score = std::max(1.0, std::min(10.0, health_score));
    if (has_val) val_score = std::max(1.0, std::min(10.0, val_score));
    if (has_risk) risk_score = std::max(1.0, std::min(10.0, risk_score));

    // Sentiment: only valid if scoring didn't fail and we had items
    bool has_sentiment = !agg.scoring_failed && !batch_items.empty();
    double sent_score = 5.0;
    if (has_sentiment) {
        sent_score = std::max(1.0, std::min(10.0, 5.5 + (agg.overall_score * 4.5)));
    }

    // Peers: only valid if we have benchmarks
    bool has_peers = !peer_benchmarks.empty();
    double peer_score = 5.0;
    if (has_peers) {
        double total_pd = 0;
        int pd_count = 0;
        for (const auto& pb : peer_benchmarks) {
            if (pb.ratio_name == "pe_ratio" || pb.ratio_name == "pb_ratio" || pb.ratio_name == "ev_to_ebitda") {
                total_pd += pb.premium_discount;
                pd_count++;
            }
        }
        if (pd_count > 0) peer_score -= ((total_pd / pd_count) / 10.0);
        peer_score = std::max(1.0, std::min(10.0, peer_score));
    }

    // Count available components
    int available_components = 0;
    if (has_health) available_components++;
    if (has_val) available_components++;
    if (has_risk) available_components++;
    if (has_sentiment) available_components++;
    if (has_peers) available_components++;

    double composite = 0.0;
    std::string label = "INSUFFICIENT DATA";

    if (available_components >= 3) {
        // Normalized weighted average across available components only
        double weighted_sum = 0.0;
        double total_weight = 0.0;
        if (has_health)    { weighted_sum += 0.30 * health_score; total_weight += 0.30; }
        if (has_val)       { weighted_sum += 0.25 * val_score;    total_weight += 0.25; }
        if (has_sentiment) { weighted_sum += 0.20 * sent_score;   total_weight += 0.20; }
        if (has_risk)      { weighted_sum += 0.15 * risk_score;   total_weight += 0.15; }
        if (has_peers)     { weighted_sum += 0.10 * peer_score;   total_weight += 0.10; }

        composite = weighted_sum / total_weight;
        composite = std::max(1.0, std::min(10.0, composite));
        char label_buf[32];
        get_conviction_label(composite, label_buf);
        label = std::string(label_buf);
    }

    std::cout << "  Components available: " << available_components << "/5"
              << " (Health:" << (has_health ? "Y" : "N")
              << " Val:" << (has_val ? "Y" : "N")
              << " Sent:" << (has_sentiment ? "Y" : "N")
              << " Risk:" << (has_risk ? "Y" : "N")
              << " Peers:" << (has_peers ? "Y" : "N") << ")" << std::endl;

    InvestmentAssessment assessment = { ticker, composite, label };
    storage.write_investment_assessment(assessment);

    std::cout << "  Composite Score: " << composite << "/10.0 (" << label << ")" << std::endl;

    std::cout << "\n=== Pipeline complete! All data fetched, analyzed, and stored in SQLite. ===" << std::endl;

    std::cout << "\n--- Generating JSON Snapshot ---" << std::endl;
    std::string snapshot_path = JsonSnapshotWriter::generate_snapshot(ticker, generation_id, db_path, project_root + "/reports");
    if (!snapshot_path.empty()) {
        std::cout << "[OUTPUT_JSON] " << snapshot_path << std::endl;
    }

    auto pipeline_end = std::chrono::steady_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::seconds>(pipeline_end - pipeline_start).count();
    std::cout << "\n--- Total execution time: " << duration << " seconds ---" << std::endl;

    return 0;
}
