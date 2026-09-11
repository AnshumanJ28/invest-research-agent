#include "news_agent.h"
#include <nlohmann/json.hpp>
#include <iostream>
#include <fstream>

using json = nlohmann::json;

NewsAgent::NewsAgent(const std::string& api_key) : api_key_(api_key) {}

std::vector<NewsArticle> NewsAgent::fetch_news(const std::string& ticker, const std::string& generation_id) {
    std::vector<NewsArticle> articles;
    std::string in_path = "json/" + generation_id + "_news_temp.json";
    
    std::ifstream file(in_path);
    if (!file.is_open()) {
        std::cerr << "[ERROR] Could not read " << in_path << ". Java ingestion might have failed." << std::endl;
        return articles;
    }

    try {
        json j;
        file >> j;
        
        if (j.is_array()) {
            for (const auto& item : j) {
                NewsArticle article;
                article.title = item.value("title", "");
                
                // Handle NewsAPI nested source format: {"source": {"id": null, "name": "Reuters"}}
                // Also handle flat format: {"source": "Reuters"}
                if (item.contains("source") && item["source"].is_object()) {
                    article.source = item["source"].value("name", "");
                } else {
                    article.source = item.value("source", "");
                }
                
                // Handle both NewsAPI camelCase and flat format
                if (item.contains("publishedAt")) {
                    article.published_at = item.value("publishedAt", "");
                } else {
                    article.published_at = item.value("published_at", "");
                }
                
                article.url = item.value("url", "");
                // NewsAPI uses "description" for the snippet
                if (item.contains("description")) {
                    article.snippet = item.value("description", "");
                } else {
                    article.snippet = item.value("snippet", "");
                }
                articles.push_back(article);
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[ERROR] Failed to parse news JSON: " << e.what() << std::endl;
    }

    return articles;
}
