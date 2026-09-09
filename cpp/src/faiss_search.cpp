#include "faiss_search.h"
#include "simd_math.h"
#include <iostream>
#include <algorithm>
#include <numeric>
#include <stdexcept>

FaissEngine::FaissEngine(int dimension) : dimension_(dimension) {
    std::cout << "[FAISS] Initialized C++ Vector Engine (Dim: " << dimension_ << ")" << std::endl;
}

FaissEngine::~FaissEngine() = default;

void FaissEngine::add_embeddings(const std::vector<std::vector<float>>& embeddings) {
    for (const auto& emb : embeddings) {
        if (emb.size() != dimension_) {
            throw std::invalid_argument("Embedding dimension mismatch");
        }
        flat_database_.insert(flat_database_.end(), emb.begin(), emb.end());
        num_vectors_++;
    }
}

std::vector<SearchResult> FaissEngine::search(const std::vector<float>& query_embedding, int top_k) const {
    if (query_embedding.size() != dimension_) {
        throw std::invalid_argument("Query dimension mismatch");
    }

    std::vector<SearchResult> results;
    if (num_vectors_ == 0) return results;
    
    int k = std::min(top_k, num_vectors_);
    std::vector<int> out_indices(k);
    std::vector<float> out_scores(k);
    
    c_batch_vector_search(query_embedding.data(), flat_database_.data(), num_vectors_, dimension_, out_indices.data(), out_scores.data(), k);
    
    for(int i=0; i<k; ++i) {
        if (out_indices[i] != -1) {
            results.push_back({out_indices[i], out_scores[i]});
        }
    }

    return results;
}
