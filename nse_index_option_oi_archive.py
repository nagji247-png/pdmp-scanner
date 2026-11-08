"""Archive daily NSE NIFTY/BANKNIFTY index-option OI from official FO UDiFF Bhavcopy.

Research archive only. It does not generate a directional signal or alter
production data.json. SENSEX options are not NSE contracts and are excluded.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ARCHIVE_PATH = Path("nse_index_option_oi.json")
SYMBOLS = ("NIFTY", "BANKNIFTY")
KEEP_SESSIONS = 260
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PDMP-Research-Archive/1.0)",
    "Accept": "application/zip,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/all-reports-derivatives",
}


def parse_date(value):
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d%m%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid exchange date: {text!r}")


def integer(value, field):
    text = str(value if value is not None else "").strip().replace(",", "")
    if not text:
        raise ValueError(f"missing {field}")
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"invalid {field}: {text!r}")
    if not math.isfinite(number) or not number.is_integer():
        raise ValueError(f"invalid integer {field}: {text!r}")
    return int(number)


def positive_number(value, field):
    text = str(value if value is not None else "").strip().replace(",", "")
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"invalid {field}: {text!r}")
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"invalid {field}: {text!r}")
    return number


def aggregate_udiff_rows(rows, trade_date):
    """Aggregate contract OI by exact symbol, expiry and option side.

    Duplicate symbol/expiry/side/strike rows and malformed matching rows block
    the capture. Both CE and PE must be present for each tracked index.
    """
    target_date = parse_date(trade_date)
    totals = {
        symbol: {} for symbol in SYMBOLS
    }
    seen = set()
    matched = {symbol: 0 for symbol in SYMBOLS}

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed UDiFF row")
        instrument_type = str(row.get("FinInstrmTp") or "").strip().upper()
        if instrument_type != "IDO":
            continue
        symbol = str(row.get("TckrSymb") or "").strip().upper()
        if symbol not in SYMBOLS:
            continue
        if "Sgmt" in row and str(row.get("Sgmt") or "").strip().upper() not in ("", "FO"):
            raise ValueError(f"unexpected segment for {symbol}")
        if "Src" in row and str(row.get("Src") or "").strip().upper() not in ("", "NSE"):
            raise ValueError(f"unexpected source for {symbol}")
        if parse_date(row.get("BizDt")) != target_date:
            raise ValueError(f"trade date mismatch for {symbol}")
        side = str(row.get("OptnTp") or "").strip().upper()
        if side not in ("CE", "PE"):
            raise ValueError(f"invalid option side for {symbol}: {side!r}")
        expiry = parse_date(row.get("XpryDt"))
        if expiry < target_date:
            raise ValueError(f"expired contract in {symbol} bhavcopy")
        strike = positive_number(row.get("StrkPric"), "StrkPric")
        oi = integer(row.get("OpnIntrst"), "OpnIntrst")
        change = integer(row.get("ChngInOpnIntrst"), "ChngInOpnIntrst")
        if oi < 0:
            raise ValueError("negative open interest")
        key = (symbol, expiry.isoformat(), side, strike)
        if key in seen:
            raise ValueError(f"duplicate option contract row: {key}")
        seen.add(key)

        bucket = totals[symbol].setdefault(expiry.isoformat(), {
            "CE": {"open_interest": 0, "change_in_oi": 0, "contracts": 0},
            "PE": {"open_interest": 0, "change_in_oi": 0, "contracts": 0},
        })
        bucket[side]["open_interest"] += oi
        bucket[side]["change_in_oi"] += change
        bucket[side]["contracts"] += 1
        matched[symbol] += 1

    output = {}
    for symbol in SYMBOLS:
        expiries = totals[symbol]
        if not expiries:
            raise ValueError(f"no IDO contracts found for {symbol}")
        for expiry, sides in expiries.items():
            if not sides["CE"]["contracts"] or not sides["PE"]["contracts"]:
                raise ValueError(f"missing CE or PE side for {symbol} {expiry}")
        output[symbol] = {
            "expiry_count": len(expiries),
            "contract_rows": matched[symbol],
            "by_expiry": {
                expiry: sides for expiry, sides in sorted(expiries.items())
            },
            "coverage_validated": False,
            "included_in_asset_final": False,
        }
    return output


def decode_udiff_zip(payload):
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_names = [name for name in archive.namelist()
                         if name.lower().endswith(".csv") and not name.startswith("__MACOSX/")]
            if len(csv_names) != 1:
                raise ValueError("UDiFF ZIP must contain exactly one CSV")
            raw = archive.read(csv_names[0])
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("official UDiFF download is not a valid ZIP") from exc
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("UDiFF CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    required = {"FinInstrmTp", "TckrSymb", "BizDt", "XpryDt",
                "OptnTp", "StrkPric", "OpnIntrst", "ChngInOpnIntrst"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError("UDiFF CSV is missing required index-option columns")
    return list(reader)


def fetch_official_bhavcopy(trade_date, session=None):
    day = parse_date(trade_date)
    stamp = day.strftime("%Y%m%d")
    filename = f"BhavCopy_NSE_FO_0_0_0_{stamp}_F_0000.csv.zip"
    urls = (
        f"https://archives.nseindia.com/content/fo/{filename}",
        f"https://nsearchives.nseindia.com/content/fo/{filename}",
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
    raise RuntimeError("official NSE UDiFF Bhavcopy unavailable: " + " | ".join(failures))


def append_archive(archive, trade_date, source_url, payload, symbols, fetched_at):
    day = parse_date(trade_date).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    records = archive.setdefault("records", [])
    existing = next((item for item in records if item.get("date") == day), None)
    if existing:
        if existing.get("sha256") == digest:
            return False
        raise ValueError(f"archive already contains a different file for {day}")
    records.append({
        "date": day,
        "source": "NSE F&O UDiFF Common Bhavcopy Final",
        "source_url": source_url,
        "sha256": digest,
        "fetched_at": fetched_at,
        "symbols": symbols,
    })
    records.sort(key=lambda item: item["date"])
    archive["records"] = records[-KEEP_SESSIONS:]
    archive["schema_version"] = 1
    archive["source"] = "NSE India official F&O UDiFF Common Bhavcopy Final"
    archive["symbols"] = list(SYMBOLS)
    archive["scope"] = "NIFTY and BANKNIFTY index options; CE/PE OI by expiry"
    archive["research_only"] = True
    archive["included_in_asset_final"] = False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="NSE trade date YYYY-MM-DD; defaults to current IST date")
    parser.add_argument("--archive", default=str(ARCHIVE_PATH))
    args = parser.parse_args()
    trade_date = parse_date(args.date) if args.date else dt.datetime.now(IST).date()
    payload, source_url = fetch_official_bhavcopy(trade_date)
    rows = decode_udiff_zip(payload)
    symbols = aggregate_udiff_rows(rows, trade_date)
    path = Path(args.archive)
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            archive = json.load(handle)
        if not isinstance(archive, dict) or not isinstance(archive.get("records", []), list):
            raise SystemExit("existing NSE OI archive has invalid structure")
    else:
        archive = {"schema_version": 1, "records": []}
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    changed = append_archive(archive, trade_date, source_url, payload, symbols, fetched_at)
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(archive, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        temp.replace(path)
    print(json.dumps({
        "trade_date": trade_date.isoformat(),
        "archive_updated": changed,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "symbols": {
            symbol: {
                "expiry_count": value["expiry_count"],
                "contract_rows": value["contract_rows"],
                "coverage_validated": value["coverage_validated"],
                "included_in_asset_final": value["included_in_asset_final"],
            } for symbol, value in symbols.items()
        },
        "archive_sessions": len(archive.get("records", [])),
        "source": source_url,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
