#include "news_agent.h"
#include <cpr/cpr.h>
#include <nlohmann/json.hpp>
#include <iostream>

using json = nlohmann::json;

NewsAgent::NewsAgent(const std::string& api_key) : api_key_(api_key) {}

std::vector<NewsArticle> NewsAgent::fetch_news(const std::string& ticker) {
    std::vector<NewsArticle> articles;
    
    if (api_key_.empty()) {
        std::cerr << "[ERROR] NewsAPI key is missing!" << std::endl;
        return articles;
    }

    // Remove exchange suffixes for Indian tickers (e.g. INFY.NS -> INFY)
    std::string base_ticker = ticker;
    size_t dot_pos = base_ticker.find('.');
    if (dot_pos != std::string::npos) {
        base_ticker = base_ticker.substr(0, dot_pos);
    }
    
    std::string query = base_ticker;
    std::string url = "https://newsapi.org/v2/everything?q=" + query + "&sortBy=publishedAt&language=en&apiKey=" + api_key_;
    std::cout << "  [DEBUG] URL: " << url << std::endl;

    cpr::Response r = cpr::Get(
        cpr::Url{url},
        cpr::Header{{"User-Agent", "InvestResearchAgent/1.0"}}
    );

    if (r.status_code == 0) {
        std::cerr << "[ERROR] Network request failed completely: " << r.error.message << std::endl;
        return articles;
    } else if (r.status_code != 200) {
        std::cerr << "[ERROR] NewsAPI fetch failed with HTTP status: " << r.status_code << std::endl;
        return articles;
    }

    try {
        json j = json::parse(r.text);
        if (j["status"] == "ok") {
            for (const auto& item : j["articles"]) {
                NewsArticle article;
                article.title = item.value("title", "");
                article.source = item["source"].value("name", "");
                article.published_at = item.value("publishedAt", "");
                article.url = item.value("url", "");
                article.snippet = item.value("description", "");
                articles.push_back(article);
                
                // Limit to 5 articles for now
                if (articles.size() >= 5) break;
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Failed to parse NewsAPI JSON: " << e.what() << std::endl;
    }

    return articles;
}
