#pragma once

#include <string>
#include <vector>

struct NewsArticle {
    std::string title;
    std::string source;
    std::string published_at;
    std::string url;
    std::string snippet;
};

class NewsAgent {
public:
    NewsAgent(const std::string& api_key);
    std::vector<NewsArticle> fetch_news(const std::string& ticker);

private:
    std::string api_key_;
};
