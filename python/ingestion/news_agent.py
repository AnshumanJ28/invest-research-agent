"""
News ingestion agent for fetching and deduplicating news articles via NewsAPI.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from .schemas import CitationMetadata, DocumentType, NewsArticle

LOGGER = logging.getLogger(__name__)

NEWS_CACHE: dict[str, list[NewsArticle]] = {}


def _call_provider(ticker: str, company_name: str | None = None, days_back: int = 30) -> dict:
    api_key = os.environ.get("NEWSAPI_KEY", "").strip()
    if not api_key:
        raise RuntimeError("NEWSAPI_KEY environment variable is not set.")

    query = f'"{ticker}"'
    if company_name:
        query += f' OR "{company_name}"'

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 50,
        "apiKey": api_key,
    }

    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_news(ticker: str, company_name: str | None = None, days_back: int = 30) -> list[NewsArticle]:
    cache_key = f"{ticker.upper()}_{days_back}"
    if cache_key in NEWS_CACHE:
        return NEWS_CACHE[cache_key]

    try:
        raw_data = _call_provider(ticker, company_name=company_name, days_back=days_back)
    except Exception as exc:
        LOGGER.warning("News provider failed for %s: %s", ticker, exc)
        return []

    articles: list[NewsArticle] = []
    seen_dedupes: set[str] = set()

    for item in raw_data.get("articles", []):
        url = item.get("url")
        if not url:
            continue

        title = item.get("title", "") or ""
        desc = item.get("description", "") or ""
        full_text = f"{title} {desc}".lower()

        # Relevance check
        ticker_base = ticker.split(".")[0] # INFY.NS -> INFY
        ticker_lower = ticker_base.lower()
        company_lower = company_name.lower() if company_name else ""
        
        aliases = []
        if ticker_lower == "reliance":
            aliases = ["industries", "jio", "ril", "ambani"]
            
        negative_idioms = ["reliance on", "heavy reliance", "our reliance", "placed reliance"]
        has_idiom = any(idiom in full_text for idiom in negative_idioms)
        
        is_relevant = False
        
        if has_idiom and not any(alias in full_text for alias in aliases):
            is_relevant = False
        else:
            title_lower = title.lower()
            if ticker_lower in title_lower or (company_lower and company_lower in title_lower):
                is_relevant = True
            else:
                financial_markers = ["shares", "stock", "quarter", "profit", "revenue", "ceo", "dividend"]
                if ticker_lower in full_text or (company_lower and company_lower in full_text):
                    if any(marker in full_text for marker in financial_markers):
                        is_relevant = True
                        
        if not is_relevant:
            continue

        domain = urlparse(url).netloc.lower()
        dedupe_key = hashlib.md5(f"{title.strip().lower()}_{domain}".encode("utf-8")).hexdigest()
        if dedupe_key in seen_dedupes:
            continue
        seen_dedupes.add(dedupe_key)

        pub_date_raw = item.get("publishedAt")
        if pub_date_raw:
            try:
                pub_date = datetime.fromisoformat(pub_date_raw.replace("Z", "+00:00"))
            except ValueError:
                pub_date = datetime.now(timezone.utc)
        else:
            pub_date = datetime.now(timezone.utc)

        source_name = item.get("source", {}).get("name") or domain
        meta = CitationMetadata(
            ticker=ticker.upper(),
            document_type=DocumentType.NEWS_ARTICLE,
            source_name=source_name,
            source_url=url,
            retrieval_timestamp=datetime.now(timezone.utc),
        )

        article = NewsArticle(
            metadata=meta,
            title=title,
            source_publication=item.get("source", {}).get("name") or domain,
            published_at=pub_date,
            url=url,
            snippet=desc,
            dedupe_key=dedupe_key,
        )
        articles.append(article)

    NEWS_CACHE[cache_key] = articles
    return articles
