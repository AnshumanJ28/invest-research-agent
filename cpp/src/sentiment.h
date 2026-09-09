#pragma once

#include <string>
#include <vector>
#include <map>
#include <memory>

class OnnxEngine;
class BertTokenizer;

struct SentimentInput {
    std::string ticker;
    std::string text;
    std::string segment;
    std::string source_url;
    std::string title;
    std::string published_at;
};

struct SentimentResult {
    std::string excerpt;
    std::string segment;
    std::string source_url;
    std::string title;
    std::string published_at;
    
    std::string label;
    double confidence;
    bool is_fls; // Forward looking statement
    std::vector<std::string> aspects;
    bool ok;
};

struct AggregateSentiment {
    std::string ticker;
    std::string overall_label;
    double overall_score; // -1.0 to 1.0
    std::string trend;
    std::map<std::string, double> component_scores;
    std::map<std::string, int> sample_size;
    bool scoring_failed = false; // true when the scoring subprocess failed
};

class SentimentAgent {
public:
    SentimentAgent();
    ~SentimentAgent();

    std::vector<SentimentResult> score_batch(const std::vector<SentimentInput>& items);
    AggregateSentiment aggregate_sentiment(const std::string& ticker, const std::vector<SentimentResult>& results);

private:
    std::unique_ptr<OnnxEngine> engine_;
    std::unique_ptr<BertTokenizer> tokenizer_;
};
