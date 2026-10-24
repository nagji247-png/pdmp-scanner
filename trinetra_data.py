#!/usr/bin/env python3
"""Build TRINETRA's free-data company universe snapshot.
The official NSE equity list is used for listed-symbol discovery. Yahoo Finance
is best-effort for fundamentals; missing or blocked fields stay null, never guessed.
"""
import csv, io, json, os, datetime as dt
from urllib.parse import urlparse
import requests
import yfinance as yf

OUT = os.environ.get("TRINETRA_OUT", "trinetra-data.json")
NSE_URLS = [
    "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
    "https://archives.nseindia.com/content/equities/EQUITY_L.csv",
]
HEADERS = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"text/csv,*/*"}
SECTOR_MAP = {
"RELIANCE":"Energy & Power","NTPC":"Energy & Power","POWERGRID":"Energy & Power","COALINDIA":"Energy & Power","ONGC":"Energy & Power","TATAPOWER":"Energy & Power","ADANIGREEN":"Energy & Power","JSWENERGY":"Energy & Power",
"BEL":"Industrials & Defence","HAL":"Industrials & Defence","BHEL":"Industrials & Defence","LT":"Industrials & Defence","MAZDOCK":"Industrials & Defence","BDL":"Industrials & Defence","CUMMINSIND":"Industrials & Defence",
"SUNPHARMA":"Pharma & Healthcare","CIPLA":"Pharma & Healthcare","DRREDDY":"Pharma & Healthcare","APOLLOHOSP":"Pharma & Healthcare","DIVISLAB":"Pharma & Healthcare","LUPIN":"Pharma & Healthcare","ZYDUSLIFE":"Pharma & Healthcare",
"TCS":"Tech & Telecom","INFY":"Tech & Telecom","WIPRO":"Tech & Telecom","HCLTECH":"Tech & Telecom","TECHM":"Tech & Telecom","BHARTIARTL":"Tech & Telecom","INDUSTOWER":"Tech & Telecom",
"ADANIPORTS":"Services & Logistics","CONCOR":"Services & Logistics","DELHIVERY":"Services & Logistics","BLUEDART":"Services & Logistics","INDIGO":"Services & Logistics",
"TATAMOTORS":"Autos","M&M":"Autos","MARUTI":"Autos","EICHERMOT":"Autos","HEROMOTOCO":"Autos","BAJAJ-AUTO":"Autos","TVSMOTOR":"Autos","ASHOKLEY":"Autos",
"HINDALCO":"Materials","TATASTEEL":"Materials","JSWSTEEL":"Materials","ULTRACEMCO":"Materials","GRASIM":"Materials","AMBUJACEM":"Materials","VEDL":"Materials",
"ITC":"Consumer","HINDUNILVR":"Consumer","TITAN":"Consumer","ASIANPAINT":"Consumer","NESTLEIND":"Consumer","TRENT":"Consumer","VBL":"Consumer","DMART":"Consumer",
"HDFCBANK":"Banks & Property","ICICIBANK":"Banks & Property","SBIN":"Banks & Property","KOTAKBANK":"Banks & Property","AXISBANK":"Banks & Property","BAJFINANCE":"Banks & Property","DLF":"Banks & Property","LICI":"Banks & Property"
}
def num(v):
    try:
        x=float(v)
        return x if x == x and abs(x) != float("inf") else None
    except (TypeError, ValueError): return None

def get_universe():
    last=None
    for url in NSE_URLS:
        try:
            r=requests.get(url,headers=HEADERS,timeout=25)
            r.raise_for_status()
            rows=list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
            if rows and "SYMBOL" in rows[0] and "NAME OF COMPANY" in rows[0]:
                out=[]
                for row in rows:
                    sym=(row.get("SYMBOL") or "").strip()
                    if not sym: continue
                    out.append({"symbol":sym,"name":(row.get("NAME OF COMPANY") or "").strip() or None,
                                "isin":(row.get("ISIN NUMBER") or "").strip() or None,
                                "sector":SECTOR_MAP.get(sym)})
                if len(out) >= 100:
                    return out
                last="NSE CSV returned too few valid equity rows"
            else:
                last="NSE CSV headers were not recognized"
        except Exception as e: last=str(e)
    raise RuntimeError("NSE official equity list unavailable: "+str(last))

def fundamentals(symbol):
    result={"price":None,"market_cap":None,"pe":None,"eps":None,"roe":None,
            "week52_low":None,"week52_high":None,"rsi14":None,"revenue_growth":None,
            "profit_growth":None,"promoter_pct":None,"fii_pct":None,"dii_pct":None,
            "currency":None,"source":"Yahoo Finance (best-effort)","as_of":None}
    try:
        t=yf.Ticker(symbol+".NS")
        info=t.get_info()
        result.update({
          "price":num(info.get("currentPrice") or info.get("regularMarketPrice")),
          "market_cap":num(info.get("marketCap")),
          "pe":num(info.get("trailingPE")),
          "eps":num(info.get("trailingEps")),
          "roe":num(info.get("returnOnEquity")),
          "week52_low":num(info.get("fiftyTwoWeekLow")),
          "week52_high":num(info.get("fiftyTwoWeekHigh")),
          "revenue_growth":num(info.get("revenueGrowth")),
          "profit_growth":num(info.get("earningsGrowth")),
          "currency":info.get("currency"),
          "as_of":None
        })
        # Do not label the retrieval time as the exchange quote time.
        quote_time=info.get("regularMarketTime")
        if quote_time:
            try:
                result["as_of"]=dt.datetime.fromtimestamp(float(quote_time),dt.timezone.utc).isoformat(timespec="seconds")
            except (TypeError,ValueError,OverflowError):
                result["as_of"]=None
        try:
            hist=t.history(period="3mo", interval="1d", auto_adjust=False)
            close=hist["Close"].dropna()
            delta=close.diff()
            gains=delta.clip(lower=0).rolling(14).mean()
            losses=(-delta.clip(upper=0)).rolling(14).mean()
            if len(close)>=15:
                avg_gain=float(gains.iloc[-1]); avg_loss=float(losses.iloc[-1])
                result["rsi14"]=100.0 if avg_loss==0 and avg_gain>0 else (50.0 if avg_loss==0 and avg_gain==0 else (100-(100/(1+avg_gain/avg_loss)) if avg_loss>0 else None))
        except Exception:
            result["rsi14"]=None
    except Exception:
        result["error"]="Fundamental data unavailable from free source"
    return result

def main():
    companies=get_universe()
    # Small verified seed set for usable initial details; full universe remains searchable.
    # Additional symbols can be enriched on later runs to avoid hammering free endpoints.
    seed={"RELIANCE","HDFCBANK","TATAMOTORS","HINDALCO","ADANIPORTS","COALINDIA","EICHERMOT","APOLLOHOSP","SBIN","TCS","INFY","BEL","HAL","SUNPHARMA","NTPC","ITC","ICICIBANK","LT","MARUTI","BHARTIARTL"}
    for c in companies:
        if c["symbol"] in seed:
            c["fundamentals"]=fundamentals(c["symbol"])
        else:
            c["fundamentals"]=None
    data={"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "source":"NSE official listed equity CSV; Yahoo Finance best-effort fundamentals",
          "companies_count":len(companies),"companies":companies,
          "disclaimer":"Sector is only populated for a curated mapping. Missing fundamentals/holdings are null, not zero. Business relationships are not inferred from sector."}
    with open(OUT,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,separators=(",",":"))
    print("Wrote",OUT,"with",len(companies),"NSE equity records")
if __name__=="__main__": main()
