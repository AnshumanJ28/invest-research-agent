import sys
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from yf_json import fetch_ticker_data

def main():
    if len(sys.argv) < 2:
        print("Usage: python async_fetch.py TICKER [PEER1 PEER2 ...]")
        return
        
    main_ticker = sys.argv[1]
    peers = sys.argv[2:] if len(sys.argv) > 2 else []
    
    os.makedirs("json", exist_ok=True)
    
    main_data = {}
    peers_data = {}
    
    def fetch_t(t, is_main):
        try:
            res = fetch_ticker_data(t)
            if is_main:
                main_data.update(res)
            else:
                peers_data[t] = res
        except Exception as e:
            print(f"Failed to fetch {t}: {e}")
            
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(fetch_t, main_ticker, True)]
        for p in peers:
            futures.append(executor.submit(fetch_t, p, False))
            
        for future in as_completed(futures):
            future.result()
            
    with open("json/yf_temp.json", "w", encoding="utf-8") as f:
        json.dump(main_data, f)
        
    with open("json/peers_temp.json", "w", encoding="utf-8") as f:
        json.dump(peers_data, f)
        
    print(f"  [async_fetch] Fetched {main_ticker} and {len(peers)} peers natively in parallel!")

if __name__ == '__main__':
    main()
