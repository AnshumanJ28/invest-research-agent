"""
News Aggregation Agent.

Pulls recent (30-90 day) English-language articles for a ticker, dedupes,
filters for relevance, and normalizes into schemas.NewsArticle.

Data source: NewsAPI.org's `everything` endpoint (free developer tier,
English-language filter built in via `language=en`). Free tier caps at 100
req/day and only returns articles from the last month, which is why the
default window below is 30 days -- the constraint file's 30-90 day range is
best served with a paid tier or a secondary source; that gap is flagged in
the README as a known limitation, not silently papered over.

--- Note on India support ---
Per project notes, this agent needed the least work of the four ingestion
agents: NewsAPI already indexes Indian publications (Economic Times,
Livemint, Moneycontrol, Business Standard, etc.), and the dedup/relevance
logic is country-agnostic. The one real gap was ticker format: other
agents in this pipeline now pass suffixed tickers for Indian equities
(e.g. "RELIANCE.NS", per yfinance_agent's `_normalize_ticker`), but
".NS"/".BO" never appears in article text -- searching or relevance-
matching on the raw suffixed ticker would silently return zero results for
every Indian company. `_search_key()` below strips the suffix for the
NewsAPI query string and the relevance check, while `metadata.ticker` on
the returned NewsArticle objects keeps the original (possibly suffixed)
ticker, so downstream code that joins across agents by ticker still lines
up with yfinance_agent/edgar_agent/transcript_agent output.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from .schemas import CitationMetadata, DocumentType, NewsArticle
from .utils import NEWS_API_RATE_LIMITER, NEWS_CACHE, retry

try:
    import requests
except ImportError:
    requests = None

NEWSAPI_URL = "https://newsapi.org/v2/everything"
API_KEY_ENV_VAR = "NEWSAPI_KEY"

# Exchange suffixes yfinance_agent may have appended for Indian tickers.
# Stripped before the value is used as search text (see module docstring).
_INDIAN_SUFFIX_RE = re.compile(r"\.(NS|BO)$", re.I)


def _search_key(ticker: str) -> str:
    """The part of a (possibly suffixed) ticker that's actually meaningful
    as search/relevance text -- e.g. "RELIANCE.NS" -> "RELIANCE"."""
    return _INDIAN_SUFFIX_RE.sub("", ticker.upper().strip())


def _dedupe_key(title: str, url: str) -> str:
    domain = urlparse(url).netloc.lower()
    norm_title = re.sub(r"[^a-z0-9]", "", title.lower())
    return hashlib.sha256(f"{domain}:{norm_title}".encode()).hexdigest()[:16]


def _is_relevant(article: dict, search_key: str, company_name: str | None) -> bool:
    """Cheap relevance filter: ticker (suffix stripped) or company name
    must appear in title or description. Real deployments would swap this
    for an entity-linking model; this keeps the agent dependency-light and
    deterministic."""
    haystack = f"{article.get('title', '')} {article.get('description', '')}".lower()
    if search_key.lower() in haystack:
        return True
    if company_name and company_name.lower() in haystack:
        return True
    return False


@retry(max_attempts=3, base_delay=2.0, exceptions=(requests.RequestException,) if requests is not None else (Exception,))
def _call_provider(query: str, from_date: str) -> dict:
    if requests is None:
        raise RuntimeError("requests is not installed in this environment")
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"{API_KEY_ENV_VAR} not set in environment")
    NEWS_API_RATE_LIMITER.acquire()
    resp = requests.get(
        NEWSAPI_URL,
        params={
            "q": query,
            "language": "en",
            "from": from_date,
            "sortBy": "publishedAt",
            "pageSize": 50,
            "apiKey": api_key,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _clean_company_name(name: str) -> str:
    # Remove common corporate suffixes in uppercase
    cleaned = name.upper()
    suffixes = [
        " INDUSTRIES LTD", " INDUSTRIES LIMITED", " SERVICES LTD", " SERVICES LIMITED",
        " ENTERPRISES LTD", " ENTERPRISES LIMITED", " PASSENGER VEHICLES LTD",
        " CO LTD", " CO LIMITED", " LTD", " LIMITED", " CORP", " CORPORATION",
        " TRUST"
    ]
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned.strip()


def fetch_news(
    ticker: str,
    company_name: str | None = None,
    days_back: int = 30,
) -> list[NewsArticle]:
    """Fetch, dedupe, and relevance-filter recent news for `ticker`.
    `ticker` may be a plain US symbol or a suffixed Indian one
    ("RELIANCE.NS") -- the suffix is stripped internally for search and
    relevance matching but preserved as-is on returned NewsArticle
    metadata. Returns an empty list (never raises) if the provider is
    unreachable or misconfigured -- an empty news set shouldn't fail the
    rest of ingestion."""
    ticker = ticker.upper().strip()
    search_key = _search_key(ticker)
    cache_key = f"news::{ticker}::{days_back}"
    cached = NEWS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    # Strip exchange suffixes like .NS/.BO before building the search query --
    # real news text won't contain "RELIANCE.NS", just "Reliance".
    clean_ticker = ticker.split(".")[0]

    # Resolve company name from BSE if not provided
    resolved_company = None
    if not company_name:
        try:
            from .edgar_agent import resolve_bse_company_info
            _, resolved_name = resolve_bse_company_info(ticker)
            if resolved_name:
                resolved_company = _clean_company_name(resolved_name)
        except Exception:  # noqa: BLE001
            pass

    search_name = company_name or resolved_company

    if search_name:
        query = f'"{clean_ticker}" OR "{search_name}"'
    else:
        query = f'"{clean_ticker}"'

    from_date = (datetime.now(timezone.utc) - timedelta(days=min(days_back, 30))).strftime("%Y-%m-%d")

    try:
        raw = _call_provider(query, from_date)
    except Exception:  # noqa: BLE001 -- provider outage degrades to empty, not crash
        NEWS_CACHE.set(cache_key, [])
        return []

    seen_keys: set[str] = set()
    articles: list[NewsArticle] = []
    for item in raw.get("articles", []):
        url = item.get("url")
        title = item.get("title")
        if not url or not title:
            continue  # no resolvable source URL -> useless for citation, drop it

        relevant = _is_relevant(item, clean_ticker, company_name)
        if not relevant and search_name:
            relevant = _is_relevant(item, search_name, None)
        if not relevant:
            continue

        key = _dedupe_key(title, url)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        published_raw = item.get("publishedAt")
        try:
            published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00")) if published_raw else datetime.now(timezone.utc)
        except ValueError:
            published_at = datetime.now(timezone.utc)

        articles.append(NewsArticle(
            metadata=CitationMetadata(
                ticker=ticker,
                document_type=DocumentType.NEWS_ARTICLE,
                source_name=item.get("source", {}).get("name", "unknown"),
                source_url=url,
                as_of_date=published_at,
            ),
            title=title,
            source_publication=item.get("source", {}).get("name", "unknown"),
            published_at=published_at,
            url=url,
            snippet=item.get("description") or item.get("content") or "",
            dedupe_key=key,
        ))

    NEWS_CACHE.set(cache_key, articles)
    return articles


if __name__ == "__main__":
    import sys
    tk_symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    results = fetch_news(tk_symbol, company_name="Apple")
    print(f"{len(results)} relevant articles for {tk_symbol}")
    for a in results[:5]:
        print(f"  [{a.published_at.date()}] {a.title} -- {a.url}")