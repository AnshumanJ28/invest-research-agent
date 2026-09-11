#include "storage.h"
#include <sqlite3.h>
#include <iostream>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

static bool column_exists(sqlite3* db, const std::string& table, const std::string& column) {
    std::string sql = "PRAGMA table_info(" + table + ");";
    sqlite3_stmt* res;
    bool found = false;
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        while (sqlite3_step(res) == SQLITE_ROW) {
            const char* col_name = reinterpret_cast<const char*>(sqlite3_column_text(res, 1));
            if (col_name && std::string(col_name) == column) {
                found = true;
                break;
            }
        }
        sqlite3_finalize(res);
    }
    return found;
}

Storage::Storage(const std::string& db_path) {
    if (sqlite3_open(db_path.c_str(), &db_) != SQLITE_OK) {
        std::cerr << "[ERROR] Cannot open SQLite DB: " << sqlite3_errmsg(db_) << std::endl;
        db_ = nullptr;
    } else {
        // Enable WAL mode for high concurrency
        execute("PRAGMA journal_mode=WAL;");
        execute("PRAGMA synchronous=NORMAL;");
        execute("PRAGMA busy_timeout=5000;"); // 5s timeout on locks
    }
}

Storage::~Storage() {
    if (db_) {
        sqlite3_close(db_);
    }
}

void Storage::execute(const std::string& sql) {
    if (!db_) return;
    char* err_msg = nullptr;
    if (sqlite3_exec(db_, sql.c_str(), nullptr, nullptr, &err_msg) != SQLITE_OK) {
        std::cerr << "[ERROR] SQLite error: " << err_msg << "\nSQL: " << sql << std::endl;
        sqlite3_free(err_msg);
    }
}

void Storage::init_schema() {
    execute(R"(
        CREATE TABLE IF NOT EXISTS financial_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            statement_type TEXT NOT NULL,
            fiscal_period TEXT NOT NULL,
            line_items TEXT NOT NULL,
            UNIQUE (ticker, statement_type, fiscal_period)
        );
        CREATE TABLE IF NOT EXISTS filing_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            filing_type TEXT NOT NULL,
            filed_date TEXT NOT NULL,
            section_name TEXT NOT NULL,
            text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transcript_utterances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            speaker TEXT NOT NULL,
            section TEXT NOT NULL,
            text TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sentiment_excerpts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            segment TEXT NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            excerpt TEXT NOT NULL,
            is_fls INTEGER NOT NULL,
            aspects_json TEXT NOT NULL,
            source_url TEXT,
            title TEXT,
            published_at TEXT
        );
        CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            title TEXT NOT NULL,
            source_publication TEXT NOT NULL,
            published_at TEXT NOT NULL,
            url TEXT NOT NULL,
            snippet TEXT,
            UNIQUE (url)
        );
        CREATE TABLE IF NOT EXISTS financial_ratios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            ratio_name TEXT NOT NULL,
            category TEXT NOT NULL,
            value REAL,
            health_flag TEXT,
            narrative TEXT,
            formula TEXT,
            note TEXT,
            status TEXT,
            UNIQUE (ticker, ratio_name)
        );
        CREATE TABLE IF NOT EXISTS aggregate_sentiment (
            ticker TEXT PRIMARY KEY,
            overall_label TEXT,
            overall_score REAL,
            trend TEXT,
            component_scores TEXT,
            sample_size TEXT,
            scoring_failed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS peer_benchmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            peer_ticker TEXT NOT NULL,
            ratio_name TEXT NOT NULL,
            ticker_value REAL,
            peer_value REAL,
            premium_discount REAL,
            UNIQUE(ticker, peer_ticker, ratio_name)
        );
        CREATE TABLE IF NOT EXISTS investment_assessment (
            ticker TEXT PRIMARY KEY,
            composite_score REAL,
            conviction_label TEXT
        );
    )");
    
    // Ensure the status column exists for legacy DBs using a schema check
    if (!column_exists(db_, "financial_ratios", "status")) {
        execute("ALTER TABLE financial_ratios ADD COLUMN status TEXT;");
    }
}

void Storage::clear_ticker_data(const std::string& ticker, const std::vector<std::string>& tables) {
    if (!db_) return;
    for (const auto& table : tables) {
        std::string sql = "DELETE FROM " + table + " WHERE ticker = ?;";
        sqlite3_stmt* res;
        if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
            sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(res);
            sqlite3_finalize(res);
        }
    }
}

void Storage::write_financial_statement(const std::string& ticker, const FinancialStatement& stmt) {
    if (!db_) return;
    std::string sql = "INSERT OR REPLACE INTO financial_statements (ticker, statement_type, fiscal_period, line_items) VALUES (?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(res, 2, stmt.statement_type.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(res, 3, stmt.fiscal_period.c_str(), -1, SQLITE_STATIC);
        
        json j = json::array();
        for (const auto& li : stmt.line_items) {
            json item;
            item["name"] = li.name;
            item["value"] = li.value.has_value() ? json(li.value.value()) : json(nullptr);
            item["unit"] = li.unit;
            j.push_back(item);
        }
        std::string j_str = j.dump();
        sqlite3_bind_text(res, 4, j_str.c_str(), -1, SQLITE_TRANSIENT);
        
        sqlite3_step(res);
        sqlite3_finalize(res);
    }
}


void Storage::write_news(const std::string& ticker, const std::vector<NewsArticle>& articles) {
    if (!db_) return;
    std::string sql = "INSERT OR IGNORE INTO news_articles (ticker, title, source_publication, published_at, url, snippet) VALUES (?, ?, ?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        for (const auto& a : articles) {
            sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 2, a.title.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 3, a.source.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 4, a.published_at.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 5, a.url.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 6, a.snippet.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(res);
            sqlite3_reset(res);
        }
        sqlite3_finalize(res);
    }
}

void Storage::write_ratios(const std::string& ticker, const std::vector<RatioResult>& ratios) {
    if (!db_) return;
    std::string sql = "INSERT OR REPLACE INTO financial_ratios (ticker, ratio_name, category, value, health_flag, narrative, formula, note, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        for (const auto& r : ratios) {
            sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 2, r.name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 3, r.category.c_str(), -1, SQLITE_STATIC);
            if (r.value.has_value()) {
                sqlite3_bind_double(res, 4, r.value.value());
            } else {
                sqlite3_bind_null(res, 4);
            }
            if (!r.health_flag.empty()) {
                sqlite3_bind_text(res, 5, r.health_flag.c_str(), -1, SQLITE_STATIC);
            } else {
                sqlite3_bind_null(res, 5);
            }
            if (!r.narrative.empty()) {
                sqlite3_bind_text(res, 6, r.narrative.c_str(), -1, SQLITE_STATIC);
            } else {
                sqlite3_bind_null(res, 6);
            }
            sqlite3_bind_text(res, 7, r.formula.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 8, r.note.c_str(), -1, SQLITE_STATIC);
            
            std::string status_str;
            switch(r.status) {
                case CalculationStatus::CALCULATED: status_str = "CALCULATED"; break;
                case CalculationStatus::NOT_APPLICABLE: status_str = "NOT_APPLICABLE"; break;
                case CalculationStatus::DATA_MISSING: status_str = "DATA_MISSING"; break;
                case CalculationStatus::NOT_COMPUTABLE: status_str = "NOT_COMPUTABLE"; break;
            }
            sqlite3_bind_text(res, 9, status_str.c_str(), -1, SQLITE_STATIC);
            
            sqlite3_step(res);
            sqlite3_reset(res);
        }
        sqlite3_finalize(res);
    }
}

void Storage::write_aggregate_sentiment(const std::string& ticker, const AggregateSentiment& agg) {
    if (!db_) return;
    std::string sql = "INSERT OR REPLACE INTO aggregate_sentiment (ticker, overall_label, overall_score, trend, component_scores, sample_size, scoring_failed) VALUES (?, ?, ?, ?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(res, 2, agg.overall_label.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_double(res, 3, agg.overall_score);
        sqlite3_bind_text(res, 4, agg.trend.c_str(), -1, SQLITE_STATIC);
        
        json j_comp;
        for (const auto& [k, v] : agg.component_scores) j_comp[k] = v;
        std::string s_comp = j_comp.dump();
        sqlite3_bind_text(res, 5, s_comp.c_str(), -1, SQLITE_TRANSIENT);
        
        json j_size;
        for (const auto& [k, v] : agg.sample_size) j_size[k] = v;
        std::string s_size = j_size.dump();
        sqlite3_bind_text(res, 6, s_size.c_str(), -1, SQLITE_TRANSIENT);

        sqlite3_bind_int(res, 7, agg.scoring_failed ? 1 : 0);
        
        sqlite3_step(res);
        sqlite3_finalize(res);
    }
}

void Storage::write_sentiment_excerpts(const std::string& ticker, const std::vector<SentimentResult>& excerpts) {
    if (!db_) return;
    std::string sql = "INSERT INTO sentiment_excerpts (ticker, segment, label, confidence, excerpt, is_fls, aspects_json, source_url, title, published_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        for (const auto& r : excerpts) {
            if (!r.ok) continue;
            sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 2, r.segment.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 3, r.label.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_double(res, 4, r.confidence);
            sqlite3_bind_text(res, 5, r.excerpt.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_int(res, 6, r.is_fls ? 1 : 0);
            
            json asp_arr = json::array();
            for (const auto& asp : r.aspects) asp_arr.push_back(asp);
            std::string asp_json = asp_arr.dump();
            sqlite3_bind_text(res, 7, asp_json.c_str(), -1, SQLITE_TRANSIENT);
            
            sqlite3_bind_text(res, 8, r.source_url.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 9, r.title.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 10, r.published_at.c_str(), -1, SQLITE_STATIC);
            
            sqlite3_step(res);
            sqlite3_reset(res);
        }
        sqlite3_finalize(res);
    }
}

void Storage::write_peer_benchmarks(const std::vector<PeerBenchmark>& benchmarks) {
    if (!db_) return;
    std::string sql = "INSERT OR REPLACE INTO peer_benchmarks (ticker, peer_ticker, ratio_name, ticker_value, peer_value, premium_discount) VALUES (?, ?, ?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        for (const auto& b : benchmarks) {
            sqlite3_bind_text(res, 1, b.ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 2, b.peer_ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 3, b.ratio_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_double(res, 4, b.ticker_value);
            sqlite3_bind_double(res, 5, b.peer_value);
            sqlite3_bind_double(res, 6, b.premium_discount);
            sqlite3_step(res);
            sqlite3_reset(res);
        }
        sqlite3_finalize(res);
    }
}

void Storage::write_investment_assessment(const InvestmentAssessment& assessment) {
    if (!db_) return;
    std::string sql = "INSERT OR REPLACE INTO investment_assessment (ticker, composite_score, conviction_label) VALUES (?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        sqlite3_bind_text(res, 1, assessment.ticker.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_double(res, 2, assessment.composite_score);
        sqlite3_bind_text(res, 3, assessment.conviction_label.c_str(), -1, SQLITE_STATIC);
        sqlite3_step(res);
        sqlite3_finalize(res);
    }
}


