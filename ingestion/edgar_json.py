import sys
import json
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ingestion.edgar_agent import fetch_latest_filings

def dump_json():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing ticker argument"}))
        return
    ticker = sys.argv[1]
    try:
        docs = fetch_latest_filings(ticker)
        res = {}
        for form, doc in docs.items():
            if doc is None:
                res[form] = None
            else:
                res[form] = {
                    "filed_date": doc.filed_date.isoformat() if doc.filed_date else None,
                    "sections": [{"name": s.section_name, "text": s.text} for s in doc.sections]
                }
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    dump_json()
