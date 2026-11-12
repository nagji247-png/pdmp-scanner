"""Daily diagnostic-only archive of official MCX GOLD/SILVER FUTCOM Bhavcopy rows."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, math, time
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
            "normalized_rows_sha256":hashlib.sha256(json.dumps(clean_rows,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest(),
            "hash_scope":"SHA-256 of canonical filtered contract rows; raw HTTP response bytes are not exposed by the current fetch helper",
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
    payload=json.dumps(archive,ensure_ascii=False,indent=2,allow_nan=False)+chr(10)
    try:
        with temporary.open("w",encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()

def load_archive(path):
    if path.exists():
        try: archive=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc: raise RuntimeError(f"Existing archive unreadable; refusing overwrite: {exc}")
        if not isinstance(archive,dict) or not isinstance(archive.get("records"),list):
            raise RuntimeError("Existing MCX archive has invalid structure; refusing overwrite")
        return archive
    return {"schema_version":1,"source":SOURCE,"retention_sessions":260,"records":[]}

def default_trade_date(now=None):
    """Return the latest completed MCX EOD trade date, even after a delayed overnight run.

    The scheduled archive runs after the 22:45 IST publication window. If GitHub
    starts that run after midnight, the target remains the previous calendar
    trading day rather than silently switching to today's not-yet-published file.
    """
    current = now or dt.datetime.now(IST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=IST)
    else:
        current = current.astimezone(IST)
    target = current.date()
    if current.time() < dt.time(22, 45):
        target -= dt.timedelta(days=1)
    while target.weekday() >= 5:
        target -= dt.timedelta(days=1)
    return target

def capture_one(archive,date,fetch_rows):
    key=dt.date.fromisoformat(str(date)).isoformat()
    if any(isinstance(x,dict) and x.get("date")==key for x in archive.get("records",[])):
        return {"date":key,"status":"skipped_existing","date_attempts":0}
    rows=fetch_rows(key)
    updated,added=append_session(archive,key,rows,dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"))
    if not added: return {"date":key,"status":"skipped_existing","date_attempts":1}
    archive.clear(); archive.update(updated)
    record=next(item for item in updated["records"] if item.get("date")==key)
    return {"date":key,"status":"captured","date_attempts":1,
            "contract_rows":record["contract_count"],"normalized_rows_sha256":record["normalized_rows_sha256"],
            "score_eligible":False}

def main():
    from fetch_and_score import fetch_mcx_bhavcopy_rows
    parser=argparse.ArgumentParser()
    parser.add_argument("--date",help="One MCX trade date YYYY-MM-DD; defaults to current IST date")
    parser.add_argument("--from-date",help="Start date for bounded historical backfill")
    parser.add_argument("--to-date",help="End date for bounded historical backfill")
    parser.add_argument("--max-sessions",type=int,default=5,help="Maximum weekday dates attempted per run (hard cap 5)")
    parser.add_argument("--delay-seconds",type=float,default=2.0,help="Minimum pause between dates (minimum 2 seconds)")
    parser.add_argument("--archive",default=str(ARCHIVE_PATH))
    args=parser.parse_args()
    if args.date and (args.from_date or args.to_date): parser.error("--date cannot be combined with a date range")
    if bool(args.from_date)!=bool(args.to_date): parser.error("--from-date and --to-date must be supplied together")
    path=Path(args.archive); archive=load_archive(path)
    if args.from_date:
        start,end=dt.date.fromisoformat(args.from_date),dt.date.fromisoformat(args.to_date)
        if end<start: parser.error("--to-date must be on or after --from-date")
        if not 1<=args.max_sessions<=5: parser.error("--max-sessions must be between 1 and the hard cap of 5")
        if not math.isfinite(args.delay_seconds) or args.delay_seconds<2: parser.error("--delay-seconds must be at least 2")
        dates=[]; day=start
        while day<=end:
            if day.weekday()<5: dates.append(day)
            day+=dt.timedelta(days=1)
        dates=dates[:args.max_sessions]; results=[]
        for index,day in enumerate(dates):
            try: results.append(capture_one(archive,day.isoformat(),fetch_mcx_bhavcopy_rows))
            except Exception as exc: results.append({"date":day.isoformat(),"status":"unavailable_or_invalid","error":str(exc)[:240]})
            if index+1<len(dates): time.sleep(args.delay_seconds)
        if any(x.get("status")=="captured" for x in results): write_archive_atomic(path,archive)
        print(json.dumps({"mode":"bounded_historical_backfill","attempted_dates":len(dates),
                          "max_date_attempts":args.max_sessions,"delay_seconds":args.delay_seconds,
                          "results":results,"archive_sessions":len(archive.get("records",[])),
                          "research_only":True,"included_in_asset_final":False},sort_keys=True))
        return 0
    date=args.date or default_trade_date().isoformat()
    day=dt.date.fromisoformat(date)
    if day.weekday()>=5:
        print("MCX_ARCHIVE_SKIP weekend; no request made"); return 0
    result=capture_one(archive,date,fetch_mcx_bhavcopy_rows)
    if result["status"]=="captured": write_archive_atomic(path,archive)
    result.update({"archive_sessions":len(archive.get("records",[])),"research_only":True,"included_in_asset_final":False})
    print(json.dumps(result,sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
