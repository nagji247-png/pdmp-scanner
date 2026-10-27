import json, datetime as dt, time
from pathlib import Path
import yfinance as yf

# स्वतंत्र सेक्टर वॉचलिस्ट: पुराने PDMP/Google Trends/News डेटा से कोई निर्भरता नहीं।
WATCHLIST = {
 "RELIANCE":"RELIANCE.NS","HDFCBANK":"HDFCBANK.NS","TATAMOTORS":"TMPV.NS",
 "HINDALCO":"HINDALCO.NS","ADANIPORTS":"ADANIPORTS.NS","COALINDIA":"COALINDIA.NS",
 "EICHERMOT":"EICHERMOT.NS","APOLLOHOSP":"APOLLOHOSP.NS","SBIN":"SBIN.NS",
 "SUZLON":"SUZLON.NS","DLINKINDIA":"DLINKINDIA.NS","VEDL":"VEDL.NS",
 "APOLLOMICRO":"APOLLOMICRO.NS","MSUMI":"MSUMI.NS","PARAS":"PARAS.NS","IOC":"IOC.NS",
 "GULPOLY":"GULPOLY.NS","GPPL":"GPPL.NS","JAGRAN":"JAGRAN.NS",
 "RAYMOND":"RAYMOND.NS","AUTHUM":"AHLUCONT.NS","HDFCAMC":"HDFCAMC.NS",
 "ASTERDM":"ASTERDM.NS","DLF":"DLF.NS","IRB":"IRB.NS","OBEROIRLTY":"OBEROIRLTY.NS",
 "NATCOPHARM":"NATCOPHARM.NS","GESHIP":"GESHIP.NS","EMBASSY":"EMBASSY.NS","ITC":"ITC.NS",
 "SUNTV":"SUNTV.NS","OFSS":"OFSS.NS","POWERGRID":"POWERGRID.NS","INDUSTOWER":"INDUSTOWER.NS",
 "JSWINFRA":"JSWINFRA.NS","NATIONALUM":"NATIONALUM.NS","MOTILALOFS":"MOTILALOFS.NS",
 "COLPAL":"COLPAL.NS","PGHH":"PGHH.NS","IRIS":"IRIS.NS","TIPSMUSIC":"TIPSMUSIC.NS",
 "GILLETTE":"GILLETTE.NS","GEPIL":"GEPIL.NS","PGHL":"PGHL.NS","ESABINDIA":"ESABINDIA.NS",
 "GOCLCORP":"GOCLCORP.NS","EMKAYTOOLS":"EMKAYTOOLS.NS","SANOFI":"SANOFI.NS","TCS":"TCS.NS",
 "NCC":"NCC.NS","NOCIL":"NOCIL.NS","PINE":"PINE.NS"
}
def num(x):
 try:
  x=float(x)
  return round(x,2) if x==x and abs(x)!=float("inf") else None
 except (TypeError,ValueError): return None

def analyse(name,symbol):
 out={"name":name,"symbol":symbol,"source":"Yahoo Finance (free; market data may be delayed)","ok":False}
 try:
  t=yf.Ticker(symbol)
  h=t.history(period="1y",interval="1d",auto_adjust=False)
  info=t.info or {}
  if h.empty: raise ValueError("कोई दैनिक भाव डेटा नहीं मिला; ticker/source जाँचें")
  close=h["Close"].dropna()
  last=float(close.iloc[-1]); prev=float(close.iloc[-2]) if len(close)>1 else None
  ma20=float(close.tail(20).mean()) if len(close)>=20 else None
  ma50=float(close.tail(50).mean()) if len(close)>=50 else None
  ma200=float(close.tail(200).mean()) if len(close)>=200 else None
  delta=close.diff()
  gains=delta.clip(lower=0).rolling(14).mean()
  losses=(-delta.clip(upper=0)).rolling(14).mean()
  rs=gains.iloc[-1]/losses.iloc[-1] if len(close)>=15 and losses.iloc[-1] not in (0,None) else None
  rsi=100-(100/(1+rs)) if rs is not None else (100 if len(close)>=15 and losses.iloc[-1]==0 else None)
  recent=h.tail(20)
  out.update({
   "ok":True,"price":num(last),"change_pct":num((last/prev-1)*100) if prev else None,
   "date":h.index[-1].strftime("%Y-%m-%d"),"volume":int(h["Volume"].iloc[-1]) if h["Volume"].iloc[-1]==h["Volume"].iloc[-1] else None,
   "sma20":num(ma20),"sma50":num(ma50),"sma200":num(ma200),"rsi14":num(rsi),
   "support20":num(recent["Low"].min()),"resistance20":num(recent["High"].max()),
   "market_cap":num(info.get("marketCap")),"pe":num(info.get("trailingPE")),"forward_pe":num(info.get("forwardPE")),
   "eps":num(info.get("trailingEps")),"roe_pct":num(info.get("returnOnEquity")*100) if info.get("returnOnEquity") is not None else None,
   "debt":num(info.get("totalDebt")),"revenue_growth_pct":num(info.get("revenueGrowth")*100) if info.get("revenueGrowth") is not None else None,
   "profit_margin_pct":num(info.get("profitMargins")*100) if info.get("profitMargins") is not None else None,
   "sector":info.get("sector") or "अज्ञात","industry":info.get("industry") or ""
  })
  if ma20 and ma50:
   out["trend"]="तेज़ी" if last>ma20>ma50 else ("मंदी" if last<ma20<ma50 else "मिला-जुला")
  else: out["trend"]="पर्याप्त इतिहास नहीं"
 except Exception as e:
  out["error"]=str(e)[:180]
 return out

now=dt.datetime.now(dt.timezone.utc).isoformat()
rows=[]
for i,(name,symbol) in enumerate(WATCHLIST.items()):
 rows.append(analyse(name,symbol))
 if i%5==4: time.sleep(1)
payload={"generated_at":now,"source_note":"मुफ़्त Yahoo Finance डेटा; विलंब संभव। खाली आँकड़े उपलब्ध नहीं थे—अनुमान नहीं। यह निवेश सलाह नहीं है।","companies":rows}
Path("sector-analysis.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
print("Wrote sector-analysis.json:",sum(1 for x in rows if x.get("ok")),"/",len(rows),"companies with price data")
