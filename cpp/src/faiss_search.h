#pragma once

#include <vector>
#include <string>

struct SearchResult {
    int chunk_id;
    float score;
};

class FaissEngine {
public:
    FaissEngine(int dimension = 384);
    ~FaissEngine();

    // Adds a batch of dense embeddings to the index
    void add_embeddings(const std::vector<std::vector<float>>& embeddings);

    // Performs Inner Product (IP) search for top_k results
    std::vector<SearchResult> search(const std::vector<float>& query_embedding, int top_k) const;

private:
    int dimension_;
    int num_vectors_ = 0;
    std::vector<float> flat_database_;
};
