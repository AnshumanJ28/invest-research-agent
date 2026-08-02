import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion import transcript_agent as agent  # noqa: E402
from ingestion.schemas import TranscriptSection  # noqa: E402

SAMPLE_TRANSCRIPT = """Operator: Good afternoon and welcome to the call.
Jane CEO: Thanks everyone for joining. Revenue grew 12% year over year.
Jane CEO: We are pleased with our progress across all segments.

Question-and-Answer Session

John Analyst: Can you comment on gross margin trends?
Jane CEO: Sure, margins improved due to supply chain efficiencies.
"""


def test_missing_transcript_returns_explicit_unavailable():
    with patch.object(agent, "_call_provider", return_value=None):
        doc = agent.fetch_transcript("TINYCAP")
    assert doc.available is False
    assert doc.unavailable_reason is not None
    assert doc.utterances == []


def test_provider_exception_degrades_to_unavailable_not_crash():
    with patch.object(agent, "_call_provider", side_effect=ConnectionError("timeout")):
        doc = agent.fetch_transcript("AAPL")
    assert doc.available is False
    assert "provider error" in doc.unavailable_reason


def test_available_transcript_splits_prepared_remarks_from_qa():
    # Different ticker than the other tests -- TRANSCRIPT_CACHE is keyed per
    # ticker, and a prior test already cached an "unavailable" result for AAPL.
    with patch.object(agent, "_call_provider", return_value={"transcript": SAMPLE_TRANSCRIPT, "date": "1731000000"}):
        doc = agent.fetch_transcript("MSFT")

    assert doc.available is True
    sections = {u.section for u in doc.utterances}
    assert TranscriptSection.PREPARED_REMARKS in sections
    assert TranscriptSection.QA in sections

    qa_utterances = [u for u in doc.utterances if u.section == TranscriptSection.QA]
    assert any("John Analyst" in u.speaker for u in qa_utterances)

    # Each utterance must carry its own citation metadata for later scoring/citation
    for u in doc.utterances:
        assert u.metadata.section_id is not None
        assert u.metadata.ticker == "MSFT"
