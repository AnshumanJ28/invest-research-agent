# Investment Research Ingestion & Analysis Pipeline

A modular, production-ready Python pipeline designed to ingest company financial filings, transcripts, and news, and perform deep ratio, sentiment, and peer analysis.

This system is structured into two primary agentic layers:
1. **Data Ingestion Agent** (Retrieves raw SEC/exchanges filing documents, news articles, and earning call transcripts).
2. **Analysis & NLP Agent** (Computes financial ratios, performs sentiment scoring using FinBERT/TextBlob, and generates side-by-side peer comparisons).

---

## 📂 Project Structure

```
├── analysis/               # Analysis & NLP Agent layer
│   ├── schemas.py          # Shared output contracts (RatioResult, SentimentResult, etc.)
│   ├── ratios.py           # Financial Ratio Agent (liquidity, profitability, etc.)
│   ├── sentiment.py        # Sentiment Analysis Agent (FinBERT / TextBlob)
│   ├── competitors.py      # Peer selection & side-by-side comparison
│   ├── interpretation.py   # Threshold-based healthy/watch/concerning evaluation
│   └── utils.py            # Financial and metadata adapter utilities
│
├── ingestion/              # Data Ingestion Agent layer
│   ├── schemas.py          # Strict data contracts (BaseModel definitions)
│   ├── storage.py          # PostgreSQL persistence layer and DDL schemas
│   ├── yfinance_agent.py   # Primary financial statement extraction (Yahoo Finance)
│   ├── edgar_agent.py      # Indian exchange filing (NSE/BSE) scraper
│   ├── news_agent.py       # News article fetcher (NewsAPI, etc.)
│   ├── transcript_agent.py # Earnings call transcript extraction (Motley Fool, etc.)
│   └── utils.py            # Shared tools (exponential retry, token-bucket rate limiter)
│
├── tests/                  # Unit test suite matching each agent component
├── pipeline_test.py        # Standalone parallel smoke test script
├── run_analysis_pipeline.py# Production entry point running the full pipeline end-to-end
├── requirements.txt        # PIP dependencies
├── .env.example            # Template for local environment variables
└── .gitignore              # Files ignored by git (venv, caches, etc.)
```

---

## ⚡ Quick Start

### 1. Prerequisites & Environment Setup

Clone this repository and create a Python virtual environment:

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows)
.\venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 2. Environment Variables

Copy the `.env.example` template to create your `.env` file:

```powershell
cp .env.example .env
```

Customize the API keys and configurations inside your `.env` file (e.g. `HF_API_TOKEN` for Hugging Face FinBERT sentiment scoring, `NEWSAPI_KEY` for news article ingestion, and `DATABASE_URL` for PostgreSQL).

---

## 🚀 Running the Pipeline

You can run the end-to-end pipeline using `run_analysis_pipeline.py` by passing the target company's stock ticker symbol:

```powershell
python run_analysis_pipeline.py INFY.NS
```

This will run:
1. **Financial Statement Ingestion**: Fetches statements for the target company and automatically discovers or selects peers.
2. **Ratios & Sentiment Analysis**: Calculates leverage, profitability, liquidity, and valuation ratios, and runs FinBERT or TextBlob sentiment analysis.
3. **Peer Comparison**: Selects a relevant competitor (e.g. `WIPRO.NS`) and produces a comparison table of key ratios.

---

## 🧪 Testing

To run the automated unit test suite:

```powershell
pytest
```

To run the parallel integration smoke test script (which checks all ingestion agents concurrently):

```powershell
python pipeline_test.py RELIANCE.NS
```

---

## 📖 Component Documentation

For details on the design decisions, assumptions, and API outputs of each sub-agent layer, check out their respective documentation:
- 📥 [Data Ingestion Agent Details (ingestion/README.md)](file:///c:/Users/anshu/Downloads/agent/ingestion/README.md)
- 📊 [Analysis & NLP Agent Details (analysis/README.md)](file:///c:/Users/anshu/Downloads/agent/analysis/README.md)
