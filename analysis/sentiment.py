"""
Sentiment Analysis Agent.

Scores sentiment on news articles and transcript utterances using FinBERT
(ProsusAI/finbert), separately for news, transcript prepared-remarks, and
transcript Q&A -- these carry different tones and blending them would wash
out the (often more revealing) shift in tone between the two.

Hosting choice: Hugging Face Inference API (hosted), not loading FinBERT
into the backend process.
  - Free tier, no GPU requirement -- FinBERT (~440MB, BERT-base) is
    workable on CPU but adds real cold-start latency on a free-tier
    backend host (e.g. Render/Railway free dynos) where cold starts are
    already a problem.
  - Keeps the backend's own memory footprint small, which matters if the
    same free-tier instance also hosts the ingestion/analysis/orchestration
    API.
  - Tradeoff, stated plainly: adds network latency per call and a hard
    dependency on HF's uptime/free-tier rate limits. For a hobby/demo
    deployment this is the right tradeoff; a production system with
    real request volume would likely self-host FinBERT behind a small
    dedicated inference service instead.

Known FinBERT weak spots (surfaced in AggregateSentiment.limitations_note,
not silently omitted): sarcasm, heavily hedged forward-looking statements
("we remain cautiously optimistic, though visibility is limited"), and
dense financial jargon it wasn't fine-tuned on can all produce
low-confidence or misleading neutral/positive scores.
"""

from __future__ import annotations

import os

# Disable NLTK early import security hook since the virtual environment 'venv'
# is located inside the CWD, causing NLTK to mistakenly block standard imports.
os.environ["NLTK_DISABLE_IMPORT_SECURITY"] = "1"

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


from datetime import datetime, timezone
from typing import Any

from .schemas import AggregateSentiment, SentimentLabel, SentimentResult, SentimentSegment
from .utils import to_source_ref

try:
    import requests
except ImportError:
    requests = None

try:
    from textblob import TextBlob
except ImportError:
    TextBlob = None

HF_API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"
HF_API_KEY_ENV_VAR = "HF_API_TOKEN"

_LABEL_MAP = {
    "positive": SentimentLabel.POSITIVE,
    "negative": SentimentLabel.NEGATIVE,
    "neutral": SentimentLabel.NEUTRAL,
}
_SCORE_SIGN = {SentimentLabel.POSITIVE: 1.0, SentimentLabel.NEGATIVE: -1.0, SentimentLabel.NEUTRAL: 0.0}


def _call_finbert(text: str) -> list[dict[str, Any]]:
    """Returns HF's raw classification output: [{"label": "positive", "score": 0.87}, ...].
    Raises on transport/auth errors -- callers decide how to degrade."""
    if requests is None:
        raise RuntimeError("requests is not installed in this environment")
    api_key = os.environ.get(HF_API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(f"{HF_API_KEY_ENV_VAR} not set in environment")
    resp = requests.post(
        HF_API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"inputs": text[:512]},  # FinBERT's practical context window
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    # HF sometimes nests one level: [[{...}, {...}, {...}]]
    if data and isinstance(data[0], list):
        data = data[0]
    return data


def score_text(text: str, segment: SentimentSegment, source_metadata: Any) -> SentimentResult | None:
    """Scores a single excerpt. Returns None (not an exception) if the
    inference call fails -- callers should skip that excerpt rather than
    fail the whole batch over one bad request."""
    try:
        raw = _call_finbert(text)
        if not raw:
            raise ValueError("Empty response from Hugging Face")
        best = max(raw, key=lambda x: x.get("score", 0.0))
        label = _LABEL_MAP.get(best.get("label", "").lower(), SentimentLabel.NEUTRAL)
        confidence = float(best.get("score", 0.0))
    except Exception:  # noqa: BLE001
        # Fallback to TextBlob if Hugging Face fails
        if TextBlob is not None:
            analysis = TextBlob(text)
            polarity = analysis.sentiment.polarity
            if polarity > 0.1:
                label = SentimentLabel.POSITIVE
            elif polarity < -0.1:
                label = SentimentLabel.NEGATIVE
            else:
                label = SentimentLabel.NEUTRAL
            confidence = round(min(abs(polarity) + 0.5, 1.0), 4)
        else:
            return None

    return SentimentResult(
        segment=segment,
        label=label,
        confidence=confidence,
        excerpt=text[:280],
        source=to_source_ref(source_metadata),
    )


def score_news_batch(articles: list[Any]) -> list[SentimentResult]:
    results = []
    for article in articles:
        text = f"{article.title}. {article.snippet}" if hasattr(article, "title") else article["title"]
        metadata = article.metadata if hasattr(article, "metadata") else article["metadata"]
        r = score_text(text, SentimentSegment.NEWS, metadata)
        if r is not None:
            results.append(r)
    return results


def score_transcript(transcript: Any) -> list[SentimentResult]:
    """`transcript` is ingestion.schemas.TranscriptDocument (or equivalent).
    Returns [] immediately if `.available` is False -- no inference calls
    wasted on a transcript that doesn't exist."""
    available = transcript.available if hasattr(transcript, "available") else transcript.get("available")
    if not available:
        return []
    utterances = transcript.utterances if hasattr(transcript, "utterances") else transcript.get("utterances", [])
    results = []
    for u in utterances:
        section = u.section if hasattr(u, "section") else u.get("section")
        section_val = section.value if hasattr(section, "value") else section
        segment = (SentimentSegment.TRANSCRIPT_QA if section_val == "qa"
                   else SentimentSegment.TRANSCRIPT_PREPARED_REMARKS)
        text = u.text if hasattr(u, "text") else u.get("text")
        metadata = u.metadata if hasattr(u, "metadata") else u.get("metadata")
        r = score_text(text, segment, metadata)
        if r is not None:
            results.append(r)
    return results


def aggregate_sentiment(ticker: str, results: list[SentimentResult]) -> AggregateSentiment:
    """Recency-weighted aggregate across all scored excerpts. More recent
    `as_of_date` values get more weight; excerpts with no date get the
    lowest (but non-zero) weight rather than being dropped."""
    if not results:
        return AggregateSentiment(
            ticker=ticker,
            overall_label=SentimentLabel.NEUTRAL,
            overall_score=0.0,
            trend="stable",
            component_scores={},
            sample_size={},
        )

    now = datetime.now(timezone.utc)

    def weight(r: SentimentResult) -> float:
        as_of = r.source.as_of_date
        if as_of is None:
            return 0.25
        age_days = max((now - (as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc))).days, 0)
        return max(1.0 / (1 + age_days / 14.0), 0.05)  # ~2-week half-life-ish decay

    weighted_sum = sum(_SCORE_SIGN[r.label] * r.confidence * weight(r) for r in results)
    total_weight = sum(weight(r) for r in results) or 1.0
    overall_score = weighted_sum / total_weight

    component_scores: dict[str, float] = {}
    sample_size: dict[str, int] = {}
    for segment in SentimentSegment:
        seg_results = [r for r in results if r.segment == segment]
        sample_size[segment.value] = len(seg_results)
        if seg_results:
            seg_weight = sum(weight(r) for r in seg_results) or 1.0
            component_scores[segment.value] = sum(
                _SCORE_SIGN[r.label] * r.confidence * weight(r) for r in seg_results
            ) / seg_weight

    # crude trend: compare first half vs second half chronologically, if dated
    def _to_utc(dt):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    dated = sorted((r for r in results if r.source.as_of_date), key=lambda r: _to_utc(r.source.as_of_date))
    trend = "stable"
    if len(dated) >= 4:
        mid = len(dated) // 2
        first_half_avg = sum(_SCORE_SIGN[r.label] * r.confidence for r in dated[:mid]) / mid
        second_half_avg = sum(_SCORE_SIGN[r.label] * r.confidence for r in dated[mid:]) / (len(dated) - mid)
        if second_half_avg - first_half_avg > 0.15:
            trend = "improving"
        elif first_half_avg - second_half_avg > 0.15:
            trend = "declining"

    overall_label = (
        SentimentLabel.POSITIVE if overall_score > 0.15
        else SentimentLabel.NEGATIVE if overall_score < -0.15
        else SentimentLabel.NEUTRAL
    )

    return AggregateSentiment(
        ticker=ticker,
        overall_label=overall_label,
        overall_score=round(overall_score, 4),
        trend=trend,
        component_scores={k: round(v, 4) for k, v in component_scores.items()},
        sample_size=sample_size,
    )


if __name__ == "__main__":
    # Manual smoke test against the real HF Inference API (requires HF_API_TOKEN env var)
    from types import SimpleNamespace
    sample_meta = SimpleNamespace(ticker="AAPL", document_type=SimpleNamespace(value="news_article"),
                                   source_url="https://example.com", section_id=None, as_of_date=None)
    r = score_text("Apple reported record quarterly revenue, beating analyst expectations.",
                    SentimentSegment.NEWS, sample_meta)
    print(r)
