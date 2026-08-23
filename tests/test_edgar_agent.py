"""Tests for the Indian filings agent (BSE/NSE). Mocks network calls and PDF parsing."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion import edgar_agent as agent  # noqa: E402
from ingestion.schemas import CitationMetadata, FilingDocument, FilingSection

SAMPLE_PDF_TEXT = """
Board's Report
We design, manufacture and market widgets globally. Our widgets are sold in over 100 countries.

Management Discussion and Analysis
Our business is subject to intense competition which could materially harm results of operations.
We rely on a small number of suppliers for critical components used in our widgets.

Report on Corporate Governance
Revenue increased year over year driven primarily by strong demand across all reportable segments.
"""

def _mock_response(content):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp

@patch("ingestion.edgar_agent.resolve_bse_scrip_code")
@patch("ingestion.edgar_agent._latest_filings")
@patch("ingestion.edgar_agent._get")
@patch("ingestion.edgar_agent._extract_pdf_text")
def test_resolve_cik_and_sections_carry_own_metadata(
    mock_extract_text, mock_get, mock_latest, mock_resolve
):
    mock_resolve.return_value = "500325"
    mock_latest.return_value = [{
        "attachment_name": "reliance_ar_2025.pdf",
        "filed_date": "2025-07-20",
        "headline": "Annual Report"
    }]
    mock_get.return_value = _mock_response(b"dummy pdf bytes")
    mock_extract_text.return_value = SAMPLE_PDF_TEXT

    doc = agent.fetch_filing("RELIANCE", "annual_report")

    assert doc is not None
    assert doc.ticker == "RELIANCE"
    assert doc.cik == "500325"
    assert doc.filing_type == "annual_report"
    assert len(doc.sections) >= 3

    # Every section must carry its OWN citation metadata (not one shared blob)
    section_ids = {s.metadata.section_id for s in doc.sections}
    assert len(section_ids) == len(doc.sections), "section_ids must be unique -- required for paragraph-level citation"
    
    for s in doc.sections:
        assert s.metadata.ticker == "RELIANCE"
        assert s.metadata.source_url is not None
        assert s.paragraph_index >= 0

    mda_sections = [s for s in doc.sections if s.section_name == "Management Discussion and Analysis"]
    assert len(mda_sections) >= 1
    assert "competition" in mda_sections[0].text.lower()

@patch("ingestion.edgar_agent.resolve_bse_scrip_code")
def test_unresolvable_ticker_returns_none_not_exception(mock_resolve):
    mock_resolve.return_value = None
    doc = agent.fetch_filing("NOPE_NOT_A_REAL_TICKER", "annual_report")
    assert doc is None
