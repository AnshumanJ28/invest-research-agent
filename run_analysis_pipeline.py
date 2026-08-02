import sys
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from types import SimpleNamespace
from datetime import datetime, timezone

# Add parent directory to path to import ingestion and analysis
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestion.yfinance_agent import fetch_financial_statements
from ingestion.news_agent import fetch_news
from ingestion.transcript_agent import fetch_transcript
from analysis.ratios import compute_ratios
from analysis.interpretation import interpret
from analysis.sentiment import score_news_batch, score_transcript, aggregate_sentiment
from analysis.competitors import compare_peers

CANDIDATE_POOL = [
    {"ticker": "INFY.NS", "industry": "Information Technology Services"},
    {"ticker": "WIPRO.NS", "industry": "Information Technology Services"},
    {"ticker": "TCS.NS", "industry": "Information Technology Services"},
    {"ticker": "TATAMOTORS.NS", "industry": "Auto Manufacturers"},
    {"ticker": "M&M.NS", "industry": "Auto Manufacturers"},
    {"ticker": "ICICIBANK.NS", "industry": "Banks—Regional"},
    {"ticker": "HDFCBANK.NS", "industry": "Banks—Regional"},
    {"ticker": "RELIANCE.NS", "industry": "Oil & Gas Refining & Marketing"},
    {"ticker": "TATASTEEL.NS", "industry": "Steel"},
]

def main():
    ticker = sys.argv[1] if len(sys.argv) > 1 else "INFY.NS"
    ticker = ticker.upper().strip()
    
    # Dynamically select peer if not provided as 2nd arg
    if len(sys.argv) > 2:
        peer = sys.argv[2].upper().strip()
    else:
        # Try to find industry of the primary ticker
        primary_industry = None
        for cand in CANDIDATE_POOL:
            if cand["ticker"] == ticker:
                primary_industry = cand["industry"]
                break
        
        if primary_industry is None:
            # Fetch dynamically from yfinance
            try:
                import yfinance as yf
                tk = yf.Ticker(ticker)
                primary_industry = tk.info.get("industry")
            except Exception:
                pass
                
        # Select peer using the select_peers function
        peers = []
        if primary_industry:
            from analysis.competitors import select_peers
            # Filter pool to exclude the primary ticker itself
            pool_excluding_primary = [c for c in CANDIDATE_POOL if c["ticker"] != ticker]
            peers = select_peers(primary_industry, pool_excluding_primary, max_peers=1)
            
        peer = peers[0] if peers else ("WIPRO.NS" if ticker != "WIPRO.NS" else "INFY.NS")
            
    print(f"=== Running analysis pipeline for {ticker} ===")
    
    # 1. Ingestion
    print("\n--- Ingesting primary ticker data ---")
    statements = fetch_financial_statements(ticker)
    news = fetch_news(ticker)
    transcript = fetch_transcript(ticker)
    
    # 2. Ratios & Interpretation
    print("\n--- Computing & Interpreting Ratios ---")
    ratios = compute_ratios(statements)
    interpreted = interpret(ratios)
    
    for r in interpreted:
        status = r.health_flag.value if hasattr(r.health_flag, "value") else str(r.health_flag)
        print(f"  {r.name:20s}: {r.value if r.computable else 'N/A':<10} [{status:<10}] {r.narrative or r.note or ''}")
        
    # 3. Sentiment Analysis
    print("\n--- Scoring Sentiment ---")
    hf_token = os.environ.get("HF_API_TOKEN")
    if not hf_token:
        print("  [WARN] HF_API_TOKEN not set in environment. Simulating sentiment scoring...")
        # Mock score results since token is missing
        from analysis.schemas import SentimentResult, SentimentLabel, SentimentSegment
        from ingestion.schemas import CitationMetadata, DocumentType
        from analysis.utils import to_source_ref
        
        mock_meta = CitationMetadata(ticker=ticker, document_type=DocumentType.NEWS_ARTICLE,
                                     source_name="mock_source", source_url="https://example.com", as_of_date=datetime.now(timezone.utc))
        results = [
            SentimentResult(segment=SentimentSegment.NEWS, label=SentimentLabel.POSITIVE, confidence=0.85, excerpt="Good growth", source=to_source_ref(mock_meta)),
            SentimentResult(segment=SentimentSegment.NEWS, label=SentimentLabel.NEUTRAL, confidence=0.9, excerpt="Stable output", source=to_source_ref(mock_meta)),
        ]
    else:
        try:
            from analysis.sentiment import _call_finbert
            # Wake up / test model
            _call_finbert("test")
        except Exception as e:
            print(f"  [WARN] Hugging Face Inference API check failed: {e}")
            print("  (If it is a 503 error, the model is simply waking up. Wait 15-20 seconds and run again.)")
            
        results = score_news_batch(news)
        if transcript.available:
            results.extend(score_transcript(transcript))
            
    agg = aggregate_sentiment(ticker, results)
    print(f"  Overall Score: {agg.overall_score} [{agg.overall_label.value}]")
    print(f"  Trend: {agg.trend}")
    print(f"  Sample size: {agg.sample_size}")
    
    # 4. Peer Comparison
    print(f"\n--- Peer Comparison with {peer} ---")
    comparison = compare_peers(
        primary_ticker=ticker,
        primary_ratios=interpreted,
        peer_tickers=[peer],
        fetch_statements=fetch_financial_statements
    )
    
    print(f"  Peer selection: {comparison.peer_selection_method}")
    print("  Comparison table:")
    for ratio_name, columns in comparison.comparison_table.items():
        primary_val = columns.get(ticker)
        peer_val = columns.get(peer)
        print(f"    {ratio_name:20s} | {ticker}: {primary_val if primary_val is not None else 'N/A':<10} | {peer}: {peer_val if peer_val is not None else 'N/A'}")

if __name__ == "__main__":
    main()
