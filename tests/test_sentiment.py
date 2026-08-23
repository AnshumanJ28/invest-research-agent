import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis import sentiment as agent  # noqa: E402
from analysis.schemas import SentimentLabel, SentimentSegment  # noqa: E402


def _meta(as_of=None):
    return SimpleNamespace(ticker="TEST", document_type=SimpleNamespace(value="news_article"),
                            source_url="https://example.com", section_id=None, as_of_date=as_of)


def test_score_text_carries_source_and_excerpt():
    with patch.object(agent, "_call_finbert", return_value=[
        {"label": "positive", "score": 0.91}, {"label": "neutral", "score": 0.05}, {"label": "negative", "score": 0.04}
    ]):
        result = agent.score_text("Great quarter, revenue up sharply.", SentimentSegment.NEWS, _meta())

    assert result is not None
    assert result.label == SentimentLabel.POSITIVE
    assert result.confidence == 0.91
    assert result.source.ticker == "TEST"
    assert "Great quarter" in result.excerpt


def test_score_text_returns_none_on_provider_failure_not_exception():
    with patch.object(agent, "_call_finbert", side_effect=RuntimeError("HF_API_TOKEN not set")):
        with patch.object(agent, "TextBlob", None):
            result = agent.score_text("Some text", SentimentSegment.NEWS, _meta())
    assert result is None


def test_transcript_unavailable_skips_scoring_entirely():
    transcript = SimpleNamespace(available=False, utterances=[])
    with patch.object(agent, "_call_finbert") as mock_call:
        results = agent.score_transcript(transcript)
    assert results == []
    mock_call.assert_not_called()


def test_prepared_remarks_and_qa_scored_as_distinct_segments():
    utterances = [
        SimpleNamespace(section=SimpleNamespace(value="prepared_remarks"), text="Revenue grew nicely this quarter.",
                        metadata=_meta()),
        SimpleNamespace(section=SimpleNamespace(value="qa"), text="We are cautious about next quarter headwinds.",
                        metadata=_meta()),
    ]
    transcript = SimpleNamespace(available=True, utterances=utterances)

    with patch.object(agent, "_call_finbert", return_value=[{"label": "positive", "score": 0.8}]):
        results = agent.score_transcript(transcript)

    segments = {r.segment for r in results}
    assert SentimentSegment.TRANSCRIPT_PREPARED_REMARKS in segments
    assert SentimentSegment.TRANSCRIPT_QA in segments


def test_aggregate_sentiment_weights_recent_more_and_reports_sample_size():
    now = datetime.now(timezone.utc)
    recent_positive = agent.SentimentResult(
        segment=SentimentSegment.NEWS, label=SentimentLabel.POSITIVE, confidence=0.9,
        excerpt="recent good news", source=agent.to_source_ref(_meta(as_of=now)),
    )
    old_negative = agent.SentimentResult(
        segment=SentimentSegment.NEWS, label=SentimentLabel.NEGATIVE, confidence=0.9,
        excerpt="old bad news", source=agent.to_source_ref(_meta(as_of=now - timedelta(days=120))),
    )
    agg = agent.aggregate_sentiment("TEST", [recent_positive, old_negative])
    assert agg.overall_score > 0  # recent positive should outweigh stale negative
    assert agg.sample_size["news"] == 2
    assert "FinBERT" in agg.limitations_note


def test_empty_results_returns_neutral_default():
    agg = agent.aggregate_sentiment("TEST", [])
    assert agg.overall_label == SentimentLabel.NEUTRAL
    assert agg.overall_score == 0.0


def test_score_text_falls_back_to_textblob_on_provider_failure():
    with patch.object(agent, "_call_finbert", side_effect=RuntimeError("HF connection failed")):
        result = agent.score_text("This is an absolutely wonderful day!", SentimentSegment.NEWS, _meta())
    assert result is not None
    assert result.label == SentimentLabel.POSITIVE
    assert result.confidence > 0.5
