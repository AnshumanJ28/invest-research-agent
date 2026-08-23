#pragma once

#include <string>
#include <vector>
#include <map>

struct EdgarSection {
    std::string name;
    std::string text;
};

struct EdgarDocument {
    std::string filed_date;
    std::vector<EdgarSection> sections;
};

class EdgarAgent {
public:
    EdgarAgent() = default;
    std::map<std::string, EdgarDocument> fetch_latest_filings(const std::string& ticker);
};
