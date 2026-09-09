import sys
import json
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion.yfinance_agent import fetch_financial_statements

def dump_json():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing ticker argument"}))
        return

    ticker = sys.argv[1]
    exchange = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        stmts = fetch_financial_statements(ticker, use_cache=False, exchange=exchange)
        res = []
        for s in stmts:
            d = {
                "statement_type": s.statement_type.value,
                "fiscal_period": s.fiscal_period,
                "missing_fields": s.missing_fields,
                "line_items": [{"name": li.name, "value": li.value, "unit": getattr(li, "unit", "")} for li in s.line_items]
            }
            res.append(d)
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    dump_json()
