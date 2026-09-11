#ifndef LEXICON_SENTIMENT_H
#define LEXICON_SENTIMENT_H
#include <string>
#include <vector>
#include <unordered_set>
struct LexiconScore {
    int    positive_count   = 0;
    int    negative_count   = 0;
    int    uncertainty_count= 0;
    int    litigious_count  = 0;
    int    strong_modal     = 0;
    int    weak_modal       = 0;
    int    total_words      = 0;
    bool   is_forward_looking = false;
    double net_score() const;
    std::string label() const;
    double confidence() const;
};
class LexiconSentiment {
public:
    LexiconSentiment();
    LexiconScore score(const std::string& text) const;
private:
    static std::vector<std::string> tokenize(const std::string& text);
    std::unordered_set<std::string> positive_;
    std::unordered_set<std::string> negative_;
    std::unordered_set<std::string> uncertainty_;
    std::unordered_set<std::string> litigious_;
    std::unordered_set<std::string> strong_modal_;
    std::unordered_set<std::string> weak_modal_;
    std::unordered_set<std::string> forward_looking_;
};
#endif 
