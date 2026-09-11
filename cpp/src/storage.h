#pragma once
#include <string>
#include <vector>
#include "yfinance_agent.h"
#include "news_agent.h"
#include "ratios.h"
#include "sentiment.h"
struct PeerBenchmark {
    std::string ticker;
    std::string peer_ticker;
    std::string ratio_name;
    double ticker_value;
    double peer_value;
    double premium_discount;
};
struct InvestmentAssessment {
    std::string ticker;
    double composite_score;
    std::string conviction_label;
};
struct sqlite3;
class Storage {
public:
    Storage(const std::string& db_path);
    ~Storage();
    void init_schema();
    void clear_ticker_data(const std::string& ticker, const std::vector<std::string>& tables);
    void write_financial_statement(const std::string& ticker, const FinancialStatement& stmt);
    void write_news(const std::string& ticker, const std::vector<NewsArticle>& articles);
    void write_ratios(const std::string& ticker, const std::vector<RatioResult>& ratios);
    void write_aggregate_sentiment(const std::string& ticker, const AggregateSentiment& agg);
    void write_sentiment_excerpts(const std::string& ticker, const std::vector<SentimentResult>& excerpts);
    void write_peer_benchmarks(const std::vector<PeerBenchmark>& benchmarks);
    void write_investment_assessment(const InvestmentAssessment& assessment);
private:
    sqlite3* db_;
    void execute(const std::string& sql);
};
