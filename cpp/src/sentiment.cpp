#include "sentiment.h"
#include "lexicon_sentiment.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>
#include <cmath>
#include <algorithm>
using json = nlohmann::json;
SentimentAgent::SentimentAgent() {
    try {
        lexicon_ = std::make_unique<LexiconSentiment>();
        std::cout << "  [INFO] Initialized Loughran-McDonald Financial Lexicon Engine." << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "  [ERROR] Failed to initialize Lexicon Engine: " << e.what() << std::endl;
    }
}
SentimentAgent::~SentimentAgent() = default;
std::vector<SentimentResult> SentimentAgent::score_batch(const std::vector<SentimentInput>& items) {
    std::vector<SentimentResult> results;
    if (items.empty()) return results;
    std::cout << "  [INFO] Scoring " << items.size()
              << " excerpts with Loughran-McDonald Lexicon..." << std::endl;
    if (!lexicon_) {
        std::cerr << "  [ERROR] Lexicon Engine not initialized." << std::endl;
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
            LexiconScore ls = lexicon_->score(item.text);
            res.label = ls.label();
            res.confidence = ls.confidence();
            res.is_fls = ls.is_forward_looking;
            res.ok = true;
        } catch (...) {
            res.label = "NEUTRAL";
            res.confidence = 0.0;
            res.is_fls = false;
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
