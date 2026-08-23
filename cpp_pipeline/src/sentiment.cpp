#include "sentiment.h"
#include <cpr/cpr.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <cmath>
#include <algorithm>

using json = nlohmann::json;

SentimentAgent::SentimentAgent(const std::string& hf_api_key) : hf_api_key_(hf_api_key) {}

SentimentResult SentimentAgent::score_text(const std::string& text, const std::string& segment) {
    SentimentResult res;
    res.segment = segment;
    res.label = "NEUTRAL";
    res.confidence = 0.0;
    res.excerpt = text.substr(0, 280);

    if (hf_api_key_.empty()) {
        std::cerr << "[ERROR] HF_API_TOKEN is missing. Skipping sentiment." << std::endl;
        return res;
    }

    std::string url = "https://api-inference.huggingface.co/models/ProsusAI/finbert";
    
    // Truncate to ~512 chars for context window
    std::string input_text = text.length() > 512 ? text.substr(0, 512) : text;
    json payload = {{"inputs", input_text}};
    
    cpr::Response r = cpr::Post(
        cpr::Url{url},
        cpr::Header{
            {"Authorization", "Bearer " + hf_api_key_},
            {"Content-Type", "application/json"}
        },
        cpr::Body{payload.dump()},
        cpr::Timeout{20000} // 20s timeout
    );

    if (r.status_code != 200) {
        std::cerr << "  [WARN] HF API failed (" << r.status_code << "): " << r.text << std::endl;
        return res;
    }

    try {
        json j = json::parse(r.text);
        if (j.is_array() && !j.empty() && j[0].is_array()) {
            j = j[0];
        }

        if (j.is_array()) {
            double best_score = -1.0;
            std::string best_label = "neutral";
            for (const auto& item : j) {
                double score = item.value("score", 0.0);
                if (score > best_score) {
                    best_score = score;
                    best_label = item.value("label", "neutral");
                }
            }
            
            std::transform(best_label.begin(), best_label.end(), best_label.begin(), ::toupper);
            res.label = best_label;
            res.confidence = best_score;
        }
    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Failed to parse HF API JSON: " << e.what() << std::endl;
    }

    return res;
}

AggregateSentiment SentimentAgent::aggregate_sentiment(const std::string& ticker, const std::vector<SentimentResult>& results) {
    AggregateSentiment agg;
    agg.ticker = ticker;
    agg.overall_label = "NEUTRAL";
    agg.overall_score = 0.0;
    agg.trend = "stable";

    if (results.empty()) return agg;

    auto get_sign = [](const std::string& l) {
        if (l == "POSITIVE") return 1.0;
        if (l == "NEGATIVE") return -1.0;
        return 0.0;
    };

    double weighted_sum = 0.0;
    double total_weight = 0.0;

    for (const auto& r : results) {
        // Since we aren't tracking dates deeply in this port for simplicity, we treat all weights as 1.0
        double weight = 1.0;
        weighted_sum += get_sign(r.label) * r.confidence * weight;
        total_weight += weight;

        agg.sample_size[r.segment]++;
        agg.component_scores[r.segment] += get_sign(r.label) * r.confidence;
    }

    if (total_weight > 0) {
        agg.overall_score = weighted_sum / total_weight;
    }

    for (auto& [seg, sum_score] : agg.component_scores) {
        if (agg.sample_size[seg] > 0) {
            sum_score /= agg.sample_size[seg];
        }
    }

    if (agg.overall_score > 0.15) agg.overall_label = "POSITIVE";
    else if (agg.overall_score < -0.15) agg.overall_label = "NEGATIVE";

    return agg;
}
