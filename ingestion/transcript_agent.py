"""
Indian Earnings Call Transcript Agent -- replacement for transcript_agent.py's
role for NSE/BSE-listed companies.

Per project notes: Indian transcripts aren't aggregated for free the way
Motley Fool does for US companies via one clean, ToS-violating-but-workable
HTML scrape. The good news for India is there's actually a *better*-sourced
option than that: SEBI's LODR Regulation 30 requires listed companies to
disclose earnings call transcripts to the exchanges as a regulatory filing,
the same mechanism used for annual reports/results in `edgar_agent.py`.
That means the primary path here is NOT scraping a secondary aggregator --
it's pulling the company's own regulatory filing from BSE, same as
`edgar_agent.fetch_filing`. A secondary aggregator (Trendlyne, which
publicly lists "Conference Call / Earnings Call Transcripts" per company) is
kept as a fallback for cases where the BSE announcement search misses it,
with the SAME ToS caveat the original Motley Fool module carried.

*** VERIFICATION STATUS: UNVERIFIED / NOT TESTED AGAINST LIVE ENDPOINTS ***
Same caveat as `edgar_agent.py`, carried over because this module reuses
its BSE plumbing directly (see imports below) rather than duplicating it:
  - The BSE announcement category/headline-keyword filter used to identify
    "this announcement is a transcript, not something else" is a text
    heuristic (see `_looks_like_transcript`), not a confirmed category
    code -- BSE's public search results for Reg 30 transcript filings
    commonly use headlines like "Transcript of Earnings Conference Call"
    or "Earnings Call Transcript", per manual review of BSE/Trendlyne
    listings, but the exact, stable category code was not confirmed
    against a live API response.
  - The Trendlyne fallback (`_find_transcript_via_trendlyne`) assumes a
    listing/search page structure inferred the same way the original
    Fool-based module inferred fool.com's -- untested, and Trendlyne's own
    Terms of Use should be checked before scraping it in anything beyond a
    portfolio project, exactly as flagged for Motley Fool originally.

Missing transcripts remain the norm, not the exception, especially for
small/mid-caps that don't hold analyst calls at all -- this module always
returns a TranscriptDocument with `available=False` and a reason, never
raises.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .edgar_agent import (
    BSE_ANNOUNCEMENT_PDF_BASE,
    _extract_pdf_text,
    _get,
    resolve_bse_scrip_code,
    get_bse_announcements,
)
from .schemas import (
    CitationMetadata,
    DocumentType,
    TranscriptDocument,
    TranscriptSection,
    TranscriptUtterance,
)
from .utils import TRANSCRIPT_CACHE, retry

try:
    import requests
except ImportError:
    requests = None

TRENDLYNE_LISTING_URL = "https://trendlyne.com/conference-calls/"
TRENDLYNE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InvestmentResearchAgent/1.0 (a.pandeyj28@gmail.com)"

# Headline keywords used to identify a BSE announcement as an earnings-call
# transcript rather than any other Reg 30/33 filing sharing the same
# category. Best-effort text match, not a category code (see docstring).
TRANSCRIPT_HEADLINE_KEYWORDS = re.compile(
    r"(earnings?\s+call\s+transcript|transcript\s+of.*(conference|earnings|analyst)|conference\s+call\s+transcript)",
    re.I,
)

QA_MARKERS = re.compile(r"(question[- ]and[- ]answer|q\s?&\s?a session|moderator instructions|operator instructions)", re.I)
# Indian calls commonly label the call handler "Moderator:" rather than the
# US convention "Operator:" -- both are accepted as generic non-management
# speaker lines by the existing SPEAKER_LINE pattern, no special-casing
# needed there.
SPEAKER_LINE = re.compile(r"^([A-Z][A-Za-z.\-' ]{2,60}):\s+(.*)$")


def _unavailable(ticker: str, reason: str) -> TranscriptDocument:
    return TranscriptDocument(
        ticker=ticker.upper(),
        available=False,
        unavailable_reason=reason,
    )


def _most_recent_quarter_label() -> str:
    """India's fiscal year runs Apr-Mar, so quarter labeling differs from
    the US calendar-quarter convention the original module used. Returns
    e.g. 'Q1-FY27' for a call in Apr-Jun 2026."""
    from datetime import timezone as _tz
    now = datetime.now(_tz.utc)
    fiscal_year_end = now.year + 1 if now.month >= 4 else now.year
    fiscal_quarter = ((now.month - 4) % 12) // 3 + 1
    return f"Q{fiscal_quarter}-FY{str(fiscal_year_end)[-2:]}"


def _looks_like_transcript(headline: str) -> bool:
    return bool(TRANSCRIPT_HEADLINE_KEYWORDS.search(headline or ""))


def _find_transcript_via_bse(ticker: str) -> dict | None:
    """Primary path: search the company's own BSE announcement history for
    a Reg 30 transcript filing. Reuses edgar_agent's scrip-code
    resolution and rate-limited GET rather than duplicating that logic."""
    scrip_code = resolve_bse_scrip_code(ticker)
    if scrip_code is None:
        return None

    table = get_bse_announcements(scrip_code)
    if not table:
        return None

    candidates = []
    for row in table:
        headline = row.get("HEADLINE") or row.get("NEWSSUB") or ""
        if not _looks_like_transcript(headline):
            continue
        attachment = row.get("ATTACHMENTNAME") or row.get("Attachment")
        filed_date = row.get("NEWS_DT") or row.get("News_submission_dt")
        if attachment and filed_date:
            candidates.append({"attachment_name": attachment, "filed_date": filed_date, "headline": headline})

    if not candidates:
        return None
    candidates.sort(key=lambda c: c["filed_date"], reverse=True)
    latest = candidates[0]

    doc_url = f"{BSE_ANNOUNCEMENT_PDF_BASE}/{latest['attachment_name']}"
    pdf_resp = _get(doc_url)
    text = _extract_pdf_text(pdf_resp.content)
    if not text:
        return None

    return {"transcript": text, "filed_date": latest["filed_date"], "source_url": doc_url}


def _find_transcript_via_trendlyne(ticker: str) -> dict | None:
    """Fallback: scrape Trendlyne's public conference-call listing for a
    link matching this ticker. Same pragmatic-tradeoff caveat as the
    original Motley Fool scrape -- check Trendlyne's Terms of Use before
    using this beyond a learning/portfolio context. Untested against the
    live page structure (see module docstring)."""
    if requests is None:
        return None
    try:
        resp = requests.get(TRENDLYNE_LISTING_URL, headers={"User-Agent": TRENDLYNE_USER_AGENT}, timeout=15)
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code != 200:
        return None

    # Best-effort: look for an <a> pointing at a company's transcript page
    # whose slug/text contains the ticker symbol. Trendlyne's actual link
    # structure was not confirmed live -- this pattern will very likely
    # need adjustment on first real run.
    pattern = re.compile(
        rf'href="([^"]*{re.escape(ticker.lower())}[^"]*)"[^>]*>.*?transcript',
        re.I | re.S,
    )
    m = pattern.search(resp.text)
    if not m:
        return None
    transcript_page_url = m.group(1)
    if transcript_page_url.startswith("/"):
        transcript_page_url = "https://trendlyne.com" + transcript_page_url

    try:
        page_resp = requests.get(transcript_page_url, headers={"User-Agent": TRENDLYNE_USER_AGENT}, timeout=20)
    except Exception:  # noqa: BLE001
        return None
    if page_resp.status_code != 200:
        return None

    text = re.sub(r"<script.*?</script>", " ", page_resp.text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 500:
        return None
    return {"transcript": text, "filed_date": None, "source_url": transcript_page_url}


@retry(max_attempts=2, base_delay=1.5, exceptions=(ConnectionError, TimeoutError))
def _call_provider(ticker: str) -> dict | None:
    result = _find_transcript_via_bse(ticker)
    if result is not None:
        return result
    return _find_transcript_via_trendlyne(ticker)


def _structure_transcript(raw_text: str) -> list[tuple[str, TranscriptSection, str]]:
    """Unchanged from the original module's approach -- transcript prose
    structure (speaker lines, Q&A markers) doesn't vary by country the way
    filing structure does, so this parsing logic transfers directly.
    Degrades to a single 'Unknown' speaker/section if no speaker-line
    pattern is detected, same contract as before."""
    lines = raw_text.splitlines()
    entries: list[tuple[str, TranscriptSection, str]] = []
    current_section = TranscriptSection.PREPARED_REMARKS
    current_speaker = "Unknown"
    buffer: list[str] = []

    def flush():
        if buffer:
            entries.append((current_speaker, current_section, " ".join(buffer).strip()))
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if QA_MARKERS.search(stripped):
            flush()
            current_section = TranscriptSection.QA
            continue
        m = SPEAKER_LINE.match(stripped)
        if m:
            flush()
            current_speaker = m.group(1).strip()
            buffer.append(m.group(2).strip())
        else:
            buffer.append(stripped)
    flush()

    if not entries:
        entries = [("Unknown", TranscriptSection.UNKNOWN, raw_text.strip())]
    return entries


def fetch_transcript(ticker: str) -> TranscriptDocument:
    """Always returns a TranscriptDocument. Check `.available` before using
    `.utterances` -- an unavailable transcript is a normal, expected result
    (many Indian small/mid-caps hold no analyst calls at all), not a
    pipeline failure. Same contract as the original transcript_agent."""
    ticker = ticker.upper().strip()
    cache_key = f"in_transcript::{ticker}"
    cached = TRANSCRIPT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    fiscal_label = _most_recent_quarter_label()

    try:
        raw = _call_provider(ticker)
    except Exception as exc:  # noqa: BLE001 -- provider outage shouldn't crash the run
        doc = _unavailable(ticker, f"provider error: {exc}")
        TRANSCRIPT_CACHE.set(cache_key, doc)
        return doc

    if not raw or not raw.get("transcript"):
        doc = _unavailable(ticker, f"no transcript found for {fiscal_label}")
        TRANSCRIPT_CACHE.set(cache_key, doc)
        return doc

    raw_text = raw["transcript"]
    call_date = None
    if raw.get("filed_date"):
        try:
            call_date = datetime.strptime(str(raw["filed_date"])[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            call_date = None

    doc_url = raw.get("source_url", "")
    structured = _structure_transcript(raw_text)

    utterances = []
    for seq, (speaker, section, text) in enumerate(structured):
        if not text:
            continue
        utterances.append(TranscriptUtterance(
            metadata=CitationMetadata(
                ticker=ticker,
                document_type=DocumentType.EARNINGS_TRANSCRIPT,
                source_name="BSE (Reg. 30 filing)" if "bseindia" in doc_url else "Trendlyne (public transcript)",
                source_url=doc_url,
                section_id=f"{section.value}#{seq}",
                as_of_date=call_date,
            ),
            speaker=speaker,
            section=section,
            sequence=seq,
            text=text,
        ))

    doc = TranscriptDocument(
        ticker=ticker,
        fiscal_quarter=fiscal_label,
        call_date=call_date,
        available=True,
        utterances=utterances,
    )
    TRANSCRIPT_CACHE.set(cache_key, doc)
    return doc


if __name__ == "__main__":
    # Manual smoke test -- NOTE: not run against live endpoints in this
    # environment (see module docstring).
    #   python -m ingestion.transcript_agent RELIANCE
    import sys
    tk_symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    result = fetch_transcript(tk_symbol)
    if not result.available:
        print(f"Transcript unavailable for {tk_symbol}: {result.unavailable_reason}")
    else:
        print(f"{tk_symbol} {result.fiscal_quarter}: {len(result.utterances)} utterances")
        for u in result.utterances[:5]:
            print(f"  [{u.section.value}] {u.speaker}: {u.text[:100]}...")