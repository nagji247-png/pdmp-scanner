#!/usr/bin/env python3
"""Fetch NSDL fortnightly FPI equity sector flows; never touches daily PDMP data."""
import datetime as dt, html, json, re, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

OUT=Path("fpi-sector-data.json")
MONTHS=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
SKIP={"Sovereign","Others","Grand Total","Total"}
EQUITY_NET_INR_COLUMN=50

class Rows(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr": self.row=[]
        elif tag in ("td","th") and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split())); self.cell=None
        elif tag=="tr" and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row=None

def candidates(today):
    out=[]; month=today.replace(day=1)
    while len(out)<18:
        last=(month.replace(day=28)+dt.timedelta(days=4)).replace(day=1)-dt.timedelta(days=1)
        for day in (last.day,15):
            d=month.replace(day=day)
            if d<=today and d not in out: out.append(d)
        month=(month-dt.timedelta(days=1)).replace(day=1)
    return sorted(out,reverse=True)

def number(v):
    v=html.unescape(str(v)).replace(",","").replace("₹","").strip()
    if v in ("","-","—","–"): return None
    try: return float(v)
    except ValueError: return None

def fetch_period(end):
    mon=MONTHS[end.month-1]
    url=f"https://pilot.fpi.nsdl.co.in/StaticReports/Fortnightly_Sector_wise_FII_Investment_Data/FIIInvestSector_{mon}{end.day:02d}{end.year}.html"
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 TRINETRA research dashboard"})
    with urlopen(req,timeout=25) as response: raw=response.read().decode("utf-8",errors="replace")
    parser=Rows(); parser.feed(raw); sectors=[]
    grand_total=None
    excluded_flows={}
    for row in parser.rows:
        if len(row)<=EQUITY_NET_INR_COLUMN:
            continue
        name=html.unescape(row[1]).strip() if len(row)>1 else ""
        flow=number(row[EQUITY_NET_INR_COLUMN])
        if name=="Grand Total":
            grand_total=flow
            continue
        if name in ("Sovereign","Others"):
            excluded_flows[name]=flow or 0
            continue
        if not name or name in SKIP or not re.fullmatch(r"\\d+",row[0].strip()):
            continue
        if flow is not None:
            sectors.append({"name":name,"net_equity_cr":round(flow,2)})
    if len(sectors)<18:
        raise ValueError(f"only {len(sectors)} valid industry rows")
    if grand_total is None:
        raise ValueError("NSDL Grand Total equity cell is missing")
    reconstructed=round(sum(x["net_equity_cr"] for x in sectors)+sum(excluded_flows.values()),2)
    if abs(reconstructed-grand_total)>2:
        raise ValueError(f"Equity column validation failed: sector sum {reconstructed} vs NSDL Grand Total {grand_total}")
    start=end.replace(day=1) if end.day==15 else end.replace(day=16)
    return {"end_date":end.isoformat(),"from_date":start.isoformat(),"to_date":end.isoformat(),
      "label":f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}",
      "net_equity_total_cr":round(sum(x["net_equity_cr"] for x in sectors),2),
      "sectors":sorted(sectors,key=lambda x:x["name"].casefold()),"source_url":url}

def main():
    today=dt.datetime.now(dt.timezone.utc).date()
    old={}
    if OUT.exists():
        try: old=json.loads(OUT.read_text(encoding="utf-8"))
        except Exception: pass
    old_latest=(old.get("history") or [{}])[0].get("end_date")
    history=[]
    for end in candidates(today):
        try:
            period=fetch_period(end); history.append(period)
            print(f"{end}: {len(period['sectors'])} sectors")
            if len(history)==6: break
        except Exception as exc: print(f"{end}: unavailable: {str(exc)[:120]}")
        time.sleep(.25)
    if not history: raise SystemExit("No valid NSDL report; refusing to replace published data")
    if old_latest and history[0]["end_date"]<old_latest:
        raise SystemExit("Fetched data is older than published data; refusing downgrade")
    payload={"updated_at":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
      "source":"NSDL Fortnightly Sector-wise FII Investment Data · Equity net investment",
      "source_url":history[0]["source_url"],"unit":"INR crore","history":history,
      "note":"केवल उद्योग सेक्टरों का Equity net investment; Debt, Hybrid, AUC, Sovereign और Others शामिल नहीं। यह अलग संदर्भ है, PDMP Final Score का हिस्सा नहीं।"}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Saved {len(history)} fortnights; latest {history[0]['end_date']}")

if __name__=="__main__": main()
