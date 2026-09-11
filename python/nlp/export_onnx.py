import os
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer
try:
    from onnxruntime.quantization import quantize_dynamic, QuantType
    HAS_ORT = True
except ImportError:
    HAS_ORT = False
    print("Warning: onnxruntime not installed, quantization will be skipped unless installed.")
def export_model():
    model_name = "ProsusAI/finbert"
    print(f"Loading {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.eval()
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "cpp", "models")
    os.makedirs(out_dir, exist_ok=True)
    vocab_path = os.path.join(out_dir, "vocab.txt")
    tokenizer.save_vocabulary(out_dir)
    print(f"Saved vocab to {vocab_path}")
    onnx_path = os.path.join(out_dir, "finbert.onnx")
    onnx_int8_path = os.path.join(out_dir, "finbert_int8.onnx")
    dummy_input = torch.zeros(1, 128, dtype=torch.long)
    dummy_mask = torch.zeros(1, 128, dtype=torch.long)
    dummy_types = torch.zeros(1, 128, dtype=torch.long)
    print(f"Exporting to {onnx_path}...")
    torch.onnx.export(
        model, 
        (dummy_input, dummy_mask, dummy_types), 
        onnx_path,
        input_names=["input_ids", "attention_mask", "token_type_ids"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "token_type_ids": {0: "batch_size", 1: "sequence_length"},
            "logits": {0: "batch_size"}
        },
        opset_version=14,
        do_constant_folding=True
    )
    print("Export successful.")
    if HAS_ORT:
        print(f"Quantizing to {onnx_int8_path}...")
        quantize_dynamic(onnx_path, onnx_int8_path, weight_type=QuantType.QUInt8)
        print("Quantization successful.")
        os.remove(onnx_path)
    else:
        print("Please pip install onnxruntime to perform quantization.")
if __name__ == "__main__":
    export_model()
