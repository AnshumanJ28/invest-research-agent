#include "onnx_engine.h"
#include <iostream>
#include <stdexcept>
#include <numeric>
#include <cmath>
#include <algorithm>
#include <onnxruntime_cxx_api.h>
OnnxEngine::OnnxEngine(const std::string& model_path) {
    std::cout << "[ONNX] Initializing ONNX Runtime..." << std::endl;
    env_ = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_WARNING, "invest_agent");
    Ort::SessionOptions session_options;
    session_options.SetIntraOpNumThreads(1);
    session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    std::wstring w_model_path(model_path.begin(), model_path.end());
    session_ = std::make_unique<Ort::Session>(*env_, w_model_path.c_str(), session_options);
    memory_info_ = std::make_unique<Ort::MemoryInfo>(Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault));
    std::cout << "[ONNX] Successfully loaded model: " << model_path << std::endl;
}
OnnxEngine::~OnnxEngine() = default;
std::vector<float> OnnxEngine::score_sentiment(const std::vector<int>& input_ids) {
    if (input_ids.empty()) return {0.0f, 0.0f, 0.0f};
    size_t seq_len = input_ids.size();
    std::vector<int64_t> input_ids_i64(seq_len);
    std::vector<int64_t> attention_mask_i64(seq_len, 1);
    std::vector<int64_t> token_type_ids_i64(seq_len, 0);
    for (size_t i = 0; i < seq_len; ++i) {
        input_ids_i64[i] = input_ids[i];
    }
    std::vector<int64_t> input_node_dims = {1, static_cast<int64_t>(seq_len)};
    auto input_ids_tensor = Ort::Value::CreateTensor<int64_t>(
        *memory_info_, input_ids_i64.data(), input_ids_i64.size(),
        input_node_dims.data(), input_node_dims.size());
    auto attention_mask_tensor = Ort::Value::CreateTensor<int64_t>(
        *memory_info_, attention_mask_i64.data(), attention_mask_i64.size(),
        input_node_dims.data(), input_node_dims.size());
    auto token_type_ids_tensor = Ort::Value::CreateTensor<int64_t>(
        *memory_info_, token_type_ids_i64.data(), token_type_ids_i64.size(),
        input_node_dims.data(), input_node_dims.size());
    const char* input_names[] = {"input_ids", "attention_mask", "token_type_ids"};
    Ort::Value input_tensors[] = {std::move(input_ids_tensor), std::move(attention_mask_tensor), std::move(token_type_ids_tensor)};
    const char* output_names[] = {"logits"};
    auto output_tensors = session_->Run(
        Ort::RunOptions{nullptr}, 
        input_names, 
        input_tensors, 3, 
        output_names, 1);
    if (output_tensors.empty()) {
        throw std::runtime_error("ONNX Runtime returned empty output");
    }
    float* floatarr = output_tensors.front().GetTensorMutableData<float>();
    float max_val = std::max({floatarr[0], floatarr[1], floatarr[2]});
    float sum = 0.0f;
    for (int i = 0; i < 3; ++i) {
        sum += std::exp(floatarr[i] - max_val);
    }
    std::vector<float> probs(3);
    for (int i = 0; i < 3; ++i) {
        probs[i] = std::exp(floatarr[i] - max_val) / sum;
    }
    return probs; 
}
std::vector<float> OnnxEngine::extract_embeddings(const std::vector<int>& input_ids) {
    std::vector<float> dummy_embedding(384, 0.0f);
    if (!dummy_embedding.empty()) {
        dummy_embedding[0] = 1.0f; 
    }
    return dummy_embedding;
}
