# Analysis & NLP Layer

Consumes normalized data from the Data Ingestion layer (financial statements,
filing sections, transcripts, news) and produces ratios, sentiment, and peer
comparisons for Role 3 (RAG/Memo generation) — with the source citation chain
preserved end to end.

## Module map

| File | Purpose |
|---|---|
| `analysis/schemas.py` | Shared output contract (`RatioResult`, `SentimentResult`, `AggregateSentiment`, `CompetitorComparison`, `AnalysisReport`) |
| `analysis/ratios.py` | Financial Ratio Agent — liquidity, profitability, leverage, valuation |
| `analysis/sentiment.py` | Sentiment Analysis Agent — FinBERT via Hugging Face Inference API |
| `analysis/competitors.py` | Competitor Comparison Agent — peer selection + side-by-side ratios/sentiment |
| `analysis/interpretation.py` | Threshold-based healthy/watch/concerning narrative framing |
| `analysis/utils.py` | Safe division, missing-data handling, ingestion-schema adapter |

## Input shape expected from Role 1 (Data Ingestion)

This layer does **not** hard-import `ingestion.schemas` — it accepts anything
duck-typed the same way (real ingestion objects, dicts, or `SimpleNamespace`
in tests), via `analysis/utils.py::to_source_ref` and `line_item_value`. In
practice you'll pass ingestion's real objects straight through:

```python
from ingestion.yfinance_agent import fetch_financial_statements
from ingestion.transcript_agent import fetch_transcript
from ingestion.news_agent import fetch_news

from analysis.ratios import compute_ratios
from analysis.interpretation import interpret
from analysis.sentiment import score_news_batch, score_transcript, aggregate_sentiment
from analysis.competitors import compare_peers

statements = fetch_financial_statements("AAPL")
ratios = interpret(compute_ratios(statements, is_financial_company=False))

news = fetch_news("AAPL", company_name="Apple Inc.")
transcript = fetch_transcript("AAPL")
sentiment_results = score_news_batch(news) + score_transcript(transcript)
sentiment = aggregate_sentiment("AAPL", sentiment_results)

comparison = compare_peers(
    "AAPL", ratios, peer_tickers=["MSFT", "GOOGL"],
    fetch_statements=fetch_financial_statements,
)
```

**ASSUMPTION FLAGGED:** `analysis/schemas.py::SourceRef` is a deliberately
looser placeholder for `ingestion.schemas.CitationMetadata`. Both are present
side by side in this project, so `to_source_ref()` is a thin adapter, not a
guess — but if Role 1's schema shape changes, `analysis/utils.py::to_source_ref`
is the one place that needs to change; ratios/sentiment/competitors never
touch ingestion metadata directly.

## Output shape for Role 3 (RAG/Memo)

- `RatioResult`: `name`, `category`, `formula`, `value`, `computable`,
  `health_flag` (`healthy` / `watch` / `concerning` / `not_applicable`),
  `narrative` (memo-ready sentence), `source_line_items: list[SourceRef]`.
- `AggregateSentiment`: `overall_label`, `overall_score` (-1..+1),
  `trend` (`improving`/`declining`/`stable`), `component_scores` per segment,
  `sample_size` per segment, and a standing `limitations_note`.
- `CompetitorComparison`: `comparison_table` is `{ratio_name: {ticker: value}}`,
  always including the primary ticker as one of the columns; `peers` includes
  a `data_available` flag and `unavailable_reason` per peer.

Every `RatioResult.source_line_items` and `SentimentResult.source` traces back
to a `SourceRef(ticker, document_type, source_url, section_id, as_of_date)` —
enough for Role 3 to build a citation without re-querying ingestion.

## Known limitations (stated explicitly)

1. **Ratio formulas that break for certain company types.** For
   `is_financial_company=True`, `current_ratio`, `quick_ratio`, and
   `debt_to_equity` are returned as `computable=False` /
   `health_flag=not_applicable` with an explanatory `note` — banks'
   balance sheets don't fit the standard current/non-current or
   debt/equity framing. A regulatory capital ratio (e.g. Tier 1) would be
   the right substitute; that's not implemented here.
2. **FinBERT weak spots** (stated in every `AggregateSentiment.limitations_note`,
   not just this README): sarcasm, heavily hedged forward-looking language,
   and dense financial jargon it wasn't fine-tuned on can produce
   low-confidence or misleading scores. Treat near-neutral scores with extra
   caution rather than as a confident "no signal" reading.
3. **Peer-data dependency (Loop 3) is real, not assumed away.**
   `compare_peers` calls back into whatever `fetch_statements` callable it's
   given — if ingestion hasn't been run yet for a peer ticker (or that call
   fails/returns nothing), `PeerSnapshot(data_available=False, ...)` is
   returned for that peer and the comparison table gets `None` in that
   column, rather than raising or silently omitting the peer.
4. **Peer *candidate discovery* is intentionally out of scope here.**
   `select_peers()` filters a `candidate_pool` you already have (e.g. a
   maintained industry/ticker list) — it does not itself scrape or guess
   "who are Apple's competitors." Building or sourcing that candidate pool
   is an explicit upstream dependency for whoever wires this agent up.
5. **Sentiment hosting tradeoff.** Hugging Face Inference API (hosted) is
   used instead of loading FinBERT into the backend process, trading a
   small amount of added latency and an HF-uptime dependency for a much
   lighter, GPU-free backend footprint appropriate to a free-tier deployment.
6. **Trend detection in `aggregate_sentiment`** is a simple first-half vs.
   second-half comparison over dated excerpts (needs ≥4 dated results to
   report anything other than "stable") — a lightweight heuristic, not a
   proper time-series model.

## Testing

`tests/test_ratios.py`, `tests/test_sentiment.py`, `tests/test_competitors.py`
all run against synthetic/mocked data (no live network, no HF token, no
ingestion dependency) via `unittest.mock.patch` and `SimpleNamespace` stand-ins
for ingestion objects — run with `pytest tests/ -q`.
