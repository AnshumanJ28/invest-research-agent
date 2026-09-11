#pragma once
#include <string>
#include <vector>
#include <memory>
namespace Ort {
    struct Env;
    struct Session;
    struct MemoryInfo;
}
class OnnxEngine {
public:
    OnnxEngine(const std::string& model_path);
    ~OnnxEngine();
    std::vector<float> score_sentiment(const std::vector<int>& input_ids);
    std::vector<float> extract_embeddings(const std::vector<int>& input_ids);
private:
    std::unique_ptr<Ort::Env> env_;
    std::unique_ptr<Ort::Session> session_;
    std::unique_ptr<Ort::MemoryInfo> memory_info_;
};
