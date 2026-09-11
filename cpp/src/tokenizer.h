#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <memory>

class BertTokenizer {
public:
    BertTokenizer(const std::string& vocab_path);
    ~BertTokenizer() = default;

    // Tokenizes text into a vector of vocabulary IDs
    std::vector<int> encode(const std::string& text, int max_length = 512) const;

private:
    std::unordered_map<std::string, int> vocab_;
    int unk_token_id_ = 100;
    int cls_token_id_ = 101;
    int sep_token_id_ = 102;

    void load_vocab(const std::string& vocab_path);
    std::vector<std::string> basic_tokenize(const std::string& text) const;
    std::vector<int> wordpiece_tokenize(const std::vector<std::string>& words) const;
};
