# Data Ingestion Layer

Produces citation-grounded, normalized data for US-listed equities (NYSE/NASDAQ),
delayed-only, English-only. Every unit of data (a line item, a filing paragraph,
a transcript utterance, a news article) carries its own `CitationMetadata` --
never a single shared metadata block for a whole document.

## Module map

| File | Purpose |
|---|---|
| `ingestion/schemas.py` | Shared Pydantic contract (`CitationMetadata`, `FinancialStatement`, `FilingDocument`, `TranscriptDocument`, `NewsArticle`) |
| `ingestion/yfinance_agent.py` | Financial statements, key stats, price history |
| `ingestion/edgar_agent.py` | Most recent 10-K / 10-Q, sectioned by Item, paragraph-level citations |
| `ingestion/transcript_agent.py` | Most recent earnings call, split by speaker & prepared-remarks/Q&A |
| `ingestion/news_agent.py` | Recent news, deduped, relevance-filtered |
| `ingestion/storage.py` | PostgreSQL writes preserving all citation metadata |
| `ingestion/utils.py` | Retry, rate limiting, TTL caching |
| `workflows/watchlist_monitor.json` | n8n scheduled re-ingestion workflow |

## How Role 2 / Role 3 should call this

```python
from ingestion.yfinance_agent import fetch_financial_statements
from ingestion.edgar_agent import fetch_latest_filings
from ingestion.transcript_agent import fetch_transcript
from ingestion.news_agent import fetch_news

statements = fetch_financial_statements("AAPL")          # list[FinancialStatement], always non-empty
filings    = fetch_latest_filings("AAPL")                 # {"10-K": FilingDocument|None, "10-Q": FilingDocument|None}
transcript = fetch_transcript("AAPL")                      # TranscriptDocument, check .available first
news       = fetch_news("AAPL", company_name="Apple Inc.")  # list[NewsArticle], possibly empty
```

**Always check before using:**
- `filings["10-K"]` / `filings["10-Q"]` can be `None` — ticker not resolvable to a CIK, or no filing of that type exists yet.
- `transcript.available` — `False` for small-caps, recent IPOs, or non-callers. Do not access `.utterances` without checking this first; it will be an empty list, not an error, but treating an unavailable transcript as "no sentiment signal" vs. "zero mentions" matters downstream.
- `FinancialStatement.missing_fields` — a non-empty list means those specific line items weren't available from yfinance for this ticker; the corresponding `FinancialLineItem.value` will be `None`, not `0`.

**Every returned object's `.metadata` (or per-item `.metadata`) always has:** `ticker`, `document_type`, `source_name`, `retrieved_at`, and `source_url` (except for a small number of yfinance-derived key stats which have no stable per-field URL — those still carry `source_name="yfinance"` and a quote-page `source_url`).

## Rate limits, caching, retry — per external API

| API | Limit | Our throttle | Cache TTL | Retry |
|---|---|---|---|---|
| yfinance (unofficial Yahoo endpoints) | Undocumented, but bursty calls get temporarily blocked | No explicit rate limiter (single calls per ticker); relies on 15-min cache to avoid re-hitting | 15 min (`PRICE_CACHE`) | 3 attempts, exponential backoff from 2s |
| SEC EDGAR (`data.sec.gov`, `www.sec.gov`) | 10 req/sec documented; **requires descriptive `User-Agent`** or requests are 403'd | Throttled to 5 req/sec (`SEC_EDGAR_RATE_LIMITER`) | 6 hours (`FILING_CACHE`) — filings don't change intraday | 3 attempts, exponential backoff from 2s |
| Transcript provider (API Ninjas) | Free tier: modest daily cap, no published rate/sec limit | 2 attempts only (network errors), since a 404 = legitimately no transcript, not a transient failure | 24 hours (`TRANSCRIPT_CACHE`) — transcripts are static once posted | 2 attempts, backoff from 1.5s, only on connection/timeout errors |
| News (NewsAPI.org) | Free dev tier: 100 req/day, ~1 month lookback | Throttled to 1 req/sec (`NEWS_API_RATE_LIMITER`) | 30 min (`NEWS_CACHE`) | 3 attempts, exponential backoff from 2s |

## Known limitations (stated explicitly, not silently dropped)

1. **News lookback window**: the constraint file asks for 30–90 day coverage. NewsAPI's free tier only returns the trailing ~30 days. `fetch_news(days_back=...)` is clamped to 30 regardless of the argument. A paid tier or a secondary source (e.g. GDELT) would be needed to reach 90 days.
2. **yfinance field coverage varies by ticker.** Small-caps and foreign private issuers frequently have `None` for several `KEY_STATS_FIELDS`. This is surfaced via `missing_fields`, not hidden.
3. **EDGAR section-splitting is heuristic**, based on `Item N.` header regexes against cleaned text. Filers with non-standard formatting can produce a single `"Full Document"` section instead of clean per-Item splits — check `len(doc.sections) > 1` if per-Item granularity is required for a claim.
4. **`resolve_cik` requires a network hit to `sec.gov/files/company_tickers.json`** on cold cache; if that's unreachable, `fetch_filing` returns `None` for every ticker until the cache (6h TTL, keyed under `"ticker_cik_map"`) is repopulated.
5. **The n8n workflow (`workflows/watchlist_monitor.json`) depends on a `POST /research` backend endpoint that does not exist yet** — it's the orchestration role's responsibility. The workflow is wired against `$env.INGESTION_BACKEND_URL` and will fail until that's deployed. This is noted directly in the workflow JSON's node `notes` field.
6. **`transcript_agent.py`'s `API_NINJAS_KEY` and `news_agent.py`'s `NEWSAPI_KEY`** must be set as environment variables in deployment; neither module will raise on a missing key — they degrade to "unavailable"/"empty," which is correct behavior for a broken pipeline stage but means a missing key can silently look like "no news today." Alert on `NEWSAPI_KEY`/`API_NINJAS_KEY` absence at deploy-time health checks, not just at runtime.

## Storage

See `ingestion/storage.py` docstring for the PostgreSQL-over-MongoDB justification. Call `Storage.init_schema()` once, then use `write_financial_statement`, `write_filing`, `write_transcript`, `write_news` per ticker per run. `Storage.reconstruct_citation(table, row_id)` is a debugging helper that proves any stored row still carries enough fields (source, section, date, URL) to rebuild a citation — used in place of an actual DB in the test suite since no live Postgres is available in this environment.
