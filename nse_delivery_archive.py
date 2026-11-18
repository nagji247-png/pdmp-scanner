"""Archive official NSE full cash bhavcopy with security-wise delivery fields."""
from __future__ import annotations
import argparse, csv, datetime as dt, io, json, math
from pathlib import Path
import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{stamp}.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/all-reports",
}
REQUIRED = {"SYMBOL", "SERIES", "DATE1", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"}

def parse_day(value):
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d%m%Y"):
        try: return dt.datetime.strptime(str(value).strip(), fmt).date()
        except ValueError: pass
    raise ValueError("invalid NSE delivery date")

def number(value, field, allow_dash=False):
    raw = str(value if value is not None else "").strip().replace(",", "")
    if allow_dash and raw in ("", "-"): return None
    try: x = float(raw)
    except (TypeError, ValueError, OverflowError): raise ValueError("invalid " + field)
    if not math.isfinite(x) or x < 0: raise ValueError("invalid " + field)
    return x

def parse_delivery_csv(payload, trade_date, min_rows=100):
    if not isinstance(payload, (bytes, bytearray)) or not payload: raise ValueError("empty NSE full bhavcopy")
    try: decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError: raise ValueError("NSE full bhavcopy is not UTF-8")
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames: raise ValueError("NSE full bhavcopy missing header")
    reader.fieldnames = [x.strip().upper() for x in reader.fieldnames]
    if not REQUIRED.issubset(set(reader.fieldnames)):
        raise ValueError("NSE full bhavcopy missing required delivery columns")
    target = parse_day(trade_date)
    out, seen = {}, set()
    for raw in reader:
        row = {str(k).strip().upper(): str(v or "").strip() for k,v in raw.items() if k is not None}
        if row.get("SERIES", "").upper() != "EQ": continue
        symbol = row.get("SYMBOL", "").upper()
        if not symbol: raise ValueError("EQ delivery row missing symbol")
        if parse_day(row.get("DATE1")) != target: raise ValueError("NSE delivery date mismatch for " + symbol)
        if symbol in seen: raise ValueError("duplicate NSE EQ delivery row: " + symbol)
        seen.add(symbol)
        traded = number(row.get("TTL_TRD_QNTY"), "TTL_TRD_QNTY")
        qty = number(row.get("DELIV_QTY"), "DELIV_QTY", allow_dash=True)
        pct = number(row.get("DELIV_PER"), "DELIV_PER", allow_dash=True)
        if traded is None or traded <= 0:
            raise ValueError("invalid traded quantity for " + symbol)
        if qty is not None and qty > traded: raise ValueError("delivery quantity exceeds traded quantity for " + symbol)
        if pct is not None and pct > 100: raise ValueError("delivery percentage exceeds 100 for " + symbol)
        if qty is not None and pct is not None:
            calculated = qty / traded * 100
            if abs(calculated - pct) > 0.15: raise ValueError("delivery percentage consistency failure for " + symbol)
        out[symbol] = {"delivery_qty": int(qty) if qty is not None and qty.is_integer() else qty,
                       "delivery_pct": round(pct, 2) if pct is not None else None,
                       "traded_qty": int(traded) if traded.is_integer() else traded,
                       "series": "EQ"}
    if len(out) < min_rows: raise ValueError("implausibly small NSE EQ delivery universe: " + str(len(out)))
    return out

def fetch_delivery(trade_date, session=None):
    day = parse_day(trade_date)
    url = URL.format(stamp=day.strftime("%d%m%Y"))
    client = session or requests.Session()
    response = client.get(url, headers=HEADERS, timeout=(10, 45))
    if response.status_code != 200 or not response.content:
        raise RuntimeError("official NSE full bhavcopy unavailable: HTTP " + str(response.status_code))
    return response.content, url

def build_archive_record(trade_date, payload, source_url):
    day = parse_day(trade_date)
    rows = parse_delivery_csv(payload, day)
    return {"date": day.isoformat(), "source": "NSE official Full Bhavcopy and Security Deliverable data",
            "source_url": source_url, "rows": rows, "symbol_count": len(rows),
            "research_only": True, "included_in_asset_final": False}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--archive", default="nse_delivery_archive.json")
    args = parser.parse_args()
    day = parse_day(args.date) if args.date else dt.datetime.now(IST).date() - dt.timedelta(days=1)
    path = Path(args.archive)
    archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "records": []}
    payload, url = fetch_delivery(day)
    record = build_archive_record(day, payload, url)
    existing = next((x for x in archive["records"] if x.get("date") == record["date"]), None)
    if existing and existing.get("rows") == record["rows"]:
        print(json.dumps({"date": record["date"], "status": "unchanged", "symbols": record["symbol_count"]}))
        return
    if existing: archive["records"].remove(existing)
    archive["records"].append(record)
    archive["records"] = sorted(archive["records"], key=lambda x:x["date"])[-260:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\\n", encoding="utf-8")
    tmp.replace(path)
    print(json.dumps({"date": record["date"], "status": "captured", "symbols": record["symbol_count"]}))

if __name__ == "__main__": main()
