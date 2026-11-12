"""Daily diagnostic-only archive of official BSE CM UDiFF cash Bhavcopy.

One official BSE request per session. Stores BSE scrip code (FinInstrmId),
ISIN, symbol and same-session OHLC/previous close/volume. Research only.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ARCHIVE_PATH = Path("bse_cm_bhavcopy_archive.json")
KEEP_SESSIONS = 260
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Trinetra-EOD-Research/1.0)",
    "Accept": "text/csv,application/octet-stream,*/*",
    "Referer": "https://www.bseindia.com/",
}
REQUIRED_COLUMNS = {
    "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "TckrSymb", "SctySrs",
    "ISIN", "TradDt", "OpnPric", "HghPric", "LwPric", "ClsPric",
    "PrvsClsgPric", "TtlTradgVol",
}


def parse_date(value):
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d%m%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid BSE exchange date: {value!r}")


def finite_positive(value, field, allow_zero=False):
    raw = str(value if value is not None else "").strip().replace(",", "")
    try:
        number = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid {field}: {raw!r}") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"invalid {field}: {raw!r}")
    return number


def parse_bse_cm_csv(payload, trade_date, min_rows=500):
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("empty official BSE CM Bhavcopy")
    try:
        decoded = bytes(payload).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("BSE CM CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        raise ValueError("BSE CM UDiFF CSV missing columns: " + ", ".join(missing))
    target = parse_date(trade_date)
    result = []
    seen_ids = set()
    for row in reader:
        if str(row.get("Sgmt") or "").strip().upper() != "CM":
            continue
        if str(row.get("Src") or "").strip().upper() not in ("BSE", ""):
            continue
        if str(row.get("FinInstrmTp") or "").strip().upper() not in ("STK", "EQUITY", ""):
            continue
        instrument_id = str(row.get("FinInstrmId") or "").strip()
        symbol = str(row.get("TckrSymb") or "").strip().upper()
        isin = str(row.get("ISIN") or "").strip().upper()
        if not instrument_id or not instrument_id.isdigit() or not isin:
            raise ValueError("BSE cash row missing numeric scrip code or ISIN")
        if instrument_id in seen_ids:
            raise ValueError(f"duplicate BSE scrip code: {instrument_id}")
        seen_ids.add(instrument_id)
        if parse_date(row.get("TradDt")) != target:
            raise ValueError(f"BSE trade date mismatch for scrip {instrument_id}")
        business_date = str(row.get("BizDt") or "").strip()
        if business_date and parse_date(business_date) != target:
            raise ValueError(f"BSE business date mismatch for scrip {instrument_id}")
        opening = finite_positive(row.get("OpnPric"), "OpnPric")
        high = finite_positive(row.get("HghPric"), "HghPric")
        low = finite_positive(row.get("LwPric"), "LwPric")
        close = finite_positive(row.get("ClsPric"), "ClsPric")
        previous = finite_positive(row.get("PrvsClsgPric"), "PrvsClsgPric", allow_zero=True)
        volume = finite_positive(row.get("TtlTradgVol"), "TtlTradgVol", allow_zero=True)
        if low > min(opening, close) or high < max(opening, close) or high < low:
            raise ValueError(f"inconsistent BSE OHLC for scrip {instrument_id}")
        result.append({
            "instrument_id": instrument_id, "symbol": symbol,
            "isin": isin, "series": str(row.get("SctySrs") or "").strip().upper(),
            "open": round(opening, 6), "high": round(high, 6),
            "low": round(low, 6), "close": round(close, 6),
            "previous_close": round(previous, 6) if previous > 0 else None,
            "volume": int(volume) if volume.is_integer() else volume,
        })
    if len(result) < min_rows:
        raise ValueError(f"implausibly small BSE CM cash universe: {len(result)} rows")
    return sorted(result, key=lambda item: item["instrument_id"])


def fetch_official_bse_cm_bhavcopy(trade_date, session=None):
    day = parse_date(trade_date)
    filename = f"BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv"
    url = f"https://www.bseindia.com/download/BhavCopy/Equity/{filename}"
    client = session or requests.Session()
    # Exactly one request per date; no retry or mirror fallback.
    response = client.get(url, headers=HEADERS, timeout=(10, 45))
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"official BSE CM Bhavcopy unavailable: HTTP {response.status_code}")
    return response.content, url


def load_archive(path):
    target = Path(path)
    if not target.exists():
        return {"schema_version": 1, "records": []}
    try:
        archive = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"existing BSE archive unreadable; refusing overwrite: {exc}") from exc
    if not isinstance(archive, dict) or not isinstance(archive.get("records"), list):
        raise RuntimeError("existing BSE archive structure invalid; refusing overwrite")
    return archive


def append_session(archive, trade_date, source_url, payload, rows, fetched_at):
    day = parse_date(trade_date).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    records = archive.setdefault("records", [])
    existing = next((item for item in records if item.get("date") == day), None)
    if existing:
        if existing.get("sha256") == digest:
            return False
        raise ValueError(f"BSE archive already contains a different file for {day}")
    records.append({
        "date": day, "source": "BSE CM UDiFF Common Bhavcopy Final",
        "source_url": source_url, "sha256": digest,
        "fetched_at_utc": fetched_at, "equity_rows": rows,
        "equity_count": len(rows), "research_only": True,
        "included_in_asset_final": False,
    })
    records.sort(key=lambda item: item["date"])
    archive["records"] = records[-KEEP_SESSIONS:]
    archive["schema_version"] = 1
    archive["source"] = "BSE official CM UDiFF Common Bhavcopy Final"
    archive["retention_sessions"] = KEEP_SESSIONS
    archive["scope"] = "BSE cash-market scrip code, ISIN, OHLC, previous close and volume"
    archive["research_only"] = True
    archive["included_in_asset_final"] = False
    return True


def write_archive_atomic(path, archive):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    payload = json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def capture_one(archive, trade_date):
    key = parse_date(trade_date).isoformat()
    if any(isinstance(item, dict) and item.get("date") == key
           for item in archive.get("records", [])):
        return {"date": key, "status": "skipped_existing", "date_attempts": 0}
    payload, source_url = fetch_official_bse_cm_bhavcopy(trade_date)
    rows = parse_bse_cm_csv(payload, trade_date)
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    changed = append_session(archive, trade_date, source_url, payload, rows, fetched_at)
    return {
        "date": key, "status": "captured" if changed else "skipped_existing",
        "date_attempts": 1, "equity_count": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(), "source": source_url,
        "research_only": True, "included_in_asset_final": False,
    }


def is_exchange_session(trade_date, calendar):
    day = parse_date(trade_date)
    key = day.isoformat()
    if not isinstance(calendar, dict):
        return day.weekday() < 5
    if key in calendar.get("special_sessions", {}):
        return True
    holidays = {str(item.get("date")) for item in calendar.get("holidays", [])
                if isinstance(item, dict) and item.get("date")}
    return day.weekday() < 5 and key not in holidays


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="One BSE session date YYYY-MM-DD; defaults to a rolling recent window")
    parser.add_argument("--backfill-days", type=int, default=7,
                        help="Retry every missing exchange session in this many calendar days")
    parser.add_argument("--archive", default=str(ARCHIVE_PATH))
    parser.add_argument("--calendar", default="exchange_calendar.json")
    args = parser.parse_args()
    if args.backfill_days < 1 or args.backfill_days > 31:
        parser.error("--backfill-days must be between 1 and 31")
    path = Path(args.archive)
    archive = load_archive(path)
    calendar_path = Path(args.calendar)
    calendar = json.loads(calendar_path.read_text(encoding="utf-8")) if calendar_path.exists() else None
    if args.date:
        dates = [parse_date(args.date)]
    else:
        today = dt.datetime.now(IST).date()
        dates = [today - dt.timedelta(days=offset)
                 for offset in range(args.backfill_days - 1, -1, -1)]
    results = []
    changed = False
    for trade_date in dates:
        if not is_exchange_session(trade_date, calendar):
            results.append({"date": trade_date.isoformat(), "status": "skipped_non_session",
                            "date_attempts": 0})
            continue
        try:
            result = capture_one(archive, trade_date)
            changed = changed or result.get("status") == "captured"
        except Exception as exc:
            result = {"date": trade_date.isoformat(), "status": "unavailable",
                      "error": str(exc), "date_attempts": 1}
        results.append(result)
    if changed:
        write_archive_atomic(path, archive)
    print(json.dumps({
        "results": results, "archive_sessions": len(archive.get("records", [])),
        "captured": sum(item.get("status") == "captured" for item in results),
        "unavailable": sum(item.get("status") == "unavailable" for item in results),
        "research_only": True, "included_in_asset_final": False,
    }, ensure_ascii=False, sort_keys=True))
    return 1 if any(item.get("status") == "unavailable" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
