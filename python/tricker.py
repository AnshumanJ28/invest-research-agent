import sys
import os
import json
from curl_cffi import requests

import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_single_ticker(ticker, session):
    modules = "financialData,defaultKeyStatistics,summaryDetail,incomeStatementHistory,balanceSheetHistory,cashflowStatementHistory,price,summaryProfile"
    # Get legacy data
    crumb_resp = session.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
    crumb = crumb_resp.text.strip()
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}?modules={modules}&crumb={crumb}"
    data = {}
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            
            # Check if Yahoo data is completely missing or empty (e.g. ZOMATO.NS)
            needs_fallback = False
            res = data.get("quoteSummary", {}).get("result", [])
            if not res or res[0] is None or not res[0].get("incomeStatementHistory"):
                needs_fallback = True
                
            if needs_fallback:
                # Check for API key
                av_key = None
                if os.path.exists(".env"):
                    with open(".env", "r") as f:
                        for line in f:
                            if line.startswith("ALPHA_VANTAGE_KEY="):
                                av_key = line.strip().split("=")[1]
                                break
                
                if av_key:
                    print(f"  [Tricker] Yahoo data missing, falling back to Alpha Vantage for {ticker}...")
                    clean_t = ticker.replace(".NS", ".BSE") # Alpha Vantage uses .BSE for India
                    av_data = {}
                    for func in ["INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"]:
                        av_url = f"https://www.alphavantage.co/query?function={func}&symbol={clean_t}&apikey={av_key}"
                        try:
                            av_resp = requests.get(av_url, timeout=10).json()
                            av_data[func] = av_resp
                        except:
                            pass
                    data["alpha_vantage"] = av_data
    except: pass
    
    # Get modern yfinance data (injected stealth session)
    try:
        yf_ticker = yf.Ticker(ticker, session=session)
        
        # We only want the most recent column (iloc[:, 0]) 
        # and we must wrap it in a dummy date key "latest" so C++ extract_modern works
        
        bs = yf_ticker.balance_sheet
        if not bs.empty:
            data["modern_balance_sheet"] = {"latest": bs.iloc[:, 0].dropna().to_dict()}
            
        inc = yf_ticker.income_stmt
        if not inc.empty:
            data["modern_income_stmt"] = {"latest": inc.iloc[:, 0].dropna().to_dict()}
            
        cf = yf_ticker.cashflow
        if not cf.empty:
            data["modern_cashflow"] = {"latest": cf.iloc[:, 0].dropna().to_dict()}
    except Exception as e:
        print(f"  [Tricker] Error getting yfinance data for {ticker}: {e}")
        
    return ticker, data

def fetch_yahoo_data(generation_id, tickers):
    session = requests.Session(impersonate="chrome120")
    try: session.get("https://fc.yahoo.com", timeout=10)
    except: pass
    
    os.makedirs("json", exist_ok=True)
    peers_data = {}
    
    print(f"  [Tricker] Stealth session established. Fetching {len(tickers)} tickers concurrently...")
    with ThreadPoolExecutor(max_workers=len(tickers)) as executor:
        futures = {executor.submit(fetch_single_ticker, t, session): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                t, data = future.result()
                if ticker == tickers[0]:
                    with open(f"json/{generation_id}_yf_temp.json", "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    print(f"  [Tricker] Downloaded complete main data for {ticker}")
                else:
                    peers_data[ticker] = data
                    print(f"  [Tricker] Downloaded complete peer data for {ticker}")
            except Exception as e:
                print(f"  [Tricker] Failed to process {ticker}: {e}")

    if peers_data:
        with open(f"json/{generation_id}_peers_temp.json", "w", encoding="utf-8") as f:
            json.dump(peers_data, f)
        print(f"  [Tricker] Saved all peers to peers_temp.json")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tricker.py <generation_id> <main_ticker> [peer1] [peer2] ...")
        sys.exit(1)
        
    gen_id = sys.argv[1]
    tickers = sys.argv[2:]
    fetch_yahoo_data(gen_id, tickers)
