import sys
import json
from yf_json import fetch_ticker_data
import warnings

warnings.filterwarnings('ignore')

def main(tickers):
    result = {}
    for t in tickers:
        try:
            result[t] = fetch_ticker_data(t)
        except:
            pass
    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1:])
