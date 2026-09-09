import sys
import json
import yfinance as yf
import math
import warnings

warnings.filterwarnings('ignore')

def safe_raw(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return {"fmt": None}
    return {"raw": float(val)}

def get_val(df, row_name, col_idx=0):
    if df is not None and row_name in df.index and len(df.columns) > col_idx:
        val = df.loc[row_name].iloc[col_idx]
        return safe_raw(val)
    return {"fmt": None}

def fetch_ticker_data(ticker):
    tkr = yf.Ticker(ticker)
    
    try:
        inc = tkr.financials
    except:
        inc = None
    try:
        bs = tkr.balance_sheet
    except:
        bs = None
    try:
        cf = tkr.cashflow
    except:
        cf = None
    try:
        info = tkr.info
    except:
        info = {}

    def get_date(df):
        if df is not None and not df.empty and len(df.columns) > 0:
            return {"fmt": df.columns[0].strftime('%Y-%m-%d')}
        return {"fmt": "current"}

    income_stmt = {
        "endDate": get_date(inc),
        "totalRevenue": get_val(inc, "Total Revenue"),
        "operatingRevenue": get_val(inc, "Operating Revenue"),
        "grossProfit": get_val(inc, "Gross Profit"),
        "operatingIncome": get_val(inc, "Operating Income"),
        "ebit": get_val(inc, "EBIT"),
        "netIncome": get_val(inc, "Net Income"),
        "netIncomeApplicableToCommonShares": get_val(inc, "Net Income Common Stockholders"),
        "ebitda": get_val(inc, "EBITDA"),
        "interestExpense": get_val(inc, "Interest Expense"),
        "interestExpenseNonOperating": get_val(inc, "Interest Expense Non Operating"),
        "incomeBeforeTax": get_val(inc, "Pretax Income")
    }
    
    balance_stmt = {
        "endDate": get_date(bs),
        "totalAssets": get_val(bs, "Total Assets"),
        "totalLiab": get_val(bs, "Total Liabilities Net Minority Interest"),
        "totalCurrentAssets": get_val(bs, "Current Assets"),
        "totalCurrentLiabilities": get_val(bs, "Current Liabilities"),
        "inventory": get_val(bs, "Inventory"),
        "shortLongTermDebtTotal": get_val(bs, "Total Debt"),
        "longTermDebt": get_val(bs, "Long Term Debt"),
        "totalStockholderEquity": get_val(bs, "Stockholders Equity"),
        "cash": get_val(bs, "Cash And Cash Equivalents")
    }
    
    cashflow_stmt = {
        "endDate": get_date(cf),
        "totalCashFromOperatingActivities": get_val(cf, "Operating Cash Flow"),
        "capitalExpenditures": get_val(cf, "Capital Expenditure"),
        "freeCashFlow": get_val(cf, "Free Cash Flow")
    }
    
    key_stats = {
        "trailingPE": safe_raw(info.get("trailingPE")),
        "forwardPE": safe_raw(info.get("forwardPE")),
        "priceToBook": safe_raw(info.get("priceToBook")),
        "pegRatio": safe_raw(info.get("pegRatio")),
        "enterpriseValue": safe_raw(info.get("enterpriseValue")),
        "beta": safe_raw(info.get("beta")),
        "currentPrice": safe_raw(info.get("currentPrice")),
        "targetMeanPrice": safe_raw(info.get("targetMeanPrice")),
        "revenueGrowth": safe_raw(info.get("revenueGrowth")),
        "earningsGrowth": safe_raw(info.get("earningsGrowth")),
        "dividendYield": safe_raw(info.get("dividendYield")),
        "fiftyTwoWeekHigh": safe_raw(info.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": safe_raw(info.get("fiftyTwoWeekLow")),
        "heldPercentInstitutions": safe_raw(info.get("heldPercentInstitutions")),
        "heldPercentInsiders": safe_raw(info.get("heldPercentInsiders")),
        "industry": info.get("industry")
    }
    
    return {
        "quoteSummary": {
            "result": [
                {
                    "incomeStatementHistory": {
                        "incomeStatementHistory": [income_stmt]
                    },
                    "balanceSheetHistory": {
                        "balanceSheetStatements": [balance_stmt]
                    },
                    "cashflowStatementHistory": {
                        "cashflowStatements": [cashflow_stmt]
                    },
                    "defaultKeyStatistics": key_stats
                }
            ]
        }
    }

def main(ticker):
    print(json.dumps(fetch_ticker_data(ticker)))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
