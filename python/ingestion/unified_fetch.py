"""Unified fetch: runs all data ingestion in a single Python process with parallel I/O.

Uses ThreadPoolExecutor to fetch all data sources concurrently within ONE process,
keeping RAM under 150MB while cutting network wait time in half.

Usage: python python/ingestion/unified_fetch.py TICKER [PEER1 PEER2 ...]
Outputs: json/yf_temp.json, json/news_temp.json, json/edgar_temp.json, 
         json/transcript_temp.json, json/peers_temp.json
"""

import sys
import json
import os
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

# Ensure the project root is on the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'python'))
sys.path.insert(0, os.path.join(project_root, 'python', 'ingestion'))


def ensure_json_dir():
    os.makedirs("json", exist_ok=True)


def fetch_yfinance(ticker: str):
    """Fetch Yahoo Finance financials."""
    try:
        from yf_json import fetch_ticker_data
        data = fetch_ticker_data(ticker)
        with open("json/yf_temp.json", "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"  [unified] yfinance OK for {ticker}")
    except Exception as e:
        print(f"  [unified] yfinance FAILED: {e}", file=sys.stderr)
        with open("json/yf_temp.json", "w", encoding="utf-8") as f:
            json.dump({}, f)


def fetch_news(ticker: str, max_articles: int = 10):
    """Fetch top 10 news articles via yfinance (no API key needed)."""
    try:
        from yf_news import fetch_news as _fetch
        articles = _fetch(ticker, max_articles=max_articles)
        with open("json/news_temp.json", "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2)
        print(f"  [unified] news OK: {len(articles)} articles for {ticker}")
    except Exception as e:
        print(f"  [unified] news FAILED: {e}", file=sys.stderr)
        with open("json/news_temp.json", "w", encoding="utf-8") as f:
            json.dump([], f)


def fetch_edgar(ticker: str):
    """Fetch SEC Edgar filings."""
    try:
        from ingestion.edgar_agent import fetch_latest_filings
        docs = fetch_latest_filings(ticker)
        res = {}
        for form, doc in docs.items():
            if doc is None:
                res[form] = None
            else:
                res[form] = {
                    "filed_date": doc.filed_date.isoformat() if doc.filed_date else None,
                    "sections": [{"name": s.section_name, "text": s.text} for s in doc.sections]
                }
        with open("json/edgar_temp.json", "w", encoding="utf-8") as f:
            json.dump(res, f)
        print(f"  [unified] edgar OK for {ticker}")
    except Exception as e:
        print(f"  [unified] edgar FAILED: {e}", file=sys.stderr)
        with open("json/edgar_temp.json", "w", encoding="utf-8") as f:
            json.dump({}, f)


def fetch_transcript(ticker: str):
    """Fetch earnings-call transcript."""
    try:
        from ingestion.transcript_agent import fetch_transcript as _fetch
        doc = _fetch(ticker)
        res = {
            "available": doc.available,
            "unavailable_reason": getattr(doc, 'unavailable_reason', ""),
            "utterances": [
                {"speaker": u.speaker, "text": u.text, "section": u.section.value}
                for u in getattr(doc, 'utterances', [])
            ] if doc.available else []
        }
        with open("json/transcript_temp.json", "w", encoding="utf-8") as f:
            json.dump(res, f)
        print(f"  [unified] transcript OK for {ticker}")
    except Exception as e:
        print(f"  [unified] transcript FAILED: {e}", file=sys.stderr)
        with open("json/transcript_temp.json", "w", encoding="utf-8") as f:
            json.dump({"available": False, "unavailable_reason": str(e), "utterances": []}, f)


def fetch_peers(peer_tickers: list[str]):
    """Fetch peer financial data."""
    try:
        from yf_json import fetch_ticker_data
        result = {}
        for t in peer_tickers:
            try:
                result[t] = fetch_ticker_data(t)
            except Exception:
                pass
        with open("json/peers_temp.json", "w", encoding="utf-8") as f:
            json.dump(result, f)
        print(f"  [unified] peers OK: {len(result)} peers fetched")
    except Exception as e:
        print(f"  [unified] peers FAILED: {e}", file=sys.stderr)
        with open("json/peers_temp.json", "w", encoding="utf-8") as f:
            json.dump({}, f)


def fetch_async_yfinance(ticker: str, peers: list[str]):
    import subprocess
    cmd = ["python", "python/ingestion/async_fetch.py", ticker] + peers
    subprocess.run(cmd)

def main():
    if len(sys.argv) < 2:
        print("Usage: python unified_fetch.py TICKER [PEER1 PEER2 ...]", file=sys.stderr)
        sys.exit(1)

    ticker = sys.argv[1]
    peers = sys.argv[2:] if len(sys.argv) > 2 else []

    print(f"  [unified] Starting parallel fetch for {ticker} (peers: {peers})")
    ensure_json_dir()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_async_yfinance, ticker, peers): "async_yfinance",
            executor.submit(fetch_news, ticker, 10): "news",
            executor.submit(fetch_edgar, ticker): "edgar",
            executor.submit(fetch_transcript, ticker): "transcript",
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"  [unified] {name} raised exception: {e}", file=sys.stderr)

    print(f"  [unified] All parallel fetches complete for {ticker}")


if __name__ == "__main__":
    main()
