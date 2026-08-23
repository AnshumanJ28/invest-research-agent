#pragma once

#include <string>
#include <vector>
#include "yfinance_agent.h"
#include "edgar_agent.h"
#include "transcript_agent.h"
#include "news_agent.h"

struct sqlite3;

class Storage {
public:
    Storage(const std::string& db_path);
    ~Storage();

    void init_schema();
    
    void write_financial_statement(const std::string& ticker, const FinancialStatement& stmt);
    void write_filing(const std::string& ticker, const EdgarDocument& doc);
    void write_transcript(const std::string& ticker, const TranscriptDocument& doc);
    void write_news(const std::string& ticker, const std::vector<NewsArticle>& articles);

private:
    sqlite3* db_;
    void execute(const std::string& sql);
};
