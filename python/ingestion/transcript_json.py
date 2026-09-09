import sys
import json
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from ingestion.transcript_agent import fetch_transcript

def dump_json():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing ticker argument"}))
        return
    ticker = sys.argv[1]
    try:
        doc = fetch_transcript(ticker)
        res = {
            "available": doc.available,
            "unavailable_reason": getattr(doc, 'unavailable_reason', ""),
            "utterances": [{"speaker": u.speaker, "text": u.text, "section": u.section.value} for u in getattr(doc, 'utterances', [])] if doc.available else []
        }
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    dump_json()
