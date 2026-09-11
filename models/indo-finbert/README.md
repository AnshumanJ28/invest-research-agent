# models/indo-finbert

This directory holds the **local FinBERT model weights** used by the
air-gapped sentiment analysis engine (`analysis/sentiment.py`).

## One-Time Download (requires internet)

Run this once on a machine with internet access, then copy the entire
`models/indo-finbert/` directory to the air-gapped system:

```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Use stock ProsusAI/finbert, or substitute your own fine-tuned Indo-FinBERT
model_id = "ProsusAI/finbert"

tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForSequenceClassification.from_pretrained(model_id)

tokenizer.save_pretrained("models/indo-finbert")
model.save_pretrained("models/indo-finbert")
```

## Expected Contents After Download

```
models/indo-finbert/
├── config.json
├── model.safetensors      (or pytorch_model.bin)
├── special_tokens_map.json
├── tokenizer_config.json
├── tokenizer.json
└── vocab.txt
```

## Override Path

Set the environment variable `SENTIMENT_MODEL_PATH` to use a different
directory:

```bash
export SENTIMENT_MODEL_PATH=/path/to/your/custom-finbert
```
