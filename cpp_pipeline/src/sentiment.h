#pragma once

#include <string>
#include <vector>
#include <map>

struct SentimentResult {
    std::string segment;
    std::string label;
    double confidence;
    std::string excerpt;
};

struct AggregateSentiment {
    std::string ticker;
    std::string overall_label;
    double overall_score;
    std::string trend;
    std::map<std::string, double> component_scores;
    std::map<std::string, int> sample_size;
};

class SentimentAgent {
public:
    SentimentAgent(const std::string& hf_api_key);
    
    // Score arbitrary text with HuggingFace FinBERT
    SentimentResult score_text(const std::string& text, const std::string& segment);
    
    // Aggregates all scored texts using recency weighting
    AggregateSentiment aggregate_sentiment(const std::string& ticker, const std::vector<SentimentResult>& results);

private:
    std::string hf_api_key_;
};
