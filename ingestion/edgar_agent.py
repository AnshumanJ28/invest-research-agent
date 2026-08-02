"""
Indian Filings Agent (NSE/BSE) -- replacement for edgar_agent.py's role,
NOT a config tweak of it.

Per project notes: SEC EDGAR has no Indian filings. Indian companies file
with SEBI/the exchanges (NSE, BSE), not the SEC, and there is no equivalent
of EDGAR's clean, documented, rate-limited JSON API for India -- neither
NSE nor BSE publishes a public self-serve REST API. What exists instead is
the exchanges' own public *websites* (nseindia.com / bseindia.com), which
serve corporate filings as PDFs and are commonly accessed via undocumented,
unofficial endpoints that third-party scrapers have reverse-engineered.

*** VERIFICATION STATUS: UNVERIFIED / NOT TESTED AGAINST LIVE ENDPOINTS ***
This module was written from published documentation of community scraper
projects (not from live testing -- this environment's network access does
not include nseindia.com, bseindia.com, or screener.in). Specifically:
  - `resolve_bse_scrip_code` hits BSE's search endpoint (api.bseindia.com)
    whose response shape is inferred from third-party reverse-engineering,
    not from an official spec. Field names, required headers, and even
    endpoint paths may have shifted since those were documented, and BSE
    can change them without notice.
  - `_latest_filings` now goes through the `bse` PyPI package rather than
    hand-rolling the raw `AnnGetData` endpoint call. That package wraps
    the same undocumented endpoint, so the same caveat applies -- it's
    just maintained upstream instead of duplicated here.
  - Before relying on this in production: (1) hit each endpoint manually
    and confirm the JSON shape assumed below, (2) confirm BSE's actual
    rate-limit tolerance (the limiter here is a conservative guess, not a
    documented number the way SEC's 10 req/sec is), (3) consider a paid
    data vendor (e.g. the announcement APIs referenced in the project
    notes) if uptime/reliability matters, since this is scraping a public
    website rather than calling a stable API.

What's structurally different from `edgar_agent.py`, not just re-pointed:
  1. Source documents are PDFs, not HTML -- there's no `_strip_html`
     equivalent; PDF text extraction is a different pipeline entirely
     (see `_extract_pdf_text`).
  2. Company identifier is a BSE scrip code (or NSE symbol), not a CIK --
     there's no SEC-style `company_tickers.json`; resolution goes through
     BSE's own fuzzy company search.
  3. Filing taxonomy is different -- India has no 10-K/10-Q. The rough
     equivalents used here are "annual_report" (annual report incl.
     Board's Report / Directors' Report and MD&A, filed under SEBI LODR)
     and "quarterly_results" (SEBI Reg. 33 quarterly financial results --
     much thinner than a 10-Q; often financials + limited-review report
     only, no MD&A section, unless the company separately publishes an
     investor presentation).
  4. Section headers are NOT standardized the way "Item 1A" is in a 10-K.
     `INDIAN_ANNUAL_REPORT_SECTION_HEADERS` below is a best-effort list of
     commonly-used heading phrases; expect a materially higher rate of
     documents falling back to a single "Full Document" section compared
     to the EDGAR agent.

Known follow-up dependency: this module reuses `schemas.CitationMetadata`,
`schemas.FilingDocument`, and `schemas.FilingSection` as-is to avoid
touching a file not provided here. Two rough edges from that reuse are
called out inline: `DocumentType` has no ANNUAL_REPORT/QUARTERLY_RESULTS
members yet (falls back to the SEC_FILING_10K/10Q members with a
mismatched-name caveat), and `FilingDocument.cik` is repurposed to hold the
BSE scrip code. Share schemas.py and both can be cleaned up properly.
"""

from __future__ import annotations

import io
import re
import threading
import time
from datetime import datetime, timedelta, timezone

from .schemas import CitationMetadata, DocumentType, FilingDocument, FilingSection
from .utils import FILING_CACHE, BSE_ANNOUNCEMENTS_CACHE, retry

try:
    import requests
except ImportError:
    requests = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from bse import BSE
except ImportError:
    BSE = None


USER_AGENT = "AnshumanJ28 a.pandeyj28@gmail.com"  # NOTE: real deployment
                                                               # must replace with the
                                                               # team's actual contact.
                                                               # BSE doesn't require this
                                                               # the way SEC does, but
                                                               # sending an honest UA is
                                                               # good etiquette when
                                                               # scraping a public site.

# Unofficial, reverse-engineered endpoint (see module docstring caveat).
# Only used for company-name -> scrip-code resolution; announcements go
# through the `bse` package (see `_get_bse_client` / `_latest_filings`).
BSE_SEARCH_URL = "https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearch/w"
BSE_ANNOUNCEMENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_ANNOUNCEMENT_PDF_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"

# BSE announcement category codes as used by the `bse` package's
# `announcements()` call (per third-party documentation -- unverified).
# "AR" ~ Annual Report, "Result" ~ quarterly/annual financial results
# filed under Reg. 33.
BSE_CATEGORY_BY_FORM_TYPE = {
    "annual_report": "AR",
    "quarterly_results": "Result",
}

# Best-effort section headers for Indian annual reports. Far less
# standardized than a US 10-K's "Item N" scheme -- treat this as a
# starting point to refine once tested against real filings, not a
# guarantee of clean segmentation.
INDIAN_ANNUAL_REPORT_SECTION_HEADERS = [
    "Board's Report",
    "Directors' Report",
    "Management Discussion and Analysis",
    "Business Responsibility Report",
    "Business Responsibility and Sustainability Report",
    "Corporate Governance Report",
    "Report on Corporate Governance",
    "Independent Auditor's Report",
    "Balance Sheet",
    "Statement of Profit and Loss",
    "Notes to Financial Statements",
    "Notes to the Financial Statements",
    "Cash Flow Statement",
]


class _MinIntervalRateLimiter:
    """Simple 'at most one request every N seconds' limiter. BSE publishes
    no documented rate limit (unlike SEC's 10 req/sec), so this is a
    conservative default, not a verified figure -- tune down only after
    confirming BSE tolerates it."""

    def __init__(self, min_interval_seconds: float = 1.0):
        self._min_interval = min_interval_seconds
        self._lock = threading.Lock()
        self._last_call = 0.0

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()


BSE_RATE_LIMITER = _MinIntervalRateLimiter(min_interval_seconds=1.0)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.bseindia.com/",
        "Origin": "https://www.bseindia.com",
        "X-Requested-With": "XMLHttpRequest",
    }


@retry(max_attempts=3, base_delay=2.0, exceptions=(requests.RequestException,) if requests is not None else (Exception,))
def _get(url: str, params: dict | None = None) -> "requests.Response":
    if requests is None:
        raise RuntimeError("requests is not installed in this environment")
    BSE_RATE_LIMITER.acquire()
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    return resp


# Lazily-instantiated singleton for the `bse` package's client. Lazy so
# that importing this module never touches the filesystem or the network
# on its own, and so the module still imports cleanly in environments
# where `bse` isn't installed (matches the optional-import pattern used
# for requests/pdfplumber/PyPDF2 above).
_bse_client: "BSE | None" = None


def _get_bse_client() -> "BSE":
    global _bse_client
    if BSE is None:
        raise RuntimeError("bse package is not installed in this environment")
    if _bse_client is None:
        _bse_client = BSE(download_folder="./")
    return _bse_client


def resolve_bse_company_info(ticker_or_name: str) -> tuple[str | None, str | None]:
    """Resolve an NSE symbol or company name to a BSE scrip code and company name
    via BSE's fuzzy company search. Cached hard.
    """
    cache_key = f"bse_company_info::{ticker_or_name.upper()}"
    cached = FILING_CACHE.get(cache_key)
    if cached is not None:
        return cached

    search_text = ticker_or_name.upper().replace(".NS", "").replace(".BO", "").strip()
    resp = _get(BSE_SEARCH_URL, params={"Type": "SS", "text": search_text})
    raw = resp.text
    matches = re.findall(r"liclick\('(\d+)',\s*'([^']+)'\)", raw)

    if not matches and len(search_text) > 4:
        # Fall back to searching for the first 4 characters of the name
        prefix = search_text[:4]
        try:
            resp = _get(BSE_SEARCH_URL, params={"Type": "SS", "text": prefix})
            raw = resp.text
            matches = re.findall(r"liclick\('(\d+)',\s*'([^']+)'\)", raw)
        except Exception:  # noqa: BLE001
            pass

    if not matches:
        FILING_CACHE.set(cache_key, (None, None))
        return None, None

    query_upper = ticker_or_name.upper().replace(".NS", "").replace(".BO", "")
    norm_query = re.sub(r"[^A-Z0-9]", "", query_upper)
    best_code, best_name = None, None
    for scrip_code, company_name in matches:
        norm_name = re.sub(r"[^A-Z0-9]", "", company_name.upper())
        if norm_query == norm_name or norm_query in norm_name or norm_name in norm_query:
            best_code = scrip_code
            best_name = company_name
            break
    if best_code is None:
        best_code, best_name = matches[0][0], matches[0][1]

    result = (best_code, best_name)
    FILING_CACHE.set(cache_key, result)
    return result


def resolve_bse_scrip_code(ticker_or_name: str) -> str | None:
    """Resolve an NSE symbol or company name to a BSE scrip code.
    """
    code, _ = resolve_bse_company_info(ticker_or_name)
    return code


def get_bse_announcements(scrip_code: str) -> list[dict]:
    cache_key = f"bse_announcements::{scrip_code}"
    cached = BSE_ANNOUNCEMENTS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    data = _get_bse_client().announcements(
        scripcode=scrip_code,
        from_date=datetime.now() - timedelta(days=730),  # annual reports are ~yearly; widen the window
        to_date=datetime.now(),
        category="-1",  # Fetch all categories to cache at once
    )
    table = data.get("Table") or []
    BSE_ANNOUNCEMENTS_CACHE.set(cache_key, table)
    return table


def _latest_filings(scrip_code: str, form_type: str) -> list[dict]:
    table = get_bse_announcements(scrip_code)

    out = []
    for row in table:
        subcat = (row.get("SUBCATNAME") or "").lower()
        cat = (row.get("CATEGORYNAME") or "").lower()

        if form_type == "annual_report":
            if "annual report" not in subcat:
                continue
        elif form_type == "quarterly_results":
            if cat != "result" and "financial results" not in subcat:
                continue
        else:
            raise ValueError(f"Unknown form_type '{form_type}'")

        out.append({
            "form": form_type,
            "filed_date": row.get("NEWS_DT") or row.get("News_submission_dt"),
            "attachment_name": row.get("ATTACHMENTNAME"),
            "headline": row.get("HEADLINE") or row.get("NEWSSUB"),
        })
    out = [f for f in out if f["filed_date"] and f["attachment_name"]]
    out.sort(key=lambda f: f["filed_date"], reverse=True)
    return out[:1]


def _extract_pdf_pages_chunk(pdf_bytes: bytes, start_page: int, end_page: int) -> list[str]:
    """Helper function for chunked PDF page extraction within thread workers."""
    try:
        import PyPDF2
        import io
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for idx in range(start_page, min(end_page, len(reader.pages))):
            try:
                texts.append(reader.pages[idx].extract_text() or "")
            except Exception:
                texts.append("")
        return texts
    except Exception:
        return [""] * (end_page - start_page)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """PDF text extraction with a two-library fallback, mirroring the
    dependency-light spirit of edgar_agent's _strip_html but for a
    genuinely different document format. Indian annual report PDFs are
    frequently scanned/image-based for older filings -- this extracts
    embedded text only, no OCR. A PDF that yields no text (scanned, no
    text layer) returns an empty string, which callers must handle as
    'unavailable', same as a missing filing."""
    if PyPDF2 is not None:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            num_pages = len(reader.pages)
            if num_pages > 15:
                import concurrent.futures
                import os
                num_workers = min(4, os.cpu_count() or 1)
                chunk_size = (num_pages + num_workers - 1) // num_workers

                chunks = []
                for i in range(num_workers):
                    start = i * chunk_size
                    end = min(start + chunk_size, num_pages)
                    if start < num_pages:
                        chunks.append((start, end))

                with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                    futures = [executor.submit(_extract_pdf_pages_chunk, pdf_bytes, start, end) for start, end in chunks]
                    results = [f.result() for f in futures]

                text_parts = []
                for res in results:
                    text_parts.extend(res)
                return "\n\n".join(text_parts).strip()
            else:
                text_parts = [page.extract_text() or "" for page in reader.pages]
                return "\n\n".join(text_parts).strip()
        except Exception:  # noqa: BLE001
            pass

    if pdfplumber is not None:
        try:
            text_parts = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_parts.append(page_text)
            return "\n\n".join(text_parts).strip()
        except Exception:  # noqa: BLE001
            pass  # fall through to returning empty string

    return ""


def _split_sections(full_text: str) -> list[tuple[str, str]]:
    """Split cleaned filing text into (section_name, section_text) pairs
    using best-effort Indian annual report heading phrases. Falls back to
    a single 'Full Document' section, which -- unlike in the EDGAR agent --
    should be expected as a common outcome here, not an edge case, until
    this list is refined against real filings."""
    positions: list[tuple[int, str]] = []
    for heading in INDIAN_ANNUAL_REPORT_SECTION_HEADERS:
        pattern = re.compile(re.escape(heading), re.I)
        matches = list(pattern.finditer(full_text))
        if matches:
            # Same TOC-vs-real-heading ambiguity as the EDGAR agent; last
            # match wins on the assumption the TOC entry comes first.
            positions.append((matches[-1].start(), heading))

    if not positions:
        return [("Full Document", full_text)]

    positions.sort()
    sections = []
    for i, (start, name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(full_text)
        sections.append((name, full_text[start:end].strip()))
    return sections


def _paragraphs(section_text: str, max_paragraphs: int = 40) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n{2,}|(?<=\.)\s{2,}", section_text) if len(p.strip()) > 40]
    if not paras:
        sentences = re.split(r"(?<=[.!?])\s+", section_text)
        paras = [" ".join(sentences[i:i + 5]) for i in range(0, len(sentences), 5)]
    return paras[:max_paragraphs]


def _resolve_document_type(form_type: str):
    """DocumentType has no ANNUAL_REPORT/QUARTERLY_RESULTS members yet (see
    module docstring). Falls back to the closest SEC-named member so the
    pipeline still runs; the name will read oddly ("sec_filing_10k" on an
    Indian annual report) until schemas.py adds proper members."""
    if form_type == "annual_report":
        return getattr(DocumentType, "ANNUAL_REPORT", DocumentType.SEC_FILING_10K)
    return getattr(DocumentType, "QUARTERLY_RESULTS", DocumentType.SEC_FILING_10Q)


def fetch_filing(ticker: str, form_type: str) -> FilingDocument | None:
    """Fetch and section the most recent Indian filing of `form_type`
    ('annual_report' or 'quarterly_results') for `ticker`. Returns None if
    the ticker can't be resolved to a BSE scrip code or has no filing of
    that type -- callers should handle None as a graceful 'unavailable',
    same contract as edgar_agent.fetch_filing."""
    ticker = ticker.upper().strip()
    cache_key = f"in_filing::{ticker}::{form_type}"
    cached = FILING_CACHE.get(cache_key)
    if cached is not None:
        return cached

    scrip_code = resolve_bse_scrip_code(ticker)
    if scrip_code is None:
        return None

    filings = _latest_filings(scrip_code, form_type)
    if not filings:
        return None
    filing = filings[0]

    doc_url = f"{BSE_ANNOUNCEMENT_PDF_BASE}/{filing['attachment_name']}"
    try:
        resp = _get(doc_url)
        pdf_text = _extract_pdf_text(resp.content)
    except Exception:  # noqa: BLE001
        pdf_text = ""
    if not pdf_text:
        # No text layer (likely scanned PDF) -- return None rather than an
        # empty-but-"successful" FilingDocument that would silently pass
        # downstream checks.
        return None

    section_pairs = _split_sections(pdf_text)

    try:
        filed_date = datetime.strptime(filing["filed_date"][:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        filed_date = None

    doc_type = _resolve_document_type(form_type)
    sections: list[FilingSection] = []
    for section_name, section_text in section_pairs:
        for idx, para in enumerate(_paragraphs(section_text)):
            sections.append(FilingSection(
                metadata=CitationMetadata(
                    ticker=ticker,
                    document_type=doc_type,
                    source_name="BSE",
                    source_url=doc_url,
                    section_id=f"{section_name.lower().replace(' ', '_')}#{idx}",
                    as_of_date=filed_date,
                ),
                section_name=section_name,
                paragraph_index=idx,
                text=para,
            ))

    doc = FilingDocument(
        ticker=ticker,
        cik=scrip_code,  # repurposed field -- see module docstring
        filing_type=form_type,
        filed_date=filed_date,
        accession_number=filing["attachment_name"],  # closest BSE analogue to an accession number
        sections=sections,
    )
    FILING_CACHE.set(cache_key, doc)
    return doc


def fetch_latest_filings(ticker: str) -> dict[str, FilingDocument | None]:
    """Convenience wrapper: most recent annual report and quarterly results
    in one call. Same single-most-recent-only scope as edgar_agent's
    fetch_latest_filings -- no historical archive crawling."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_ar = executor.submit(fetch_filing, ticker, "annual_report")
        future_qr = executor.submit(fetch_filing, ticker, "quarterly_results")
        return {
            "annual_report": future_ar.result(),
            "quarterly_results": future_qr.result(),
        }


if __name__ == "__main__":
    # Manual smoke test -- NOTE: per the module docstring, this has not
    # been run against live BSE endpoints in this environment. Expect to
    # debug field names/endpoint shape on first real run.
    #   python -m ingestion.edgar_agent RELIANCE
    import sys
    tk_symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    docs = fetch_latest_filings(tk_symbol)
    for form, doc in docs.items():
        if doc is None:
            print(f"{form}: unavailable")
            continue
        print(f"\n=== {form} filed {doc.filed_date} ({len(doc.sections)} sections) ===")
        for s in doc.sections[:3]:
            print(f"  [{s.metadata.section_id}] {s.text[:120]}...")