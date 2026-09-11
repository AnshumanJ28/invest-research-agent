#ifndef LEXICON_SENTIMENT_H
#define LEXICON_SENTIMENT_H

#include <string>
#include <vector>
#include <unordered_set>

/**
 * LexiconSentiment — Loughran-McDonald Financial Lexicon Engine
 *
 * Uses the academically validated Loughran-McDonald (2011) financial sentiment
 * word lists, the industry standard for classifying financial text. These
 * lists were specifically curated from SEC 10-K filings to avoid the false
 * positives that generic sentiment dictionaries produce on financial language.
 *
 * Memory footprint: ~3–5 MB (hash sets of ~4,500 words).
 * CPU cost: O(n) per document, where n = number of words. Microsecond range.
 *
 * Categories:
 *   - NEGATIVE: ~2,355 words (e.g., litigation, default, impairment)
 *   - POSITIVE: ~354 words (e.g., profitable, improvement, outperform)
 *   - UNCERTAINTY: ~297 words (e.g., approximate, contingency, fluctuation)
 *   - LITIGIOUS: ~903 words (e.g., arbitration, defendant, lawsuit)
 *   - STRONG_MODAL: words indicating strong certainty (e.g., always, must, highest)
 *   - WEAK_MODAL: words indicating weak certainty (e.g., could, might, possibly)
 *   - FORWARD_LOOKING: phrases/words indicating future projections
 */

struct LexiconScore {
    int    positive_count   = 0;
    int    negative_count   = 0;
    int    uncertainty_count= 0;
    int    litigious_count  = 0;
    int    strong_modal     = 0;
    int    weak_modal       = 0;
    int    total_words      = 0;
    bool   is_forward_looking = false;

    // Derived: net sentiment score in [-1.0, 1.0]
    double net_score() const;

    // Label: POSITIVE / NEGATIVE / NEUTRAL
    std::string label() const;

    // Confidence: how much of the text is sentiment-bearing
    double confidence() const;
};

class LexiconSentiment {
public:
    LexiconSentiment();

    /// Score a single text passage
    LexiconScore score(const std::string& text) const;

private:
    /// Tokenize text into lowercase words
    static std::vector<std::string> tokenize(const std::string& text);

    std::unordered_set<std::string> positive_;
    std::unordered_set<std::string> negative_;
    std::unordered_set<std::string> uncertainty_;
    std::unordered_set<std::string> litigious_;
    std::unordered_set<std::string> strong_modal_;
    std::unordered_set<std::string> weak_modal_;
    std::unordered_set<std::string> forward_looking_;
};

#endif // LEXICON_SENTIMENT_H
