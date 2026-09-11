#pragma once

#include <string>
#include <vector>
#include <memory>

// Forward declarations / stub types to avoid exposing full ONNX Runtime headers globally
namespace Ort {
    struct Env;
    struct Session;
    struct MemoryInfo;
}

class OnnxEngine {
public:
    OnnxEngine(const std::string& model_path);
    ~OnnxEngine();

    // Runs sentiment inference (FinBERT)
    // Returns {positive_score, negative_score, neutral_score}
    std::vector<float> score_sentiment(const std::vector<int>& input_ids);

    // Runs embedding extraction (MiniLM)
    // Returns 384-dimensional vector
    std::vector<float> extract_embeddings(const std::vector<int>& input_ids);

private:
    std::unique_ptr<Ort::Env> env_;
    std::unique_ptr<Ort::Session> session_;
    std::unique_ptr<Ort::MemoryInfo> memory_info_;
};
