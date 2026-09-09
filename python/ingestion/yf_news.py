"""Fetch top 10 recent news articles for a ticker using yfinance (no API key needed)."""

import sys
import json
import warnings

warnings.filterwarnings('ignore')


def fetch_news(ticker: str, max_articles: int = 10) -> list[dict]:
    """Fetch news from Yahoo Finance and return as a list of dicts."""
    import yfinance as yf
    
    tkr = yf.Ticker(ticker)
    try:
        raw_news = tkr.news or []
    except Exception:
        raw_news = []
    
    articles = []
    for item in raw_news[:max_articles]:
        # yfinance wraps news in a nested "content" object
        content = item.get("content", item)
        
        # Extract provider name from nested object
        provider = content.get("provider", {})
        source_name = provider.get("displayName", "") if isinstance(provider, dict) else str(provider)
        
        # Extract URL - prefer clickThroughUrl, fallback to canonicalUrl
        url = ""
        click_through = content.get("clickThroughUrl", {})
        if isinstance(click_through, dict):
            url = click_through.get("url", "")
        if not url:
            canonical = content.get("canonicalUrl", {})
            if isinstance(canonical, dict):
                url = canonical.get("url", "")
        
        # Extract publication date
        pub_date = content.get("pubDate", content.get("displayTime", ""))
        
        import html
        
        # Extract description/summary
        summary = content.get("summary", content.get("description", content.get("title", "")))
        
        article = {
            "title": html.unescape(content.get("title", "")),
            "source": html.unescape(source_name),
            "publishedAt": pub_date,
            "url": url,
            "description": html.unescape(summary),
        }
        
        # Only include articles that have actual content
        if article["title"]:
            articles.append(article)
    
    return articles


def main():
    if len(sys.argv) < 2:
        print("Usage: python yf_news.py TICKER", file=sys.stderr)
        sys.exit(1)
    
    ticker = sys.argv[1]
    articles = fetch_news(ticker, max_articles=10)
    print(json.dumps(articles, indent=2))


if __name__ == "__main__":
    main()
