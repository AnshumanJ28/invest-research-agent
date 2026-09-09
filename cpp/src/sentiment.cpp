#include "sentiment.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <cmath>
#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include "onnx_engine.h"
#include "tokenizer.h"

using json = nlohmann::json;

std::string find_project_root_sentiment() {
    for (const auto& candidate : {".", "..", "../..", "../../.."}) {
        std::string test = std::string(candidate) + "/.env";
        if (std::ifstream(test).good()) return candidate;
    }
    return "..";
}

SentimentAgent::SentimentAgent() {
    std::string root = find_project_root_sentiment();
    std::string vocab_path = root + "/cpp/models/vocab.txt";
    std::string model_path = root + "/cpp/models/finbert_int8.onnx";

    try {
        tokenizer_ = std::make_unique<BertTokenizer>(vocab_path);
        engine_ = std::make_unique<OnnxEngine>(model_path);
    } catch (const std::exception& e) {
        std::cerr << "  [ERROR] Failed to load ONNX Engine or Tokenizer: " << e.what() << std::endl;
    }
}

SentimentAgent::~SentimentAgent() = default;

std::vector<SentimentResult> SentimentAgent::score_batch(const std::vector<SentimentInput>& items) {
    std::vector<SentimentResult> results;
    if (items.empty()) return results;

    std::cout << "  [INFO] Running native C++ ONNX FinBERT engine to score " << items.size() << " excerpts..." << std::endl;

    if (!engine_ || !tokenizer_) {
        std::cerr << "  [ERROR] ONNX Engine or Tokenizer not initialized." << std::endl;
        return results;
    }

    for (const auto& item : items) {
        SentimentResult res;
        res.excerpt = item.text.length() > 280 ? item.text.substr(0, 280) : item.text;
        res.segment = item.segment;
        res.source_url = item.source_url;
        res.title = item.title;
        res.published_at = item.published_at;
        
        try {
            std::vector<int> tokens = tokenizer_->encode(item.text, 512);
            std::vector<float> probs = engine_->score_sentiment(tokens);
            
            // [Positive, Negative, Neutral]
            float pos = probs[0];
            float neg = probs[1];
            float neu = probs[2];
            
            if (pos > neg && pos > neu) {
                res.label = "POSITIVE";
                res.confidence = pos;
            } else if (neg > pos && neg > neu) {
                res.label = "NEGATIVE";
                res.confidence = neg;
            } else {
                res.label = "NEUTRAL";
                res.confidence = neu;
            }
            res.ok = true;
            
        } catch (...) {
            res.label = "NEUTRAL";
            res.confidence = 0.0;
            res.ok = false;
        }
        
        results.push_back(res);
    }

    return results;
}

AggregateSentiment SentimentAgent::aggregate_sentiment(const std::string& ticker, const std::vector<SentimentResult>& results) {
    AggregateSentiment agg;
    agg.ticker = ticker;
    agg.overall_label = "NEUTRAL";
    agg.overall_score = 0.0;
    agg.trend = "stable";

    int failed_count = 0;
    for (const auto& r : results) {
        if (!r.ok) failed_count++;
    }

    if (results.empty() || ((double)failed_count / results.size()) >= 0.5) {
        agg.scoring_failed = true;
        return agg;
    }

    auto get_sign = [](const std::string& l) {
        if (l == "POSITIVE") return 1.0;
        if (l == "NEGATIVE") return -1.0;
        return 0.0;
    };

    double weighted_sum = 0.0;
    double total_weight = 0.0;

    for (const auto& r : results) {
        if (!r.ok) continue;
        
        double weight = 1.0;
        if (r.segment.find("EARNINGS_CALL_QA") != std::string::npos) weight = 2.0;
        else if (r.segment.find("EARNINGS_CALL") != std::string::npos) weight = 1.5;
        else if (r.segment.find("FILING") != std::string::npos) weight = 1.2;
        
        if (r.is_fls) weight *= 1.5;

        weighted_sum += get_sign(r.label) * r.confidence * weight;
        total_weight += weight;

        agg.sample_size[r.segment]++;
        agg.component_scores[r.segment] += get_sign(r.label) * r.confidence;

        for (const auto& aspect : r.aspects) {
            std::string aspect_key = "Aspect: " + aspect;
            agg.sample_size[aspect_key]++;
            agg.component_scores[aspect_key] += get_sign(r.label) * r.confidence;
        }
    }

    if (total_weight > 0) {
        agg.overall_score = weighted_sum / total_weight;
    }

    for (auto& [seg, sum_score] : agg.component_scores) {
        if (agg.sample_size[seg] > 0) {
            sum_score /= agg.sample_size[seg];
        }
    }

    if (agg.overall_score > 0.20) agg.overall_label = "POSITIVE";
    else if (agg.overall_score < -0.20) agg.overall_label = "NEGATIVE";
    
    if (agg.overall_score > 0.5) agg.trend = "improving";
    else if (agg.overall_score < -0.5) agg.trend = "deteriorating";

    return agg;
}
