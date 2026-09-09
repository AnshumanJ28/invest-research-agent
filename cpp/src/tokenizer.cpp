#include "tokenizer.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cctype>

BertTokenizer::BertTokenizer(const std::string& vocab_path) {
    load_vocab(vocab_path);
}

void BertTokenizer::load_vocab(const std::string& vocab_path) {
    std::ifstream file(vocab_path);
    if (!file.is_open()) {
        std::cerr << "Failed to open vocab file: " << vocab_path << std::endl;
        return;
    }
    std::string line;
    int index = 0;
    while (std::getline(file, line)) {
        if (!line.empty() && line.back() == '\r') {
            line.pop_back();
        }
        vocab_[line] = index++;
    }
    
    // Attempt to override special tokens if they exist in vocab
    if (vocab_.find("[UNK]") != vocab_.end()) unk_token_id_ = vocab_["[UNK]"];
    if (vocab_.find("[CLS]") != vocab_.end()) cls_token_id_ = vocab_["[CLS]"];
    if (vocab_.find("[SEP]") != vocab_.end()) sep_token_id_ = vocab_["[SEP]"];
}

std::vector<std::string> BertTokenizer::basic_tokenize(const std::string& text) const {
    std::vector<std::string> words;
    std::string current_word;
    for (char c : text) {
        unsigned char uc = static_cast<unsigned char>(c);
        c = std::tolower(uc);
        if (std::isspace(uc) || std::ispunct(uc)) {
            if (!current_word.empty()) {
                words.push_back(current_word);
                current_word.clear();
            }
            if (std::ispunct(uc)) {
                words.push_back(std::string(1, c));
            }
        } else {
            current_word += c;
        }
    }
    if (!current_word.empty()) {
        words.push_back(current_word);
    }
    return words;
}

std::vector<int> BertTokenizer::wordpiece_tokenize(const std::vector<std::string>& words) const {
    std::vector<int> tokens;
    for (const auto& word : words) {
        if (word.empty()) continue;
        
        bool is_bad = false;
        std::vector<int> sub_tokens;
        int start = 0;
        int word_len = word.length();
        
        while (start < word_len) {
            int end = word_len;
            std::string cur_substr = "";
            bool found = false;
            
            while (start < end) {
                std::string substr = word.substr(start, end - start);
                if (start > 0) {
                    substr = "##" + substr;
                }
                
                auto it = vocab_.find(substr);
                if (it != vocab_.end()) {
                    cur_substr = substr;
                    sub_tokens.push_back(it->second);
                    found = true;
                    break;
                }
                end -= 1;
            }
            
            if (!found) {
                is_bad = true;
                break;
            }
            start = end;
        }
        
        if (is_bad) {
            tokens.push_back(unk_token_id_);
        } else {
            tokens.insert(tokens.end(), sub_tokens.begin(), sub_tokens.end());
        }
    }
    return tokens;
}

std::vector<int> BertTokenizer::encode(const std::string& text, int max_length) const {
    std::vector<std::string> words = basic_tokenize(text);
    std::vector<int> tokens = wordpiece_tokenize(words);
    
    std::vector<int> final_tokens;
    final_tokens.reserve(tokens.size() + 2);
    final_tokens.push_back(cls_token_id_);
    
    for (int t : tokens) {
        if (final_tokens.size() >= max_length - 1) break;
        final_tokens.push_back(t);
    }
    
    final_tokens.push_back(sep_token_id_);
    return final_tokens;
}
