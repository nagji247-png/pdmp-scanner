"""Daily diagnostic-only archive of official MCX GOLD/SILVER FUTCOM Bhavcopy rows."""
from __future__ import annotations
import datetime as dt, json, math
from pathlib import Path
ARCHIVE_PATH=Path("mcx_bhavcopy_archive.json")
IST=dt.timezone(dt.timedelta(hours=5,minutes=30))
SOURCE="MCX India official date-wise Bhavcopy · FUTCOM"

def _date(v):
    if v in (None,""): return None
    s=str(v).strip()
    for f in ("%d %b %Y","%d %B %Y","%d/%m/%Y","%Y-%m-%d","%d-%b-%Y","%d-%b-%y","%d%b%Y"):
        try: return dt.datetime.strptime(s,f).date()
        except ValueError: pass
    return None

def filter_contract_rows(rows,trade_date):
    expected=dt.date.fromisoformat(str(trade_date))
    if not isinstance(rows,list): raise ValueError("Bhavcopy rows are not a list")
    kept=[]; seen=set(); symbols=set()
    for row in rows:
        if not isinstance(row,dict): continue
        sym=str(row.get("Symbol") or "").strip().upper()
        if str(row.get("InstrumentName") or "").strip().upper()!="FUTCOM" or sym not in {"GOLD","SILVER"}: continue
        actual=_date(row.get("DateDisplay") or row.get("Date"))
        if actual!=expected: raise ValueError(f"MCX row date mismatch for {sym}: {row.get('DateDisplay') or row.get('Date')!r}")
        expiry=_date(row.get("ExpiryDate")); opt=str(row.get("OptionType") or "-").strip()
        try: oi=float(row.get("OpenInterest"))
        except (TypeError,ValueError,OverflowError): oi=float("nan")
        try: close=float(row.get("Close"))
        except (TypeError,ValueError,OverflowError): close=float("nan")
        if expiry is None or not math.isfinite(oi) or oi<0 or not oi.is_integer() or not math.isfinite(close) or close<=0 or opt not in {"","-"}:
            raise ValueError(f"Malformed MCX FUTCOM row for {sym} on {trade_date}")
        key=(sym,expiry.isoformat())
        if key in seen: raise ValueError(f"Duplicate MCX contract row: {sym} {expiry.isoformat()}")
        seen.add(key); symbols.add(sym)
        kept.append({"InstrumentName":"FUTCOM","Symbol":sym,"DateDisplay":expected.strftime("%d %b %Y"),
                     "ExpiryDate":expiry.strftime("%d%b%Y").upper(),"OptionType":"-",
                     "OpenInterest":int(oi),"Close":round(close,6)})
    if symbols!={"GOLD","SILVER"}: raise ValueError("MCX Bhavcopy lacks required commodity rows: "+", ".join(sorted({"GOLD","SILVER"}-symbols)))
    if not kept: raise ValueError("No validated GOLD/SILVER FUTCOM contracts found")
    return sorted(kept,key=lambda x:(x["Symbol"],x["ExpiryDate"]))

def append_session(archive,trade_date,rows,captured_at_utc):
    archive=archive if isinstance(archive,dict) else {}
    records=archive.get("records") if isinstance(archive.get("records"),list) else []
    date=dt.date.fromisoformat(str(trade_date)).isoformat()
    if any(isinstance(x,dict) and x.get("date")==date for x in records): return archive,False
    clean_rows=filter_contract_rows(rows,date)
    record={"date":date,"captured_at_utc":captured_at_utc,"source":SOURCE,
            "scope":"All returned GOLD and SILVER FUTCOM expiry rows; exact date and expiry retained",
            "symbols":["GOLD","SILVER"],"contract_rows":clean_rows,"contract_count":len(clean_rows)}
    result={"schema_version":1,"source":SOURCE,"retention_sessions":260,
            "records":sorted((records+[record])[-260:],key=lambda x:x.get("date",""))}
    return result,True

def write_archive_atomic(path,archive):
    """Persist a complete JSON snapshot via same-directory replace."""
    target=Path(path)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(target.suffix+".tmp")
    payload=json.dumps(archive,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    try:
        with temporary.open("w",encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()

def main():
    from fetch_and_score import fetch_mcx_bhavcopy_rows
    now=dt.datetime.now(IST)
    if now.weekday()>=5:
        print("MCX_ARCHIVE_SKIP weekend; no request made"); return 0
    archive={"schema_version":1,"source":SOURCE,"retention_sessions":260,"records":[]}
    if ARCHIVE_PATH.exists():
        try: archive=json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc: raise RuntimeError(f"Existing archive unreadable; refusing overwrite: {exc}")
        if not isinstance(archive,dict) or not isinstance(archive.get("records"),list):
            raise RuntimeError("Existing MCX archive has invalid structure; refusing overwrite")
    date=now.date().isoformat()
    if any(isinstance(x,dict) and x.get("date")==date for x in archive.get("records",[])):
        print(f"MCX_ARCHIVE_SKIP already captured {date}; no request made"); return 0
    # Exactly one official MCX Bhavcopy request per scheduled weekday run.
    rows=fetch_mcx_bhavcopy_rows(date)
    updated,added=append_session(archive,date,rows,dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"))
    if not added: print(f"MCX_ARCHIVE_SKIP duplicate date {date}"); return 0
    write_archive_atomic(ARCHIVE_PATH,updated)
    record=updated["records"][-1]
    print(f"MCX_ARCHIVE_ADDED date={date} rows={record['contract_count']} GOLD={sum(x['Symbol']=='GOLD' for x in record['contract_rows'])} SILVER={sum(x['Symbol']=='SILVER' for x in record['contract_rows'])} requests=1 score_eligible=false")
    return 0
if __name__=="__main__": raise SystemExit(main())
