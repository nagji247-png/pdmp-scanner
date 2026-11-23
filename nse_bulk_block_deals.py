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

def report_status_for_date(parsed_rows):
    # These NSE archive CSV URLs are not date-scoped. A valid header with zero
    # target-date rows cannot prove that the target date had no disclosed deals;
    # the file may simply still contain an older report. Fail closed.
    return "verified" if parsed_rows else "date_not_confirmed_no_rows"

def parse_historical_response(payload, kind):
    """Parse NSE's date-ranged historical API response; reject unknown schemas."""
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(kind + " historical API did not return valid JSON") from exc
    if isinstance(document, list):
        records = document
    elif isinstance(document, dict) and isinstance(document.get("data"), list):
        records = document["data"]
    else:
        raise ValueError(kind + " historical API response missing data list")
    parsed = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError(kind + " historical API contains a non-object row")
        raw_date = item.get("BD_DT_DATE") or item.get("date") or item.get("mTIMESTAMP")
        raw_symbol = item.get("BD_SYMBOL") or item.get("symbol")
        raw_client = item.get("BD_CLIENT_NAME") or item.get("clientName") or item.get("client")
        raw_side = item.get("BD_BUY_SELL") or item.get("buySell") or item.get("side")
        raw_qty = item.get("BD_QTY_TRD") or item.get("qty") or item.get("quantity")
        raw_price = item.get("BD_TP_WATP") or item.get("watp") or item.get("price")
        day = parse_day(raw_date)
        symbol = str(raw_symbol or "").strip().upper()
        client = str(raw_client or "").strip()
        side_text = str(raw_side or "").strip().upper()
        if not symbol or not client or not (side_text.startswith("B") or side_text.startswith("S")):
            raise ValueError(kind + " historical row missing symbol/client/side")
        parsed.append({
            "date": day.isoformat(), "kind": kind, "symbol": symbol,
            "client": client, "side": "SELL" if side_text.startswith("S") else "BUY",
            "quantity": parse_number(raw_qty, "quantity", True),
            "price": parse_number(raw_price, "trade price"),
        })
    return parsed


def fetch_historical_range(session, kind, start_date, end_date):
    option = "bulk_deals" if kind == "Bulk" else "block_deals"
    url = "https://www.nseindia.com/api/historicalOR/bulk-block-short-deals"
    params = {"optionType": option, "from": start_date.strftime("%d-%m-%Y"),
              "to": end_date.strftime("%d-%m-%Y")}
    response = session.get(url, params=params, headers={
        **HEADERS, "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.nseindia.com/report-detail/display-bulk-and-block-deals",
    }, timeout=(10, 45))
    if response.status_code != 200:
        raise RuntimeError(kind + " historical API HTTP " + str(response.status_code))
    parsed = parse_historical_response(response.content, kind)
    if any(not (start_date <= dt.date.fromisoformat(row["date"]) <= end_date) for row in parsed):
        raise ValueError(kind + " historical API returned rows outside requested date range")
    return parsed, response.url


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
    # NSE's historical endpoint is date-ranged. Warm the browser-like session first,
    # then fetch a single bounded range for both report types instead of assuming
    # today's bulk.csv/block.csv can reconstruct earlier sessions.
    try:
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=(10, 30))
    except requests.RequestException:
        pass
    path = Path(args.archive)
    archive = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema_version": 1, "records": []}
    # Backfill the latest 10 verified cash sessions, including the latest date.
    session_dates = sorted(set(dates))[-10:]
    start_date = session_dates[0]
    historical_by_kind, historical_sources, historical_status = {}, {}, {}
    for index, kind in enumerate(("Bulk", "Block")):
        if index: time.sleep(1.2)
        try:
            parsed, url = fetch_historical_range(session, kind, start_date, target)
            historical_by_kind[kind] = parsed
            historical_sources[kind] = url
            historical_status[kind] = "verified"
        except Exception as exc:
            historical_status[kind] = "unavailable: " + str(exc)

    # A successful date-ranged response with a valid data list verifies the
    # requested coverage, including a date with no rows. That is different from
    # an empty current-day CSV whose date scope is unknown.
    updated = []
    existing_by_date = {item.get("date"): item for item in archive.get("records", [])
                        if isinstance(item, dict) and item.get("date")}
    for day in session_dates:
        day_key = day.isoformat()
        previous_record = existing_by_date.get(day_key) or {}
        previous_status = previous_record.get("status") or {}
        previous_sources = previous_record.get("sources") or {}
        previous_rows = previous_record.get("rows") or []
        day_rows, day_status, day_sources = [], {}, {}
        for kind in ("Bulk", "Block"):
            if historical_status.get(kind) == "verified":
                day_rows.extend(row for row in historical_by_kind.get(kind, [])
                                if row["date"] == day_key)
                day_status[kind] = "verified"
                day_sources[kind] = historical_sources[kind]
            else:
                # A temporary failure for one report type must not erase an
                # already verified archive for that same type/date.
                day_rows.extend(row for row in previous_rows
                                if isinstance(row, dict) and row.get("kind") == kind)
                old_state = previous_status.get(kind)
                day_status[kind] = old_state if old_state == "verified" else historical_status.get(kind, "unavailable")
                if kind in previous_sources and old_state == "verified":
                    day_sources[kind] = previous_sources[kind]
        verified_count = sum(value == "verified" for value in day_status.values())
        if verified_count:
            updated.append({"date": day_key, "rows": day_rows, "status": day_status,
                            "sources": day_sources, "verified_report_count": verified_count,
                            "coverage_method": "NSE historicalOR date-range API",
                            "research_only": True, "included_in_asset_final": False})
    for record in updated:
        archive["records"] = [x for x in archive.get("records", [])
                              if x.get("date") != record["date"]]
        archive["records"].append(record)
    archive["records"] = sorted(archive.get("records", []), key=lambda x:x["date"])[-260:]
    print(json.dumps({
        "requested_sessions": [day.isoformat() for day in session_dates],
        "updated_sessions": [record["date"] for record in updated],
        "rows_by_date": {record["date"]: len(record["rows"]) for record in updated},
        "historical_status": historical_status,
        "warning": "A date is marked verified only for report types whose historical range request returned a valid data list."
    }, ensure_ascii=False))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    print(json.dumps({"date": target.isoformat(), "rows": sum(len(record["rows"]) for record in updated), "status": historical_status}, ensure_ascii=False))

if __name__ == "__main__": main()
