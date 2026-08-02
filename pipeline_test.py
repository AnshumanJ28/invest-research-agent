"""
pipeline_test.py -- quick smoke test across ingestion agents.

Usage:
    python pipeline_test.py TICKER.NS

Note: edgar_agent's API is known (fetch_latest_filings), so that part runs
for real. The other three agents' exact function names weren't available
when this was written, so this script INTROSPECTS them instead of guessing
-- it lists the public functions each module exposes so you can see what's
actually callable. Paste that output back and the calls can be wired up
properly.
"""

import inspect
import sys


def run_test_yfinance_agent(ticker: str) -> None:
    try:
        from ingestion.yfinance_agent import fetch_financial_statements
    except ImportError as e:
        print(f"  could not import yfinance_agent: {e}")
        return

    try:
        data = fetch_financial_statements(ticker)
    except Exception as e:  # noqa: BLE001
        print(f"  fetch_financial_statements raised: {e}")
        return

    if isinstance(data, dict):
        for key, value in data.items():
            n = len(value) if hasattr(value, "__len__") else "?"
            print(f"  {key}: {n} items")
    else:
        print(f"  result: {data!r}")


def run_test_transcript_agent(ticker: str) -> None:
    try:
        from ingestion.transcript_agent import fetch_transcript
    except ImportError as e:
        print(f"  could not import transcript_agent: {e}")
        return

    try:
        result = fetch_transcript(ticker)
    except Exception as e:  # noqa: BLE001
        print(f"  fetch_transcript raised: {e}")
        return

    print(f"  result: {result!r}"[:300])


def run_test_news_agent(ticker: str) -> None:
    try:
        from ingestion.news_agent import fetch_news
    except ImportError as e:
        print(f"  could not import news_agent: {e}")
        return

    try:
        result = fetch_news(ticker)
    except Exception as e:  # noqa: BLE001
        print(f"  fetch_news raised: {e}")
        return

    n = len(result) if hasattr(result, "__len__") else "?"
    print(f"  {n} articles found")


def run_test_edgar_agent(ticker: str) -> None:
    try:
        from ingestion.edgar_agent import fetch_latest_filings
    except ImportError as e:
        print(f"  could not import edgar_agent: {e}")
        return

    try:
        docs = fetch_latest_filings(ticker)
    except Exception as e:  # noqa: BLE001
        print(f"  fetch_latest_filings raised: {e}")
        return

    for form, doc in docs.items():
        if doc is None:
            print(f"  {form}: unavailable")
        else:
            print(f"  {form}: {len(doc.sections)} sections (filed {doc.filed_date})")


import threading

class ThreadLocalStream:
    def __init__(self, original_stream):
        self.original = original_stream
        self.local = threading.local()

    def write(self, data):
        if hasattr(self.local, "buf"):
            self.local.buf.write(data)
        else:
            self.original.write(data)

    def flush(self):
        if hasattr(self.local, "buf"):
            self.local.buf.flush()
        else:
            self.original.flush()


def main() -> None:
    ticker = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    print(f"=== Testing pipeline (PARALLEL) for {ticker} ===")

    import concurrent.futures
    import io

    local_stream = ThreadLocalStream(sys.stdout)
    sys.stdout = local_stream

    def run_test(name, fn):
        local_stream.local.buf = io.StringIO()
        try:
            print(f"--- {name} ---")
            fn(ticker)
            val = local_stream.local.buf.getvalue()
        finally:
            del local_stream.local.buf
        return val

    tests = [
        ("yfinance_agent", run_test_yfinance_agent),
        ("edgar_agent", run_test_edgar_agent),
        ("transcript_agent", run_test_transcript_agent),
        ("news_agent", run_test_news_agent)
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_test, name, fn): name for name, fn in tests}
        for future in concurrent.futures.as_completed(futures):
            # Temporarily restore original sys.stdout to output the captured buffer
            sys.stdout = local_stream.original
            print(future.result(), end="")
            sys.stdout = local_stream

    # Restore original sys.stdout
    sys.stdout = local_stream.original
    print("=== Done ===")


if __name__ == "__main__":
    main()