#include <iostream>
#include <string>
#include <cstdlib>
#include <cctype>
#include "news_agent.h"
#include "yfinance_agent.h"
#include "transcript_agent.h"
#include "edgar_agent.h"
#include "ratios.h"
#include "sentiment.h"
#include "storage.h"

// Simple .env parser for C++
#include <fstream>
#include <sstream>
#include <map>

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

int run_rag_pipeline(const std::string& ticker) {
#ifdef _WIN32
    std::string command =
        "if exist rag\\main.py (py -3.10 -m rag.main " + ticker + ") "
        "else if exist ..\\rag\\main.py (cd /d .. && py -3.10 -m rag.main " + ticker + ") "
        "else if exist ..\\..\\rag\\main.py (cd /d ..\\.. && py -3.10 -m rag.main " + ticker + ") "
        "else (echo [ERROR] Could not locate rag\\main.py & exit /b 1)";
#else
    std::string command =
        "if [ -f rag/main.py ]; then python3 -m rag.main " + ticker + "; "
        "elif [ -f ../rag/main.py ]; then cd .. && python3 -m rag.main " + ticker + "; "
        "elif [ -f ../../rag/main.py ]; then cd ../.. && python3 -m rag.main " + ticker + "; "
        "else echo '[ERROR] Could not locate rag/main.py'; exit 1; fi";
#endif
    return std::system(command.c_str());
}

int main(int argc, char* argv[]) {
    std::string ticker = "INFY.NS";
    bool skip_rag = false;
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--skip-rag") {
            skip_rag = true;
        } else {
            ticker = arg;
        }
    }

    if (!is_safe_ticker(ticker)) {
        std::cerr << "[ERROR] Invalid ticker. Use letters, numbers, '.', '_', or '-' only." << std::endl;
        return 1;
    }
    
    std::cout << "=== Running C++ Analysis Pipeline for " << ticker << " ===" << std::endl;

    // Try finding .env relative to the cpp_pipeline directory (CWD when running)
    auto env = load_env("../.env");
    if (env.find("NEWSAPI_KEY") == env.end()) {
        std::cerr << "[ERROR] Could not find NEWSAPI_KEY in .env file." << std::endl;
    }
    std::string news_api_key = env["NEWSAPI_KEY"];

    Storage storage("invest.sqlite");
    storage.init_schema();
    std::cout << "[INFO] Initialized local SQLite database: invest.sqlite" << std::endl;

    std::cout << "\n--- Fetching News ---" << std::endl;
    NewsAgent news_agent(news_api_key);
    auto articles = news_agent.fetch_news(ticker);

    if (articles.empty()) {
        std::cout << "No news found or API failed." << std::endl;
    } else {
        storage.write_news(ticker, articles);
        for (const auto& a : articles) {
            std::cout << " - [" << a.published_at << "] " << a.title << " (" << a.source << ")" << std::endl;
        }
    }

    std::cout << "\n--- Fetching Financial Statements ---" << std::endl;
    YFinanceAgent yf_agent;
    auto statements = yf_agent.fetch_financial_statements(ticker);
    
    if (statements.empty()) {
        std::cout << "No financial data found." << std::endl;
    } else {
        for (const auto& stmt : statements) {
            storage.write_financial_statement(ticker, stmt);
            std::cout << "  " << stmt.statement_type << " (" << stmt.fiscal_period << ")" << std::endl;
            for (const auto& li : stmt.line_items) {
                std::cout << "    " << li.name << ": " << (li.value.has_value() ? std::to_string(li.value.value()) : "N/A") << " " << li.unit << std::endl;
            }
        }
    }

    std::cout << "\n--- Fetching Earnings Transcripts ---" << std::endl;
    TranscriptAgent t_agent;
    auto t_doc = t_agent.fetch_transcript(ticker);
    if (!t_doc.available) {
        std::cout << "  Transcript unavailable: " << t_doc.unavailable_reason << std::endl;
    } else {
        storage.write_transcript(ticker, t_doc);
        std::cout << "  Found transcript with " << t_doc.utterances.size() << " utterances." << std::endl;
        if (!t_doc.utterances.empty()) {
            std::cout << "  Sample: [" << t_doc.utterances[0].section << "] " << t_doc.utterances[0].speaker << ": " 
                      << t_doc.utterances[0].text.substr(0, 100) << "..." << std::endl;
        }
    }

    std::cout << "\n--- Fetching Edgar/BSE Filings ---" << std::endl;
    EdgarAgent e_agent;
    auto filings = e_agent.fetch_latest_filings(ticker);
    if (filings.empty()) {
        std::cout << "  No filings found." << std::endl;
    } else {
        for (const auto& [form, doc] : filings) {
            storage.write_filing(ticker, doc);
            std::cout << "  " << form << " filed on " << doc.filed_date << " (" << doc.sections.size() << " sections)" << std::endl;
            if (!doc.sections.empty()) {
                std::cout << "    Sample: [" << doc.sections[0].name << "] " << doc.sections[0].text.substr(0, 100) << "..." << std::endl;
            }
        }
    }

    std::cout << "\n--- Computing Financial Ratios ---" << std::endl;
    RatioAgent r_agent;
    auto ratios = r_agent.compute_ratios(statements);
    if (ratios.empty()) {
        std::cout << "  No ratios computed." << std::endl;
    } else {
        for (const auto& r : ratios) {
            std::cout << "  " << r.name << " (" << r.category << "): ";
            if (r.computable && r.value.has_value()) {
                std::cout << r.value.value() << std::endl;
            } else {
                std::cout << "N/A (" << r.note << ")" << std::endl;
            }
        }
    }

    std::cout << "\n--- Scoring Sentiment (FinBERT) ---" << std::endl;
    std::string hf_token = env.count("HF_API_TOKEN") ? env["HF_API_TOKEN"] : "";
    SentimentAgent s_agent(hf_token);
    std::vector<SentimentResult> all_sentiments;
    
    // Score News
    for (const auto& a : articles) {
        auto res = s_agent.score_text(a.title + ". " + a.snippet, "NEWS");
        if (!res.label.empty()) all_sentiments.push_back(res);
    }
    
    // Score Transcripts
    if (t_doc.available) {
        for (const auto& u : t_doc.utterances) {
            auto res = s_agent.score_text(u.text, "TRANSCRIPT_" + u.section);
            if (!res.label.empty()) all_sentiments.push_back(res);
        }
    }

    auto agg = s_agent.aggregate_sentiment(ticker, all_sentiments);
    std::cout << "  Overall Sentiment: " << agg.overall_label << " (Score: " << agg.overall_score << ")" << std::endl;
    for (const auto& [seg, score] : agg.component_scores) {
        std::cout << "    " << seg << " [" << agg.sample_size[seg] << " items]: " << score << std::endl;
    }

    std::cout << "\n=== Pipeline complete! All data fetched, analyzed, and stored in SQLite. ===" << std::endl;

    if (skip_rag || env_flag_enabled(env, "SKIP_RAG")) {
        std::cout << "\n--- Skipping Role 3 RAG memo generation ---" << std::endl;
        return 0;
    }

    std::cout << "\n--- Running Role 3 RAG Memo Generation ---" << std::endl;
    int rag_status = run_rag_pipeline(ticker);
    if (rag_status != 0) {
        std::cerr << "[ERROR] Core pipeline completed, but Role 3 RAG memo generation failed with status "
                  << rag_status << "." << std::endl;
        return rag_status;
    }
    std::cout << "--- Role 3 RAG memo generation complete ---" << std::endl;

    return 0;
}
