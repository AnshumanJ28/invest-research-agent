#include "storage.h"
#include <sqlite3.h>
#include <iostream>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

Storage::Storage(const std::string& db_path) {
    if (sqlite3_open(db_path.c_str(), &db_) != SQLITE_OK) {
        std::cerr << "[ERROR] Cannot open SQLite DB: " << sqlite3_errmsg(db_) << std::endl;
        db_ = nullptr;
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
    )");
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
            j.push_back({{"name", li.name}, {"value", li.value.value_or(0.0)}, {"unit", li.unit}});
        }
        std::string j_str = j.dump();
        sqlite3_bind_text(res, 4, j_str.c_str(), -1, SQLITE_TRANSIENT);
        
        sqlite3_step(res);
        sqlite3_finalize(res);
    }
}

void Storage::write_filing(const std::string& ticker, const EdgarDocument& doc) {
    if (!db_) return;
    std::string sql = "INSERT INTO filing_sections (ticker, filing_type, filed_date, section_name, text) VALUES (?, ?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        for (const auto& sec : doc.sections) {
            sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 2, "quarterly_results", -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 3, doc.filed_date.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 4, sec.name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 5, sec.text.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(res);
            sqlite3_reset(res);
        }
        sqlite3_finalize(res);
    }
}

void Storage::write_transcript(const std::string& ticker, const TranscriptDocument& doc) {
    if (!db_) return;
    if (!doc.available) return;
    std::string sql = "INSERT INTO transcript_utterances (ticker, speaker, section, text) VALUES (?, ?, ?, ?);";
    sqlite3_stmt* res;
    if (sqlite3_prepare_v2(db_, sql.c_str(), -1, &res, 0) == SQLITE_OK) {
        for (const auto& u : doc.utterances) {
            sqlite3_bind_text(res, 1, ticker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 2, u.speaker.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 3, u.section.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(res, 4, u.text.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(res);
            sqlite3_reset(res);
        }
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
