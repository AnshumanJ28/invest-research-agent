import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion import news_agent as agent  # noqa: E402

RAW_RESPONSE = {
    "articles": [
        {
            "title": "Acme Corp beats Q3 earnings estimates",
            "description": "Acme Corp (ACME) reported strong quarterly results.",
            "url": "https://news.example.com/acme-q3",
            "publishedAt": "2026-07-15T10:00:00Z",
            "source": {"name": "Example News"},
        },
        {
            # Duplicate of above (same title/domain) -- should be deduped
            "title": "Acme Corp beats Q3 earnings estimates",
            "description": "Acme Corp (ACME) reported strong quarterly results.",
            "url": "https://news.example.com/acme-q3",
            "publishedAt": "2026-07-15T10:00:00Z",
            "source": {"name": "Example News"},
        },
        {
            # Irrelevant -- doesn't mention ticker or company name
            "title": "Local weather update for the weekend",
            "description": "Rain expected on Saturday.",
            "url": "https://news.example.com/weather",
            "publishedAt": "2026-07-15T09:00:00Z",
            "source": {"name": "Example News"},
        },
        {
            # No URL -- must be dropped, useless for citation
            "title": "ACME announces new product line",
            "description": "ACME unveiled new products today.",
            "url": None,
            "publishedAt": "2026-07-14T09:00:00Z",
            "source": {"name": "Example News"},
        },
    ]
}


def test_dedupe_relevance_and_url_requirement():
    with patch.object(agent, "_call_provider", return_value=RAW_RESPONSE):
        articles = agent.fetch_news("ACME", company_name="Acme Corp")

    assert len(articles) == 1  # dupe removed, irrelevant removed, no-URL removed
    assert articles[0].url == "https://news.example.com/acme-q3"
    assert articles[0].metadata.ticker == "ACME"
    assert articles[0].metadata.source_url == articles[0].url


def test_provider_failure_returns_empty_list_not_exception():
    # Distinct ticker -- NEWS_CACHE is keyed per ticker+window, and the prior
    # test already cached a real result for "ACME".
    with patch.object(agent, "_call_provider", side_effect=RuntimeError("no api key")):
        articles = agent.fetch_news("NOPROVIDER")
    assert articles == []
