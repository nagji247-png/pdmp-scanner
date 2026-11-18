"""Capture disclosed NSE bulk and block deals from official current CSV reports."""
from __future__ import annotations
import argparse, csv, datetime as dt, io, json, math, time
from pathlib import Path
import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BASE = "https://nsearchives.nseindia.com/content/equities/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
           "Accept": "text/csv,*/*", "Referer": "https://www.nseindia.com/all-reports"}

def parse_day(value):
    raw = str(value or "").strip().replace("T", " ").split(" ")[0]
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%y"):
        try: return dt.datetime.strptime(raw.title(), fmt).date()
        except ValueError: pass
    raise ValueError("invalid deal date: " + raw)

def parse_number(value, field, integer_only=False):
    raw = str(value or "").strip().replace(",", "")
    try: number = float(raw)
    except (TypeError, ValueError, OverflowError): raise ValueError("invalid " + field)
    if not math.isfinite(number) or number <= 0 or (integer_only and not number.is_integer()):
        raise ValueError("invalid " + field)
    return int(number) if integer_only else number

def parse_deal_csv(payload, kind, target_date):
    if not payload: raise ValueError(kind + " deal CSV is empty")
    try: decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError: raise ValueError(kind + " deal CSV is not UTF-8")
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames: raise ValueError(kind + " deal CSV missing header")
    headers = [h.strip().lower() for h in reader.fieldnames]
    def col(*prefixes):
        for p in prefixes:
            for h in headers:
                if h.startswith(p): return h
        return None
    date_col = col("date")
    symbol_col = col("symbol")
    client_col = col("client")
    side_col = col("buy/sell", "buy sell", "buy")
    qty_col = col("quantity")
    price_col = col("trade price", "price")
    required = [date_col, symbol_col, client_col, side_col, qty_col, price_col]
    if any(x is None for x in required): raise ValueError(kind + " deal CSV missing required columns")
    out = []
    for raw in reader:
        row = {str(k).strip().lower(): str(v or "").strip() for k,v in raw.items() if k is not None}
        try: day = parse_day(row.get(date_col))
        except ValueError: continue
        if day != target_date: continue
        symbol = row.get(symbol_col, "").upper()
        client = row.get(client_col, "").strip()
        side_raw = row.get(side_col, "").upper()
        if not symbol or not client or not (side_raw.startswith("B") or side_raw.startswith("S")):
            raise ValueError(kind + " deal row missing symbol/client/side")
        out.append({"date": day.isoformat(), "kind": kind, "symbol": symbol,
                    "client": client, "side": "SELL" if side_raw.startswith("S") else "BUY",
                    "quantity": parse_number(row.get(qty_col), "quantity", True),
                    "price": parse_number(row.get(price_col), "trade price")})
    return out

def fetch_file(session, kind):
    filename = "bulk.csv" if kind == "Bulk" else "block.csv"
    response = session.get(BASE + filename, headers=HEADERS, timeout=(10, 45))
    if response.status_code != 200: raise RuntimeError(kind + " deal report HTTP " + str(response.status_code))
    return response.content, BASE + filename

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cm-archive", default="nse_cm_bhavcopy_archive.json")
    parser.add_argument("--archive", default="nse_bulk_block_deals.json")
    args = parser.parse_args()
    cm = json.loads(Path(args.cm_archive).read_text(encoding="utf-8"))
    dates = [parse_day(x["date"]) for x in cm.get("records", []) if isinstance(x, dict) and x.get("date")]
    if not dates: raise RuntimeError("no verified NSE CM session for deal date")
    target = max(dates)
    session = requests.Session()
    rows, sources, status = [], {}, {}
    for index, kind in enumerate(("Bulk", "Block")):
        if index: time.sleep(1.2)
        try:
            payload, url = fetch_file(session, kind)
            parsed = parse_deal_csv(payload, kind, target)
            rows.extend(parsed); sources[kind] = url; status[kind] = "verified"
        except Exception as exc:
            status[kind] = "unavailable: " + str(exc)
    if not any(value == "verified" for value in status.values()):
        raise RuntimeError("both NSE deal reports unavailable")
    path = Path(args.archive)
    archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "records": []}
    record = {"date": target.isoformat(), "rows": rows, "status": status, "sources": sources,
              "verified_report_count": sum(v == "verified" for v in status.values()),
              "research_only": True, "included_in_asset_final": False}
    archive["records"] = [x for x in archive.get("records", []) if x.get("date") != target.isoformat()]
    archive["records"].append(record)
    archive["records"] = sorted(archive["records"], key=lambda x:x["date"])[-260:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\\n", encoding="utf-8")
    tmp.replace(path)
    print(json.dumps({"date": target.isoformat(), "rows": len(rows), "status": status}, ensure_ascii=False))

if __name__ == "__main__": main()
