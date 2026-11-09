"""Daily diagnostic-only archive of NSE CM UDiFF Common Bhavcopy Final.

One official ZIP per NSE session. Keeps validated EQ-series cash equity rows
for later exact-constituent basket analysis. No per-symbol provider requests,
no production score mutation, and no score eligibility.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import time
import zipfile
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ARCHIVE_PATH = Path("nse_cm_bhavcopy_archive.json")
KEEP_SESSIONS = 260
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Trinetra-EOD-Research/1.0)",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/all-reports",
}
REQUIRED_COLUMNS = {
    "Sgmt", "Src", "FinInstrmTp", "TckrSymb", "SctySrs", "ISIN",
    "BizDt", "OpnPric", "HghPric", "LwPric", "ClsPric",
    "PrvsClsgPric", "TtlTradgVol",
}


def parse_date(value):
    value = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d%m%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid exchange date: {value!r}")


def finite_positive(value, field, allow_zero=False):
    raw = str(value if value is not None else "").strip().replace(",", "")
    try:
        number = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"invalid {field}: {raw!r}") from exc
    if not math.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"invalid {field}: {raw!r}")
    return number


def decode_cm_udiff_zip(payload):
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("empty NSE CM UDiFF download")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [name for name in archive.namelist()
                     if name.lower().endswith(".csv") and not name.startswith("__MACOSX/")]
            if len(names) != 1:
                raise ValueError("CM UDiFF ZIP must contain exactly one CSV")
            raw = archive.read(names[0])
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("NSE CM download is not a valid ZIP") from exc
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("NSE CM CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        missing = sorted(REQUIRED_COLUMNS - set(reader.fieldnames or []))
        raise ValueError("CM UDiFF CSV missing required columns: " + ", ".join(missing))
    return list(reader)


def normalize_equity_rows(rows, trade_date):
    target = parse_date(trade_date)
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed CM UDiFF row")
        segment = str(row.get("Sgmt") or "").strip().upper()
        source = str(row.get("Src") or "").strip().upper()
        instrument = str(row.get("FinInstrmTp") or "").strip().upper()
        series = str(row.get("SctySrs") or "").strip().upper()
        if segment != "CM" or source not in ("NSE", ""):
            continue
        # Cash-market equity security rows only; exclude ETFs, debt, SME,
        # indices and derivatives. EQ is the exchange's normal equity series.
        if instrument not in ("STK", "EQUITY", "") or series != "EQ":
            continue
        symbol = str(row.get("TckrSymb") or "").strip().upper()
        isin = str(row.get("ISIN") or "").strip().upper()
        if not symbol or not isin:
            raise ValueError("EQ cash row missing symbol or ISIN")
        if parse_date(row.get("BizDt")) != target:
            raise ValueError(f"CM trade date mismatch for {symbol}")
        key = (symbol, series)
        if key in seen:
            raise ValueError(f"duplicate EQ cash row: {symbol}")
        seen.add(key)
        opening = finite_positive(row.get("OpnPric"), "OpnPric")
        high = finite_positive(row.get("HghPric"), "HghPric")
        low = finite_positive(row.get("LwPric"), "LwPric")
        close = finite_positive(row.get("ClsPric"), "ClsPric")
        previous = finite_positive(row.get("PrvsClsgPric"), "PrvsClsgPric")
        volume = finite_positive(row.get("TtlTradgVol"), "TtlTradgVol", allow_zero=True)
        if low > min(opening, close) or high < max(opening, close) or high < low:
            raise ValueError(f"inconsistent OHLC for {symbol}")
        result.append({
            "symbol": symbol, "series": series, "isin": isin,
            "open": round(opening, 6), "high": round(high, 6),
            "low": round(low, 6), "close": round(close, 6),
            "previous_close": round(previous, 6),
            "volume": int(volume) if volume.is_integer() else volume,
        })
    if len(result) < 100:
        raise ValueError(f"implausibly small EQ cash universe: {len(result)} rows")
    return sorted(result, key=lambda item: item["symbol"])


def fetch_official_cm_bhavcopy(trade_date, session=None):
    day = parse_date(trade_date)
    stamp = day.strftime("%Y%m%d")
    filename = f"BhavCopy_NSE_CM_0_0_0_{stamp}_F_0000.csv.zip"
    urls = (
        f"https://archives.nseindia.com/content/cm/{filename}",
        f"https://nsearchives.nseindia.com/content/cm/{filename}",
    )
    client = session or requests.Session()
    failures = []
    for url in urls:
        try:
            response = client.get(url, headers=HEADERS, timeout=(10, 45))
            if response.status_code == 200 and response.content:
                return response.content, url
            failures.append(f"{url}: HTTP {response.status_code}")
        except requests.RequestException as exc:
            failures.append(f"{url}: {str(exc)[:160]}")
    raise RuntimeError("official NSE CM Bhavcopy unavailable: " + " | ".join(failures))


def append_session(archive, trade_date, source_url, payload, rows, fetched_at):
    day = parse_date(trade_date).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    records = archive.setdefault("records", [])
    existing = next((item for item in records if item.get("date") == day), None)
    if existing:
        if existing.get("sha256") == digest:
            return False
        raise ValueError(f"archive already contains a different CM file for {day}")
    records.append({
        "date": day,
        "source": "NSE CM-UDiFF Common Bhavcopy Final",
        "source_url": source_url,
        "sha256": digest,
        "fetched_at_utc": fetched_at,
        "equity_rows": rows,
        "equity_count": len(rows),
        "research_only": True,
        "included_in_asset_final": False,
    })
    records.sort(key=lambda item: item["date"])
    archive["records"] = records[-KEEP_SESSIONS:]
    archive["schema_version"] = 1
    archive["source"] = "NSE India official CM-UDiFF Common Bhavcopy Final"
    archive["retention_sessions"] = KEEP_SESSIONS
    archive["scope"] = "NSE EQ-series cash-market EOD OHLC, previous close, volume and ISIN"
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


def load_archive(path):
    if not path.exists():
        return {"schema_version": 1, "records": []}
    try:
        archive = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"existing NSE CM archive unreadable; refusing overwrite: {exc}") from exc
    if not isinstance(archive, dict) or not isinstance(archive.get("records"), list):
        raise RuntimeError("existing NSE CM archive structure invalid; refusing overwrite")
    return archive


def capture_one(archive, trade_date):
    key = parse_date(trade_date).isoformat()
    if any(isinstance(item, dict) and item.get("date") == key
           for item in archive.get("records", [])):
        return {"date": key, "status": "skipped_existing", "date_attempts": 0}
    payload, source_url = fetch_official_cm_bhavcopy(trade_date)
    rows = normalize_equity_rows(decode_cm_udiff_zip(payload), trade_date)
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    changed = append_session(archive, trade_date, source_url, payload, rows, fetched_at)
    return {
        "date": key, "status": "captured" if changed else "skipped_existing",
        "date_attempts": 1, "equity_count": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source": source_url, "research_only": True,
        "included_in_asset_final": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="One NSE session date YYYY-MM-DD; defaults to current IST date")
    parser.add_argument("--archive", default=str(ARCHIVE_PATH))
    args = parser.parse_args()
    path = Path(args.archive)
    archive = load_archive(path)
    trade_date = parse_date(args.date) if args.date else dt.datetime.now(IST).date()
    result = capture_one(archive, trade_date)
    if result["status"] == "captured":
        write_archive_atomic(path, archive)
    result["archive_sessions"] = len(archive.get("records", []))
    result["research_only"] = True
    result["included_in_asset_final"] = False
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
