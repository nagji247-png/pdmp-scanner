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
import time
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


def aggregate_option_contracts(rows, trade_date):
    """Retain per-contract premium/OI for the nearest two expiries per index.

    Keeping two expiries allows a same-contract comparison across weekly expiry
    rolls. No strike/side is matched to a different contract.
    """
    target_date = parse_date(trade_date)
    collected = {symbol: [] for symbol in SYMBOLS}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("malformed UDiFF row")
        if str(row.get("FinInstrmTp") or "").strip().upper() != "IDO":
            continue
        symbol = str(row.get("TckrSymb") or "").strip().upper()
        if symbol not in SYMBOLS:
            continue
        if str(row.get("Sgmt") or "").strip().upper() not in ("", "FO"):
            raise ValueError(f"unexpected segment for {symbol}")
        if str(row.get("Src") or "").strip().upper() not in ("", "NSE"):
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
        close = positive_number(row.get("ClsPric"), "ClsPric")
        oi = integer(row.get("OpnIntrst"), "OpnIntrst")
        if oi < 0:
            raise ValueError("negative open interest")
        collected[symbol].append({
            "expiry": expiry.isoformat(),
            "side": side,
            "strike": round(strike, 4),
            "close": round(close, 6),
            "open_interest": oi,
        })

    result = {}
    for symbol, contracts in collected.items():
        expiries = sorted({item["expiry"] for item in contracts})
        if len(expiries) < 2:
            raise ValueError(f"fewer than two option expiries for {symbol}")
        selected = set(expiries[:2])
        retained = [
            item for item in contracts if item["expiry"] in selected
        ]
        keys = [
            (item["expiry"], item["side"], item["strike"])
            for item in retained
        ]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate retained option contract for {symbol}")
        if not any(item["side"] == "CE" for item in retained) or not any(
            item["side"] == "PE" for item in retained
        ):
            raise ValueError(f"missing CE or PE retained contracts for {symbol}")
        result[symbol] = {
            "expiry_dates": sorted(selected),
            "contract_count": len(retained),
            "contracts": sorted(
                retained,
                key=lambda item: (item["expiry"], item["strike"], item["side"]),
            ),
            "coverage_validated": False,
            "included_in_asset_final": False,
        }
    return result


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


def aggregate_index_futures_rows(rows, trade_date):
    """Capture exact NSE NIFTY/BANKNIFTY FUTIDX rows from the same UDiFF file.

    No extra exchange request is made. Rows are retained by exact expiry and
    date so consecutive-session comparisons never roll contracts implicitly.
    """
    target_date = parse_date(trade_date)
    output = {symbol: {} for symbol in SYMBOLS}
    seen = set()
    invalid = {symbol: [] for symbol in SYMBOLS}

    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("FinInstrmTp") or "").strip().upper() != "FUTIDX":
            continue
        symbol = str(row.get("TckrSymb") or "").strip().upper()
        if symbol not in SYMBOLS:
            continue
        try:
            if str(row.get("Sgmt") or "").strip().upper() != "FO":
                raise ValueError("unexpected segment")
            if str(row.get("Src") or "").strip().upper() != "NSE":
                raise ValueError("unexpected source")
            if parse_date(row.get("BizDt")) != target_date:
                raise ValueError("trade date mismatch")
            expiry = parse_date(row.get("XpryDt"))
            if expiry < target_date:
                raise ValueError("expired futures contract")
            oi = integer(row.get("OpnIntrst"), "OpnIntrst")
            change = integer(row.get("ChngInOpnIntrst"), "ChngInOpnIntrst")
            close = positive_number(row.get("ClsPric"), "ClsPric")
            if oi < 0:
                raise ValueError("negative open interest")
            key = (symbol, expiry.isoformat())
            if key in seen:
                raise ValueError(f"duplicate futures contract row: {key}")
            seen.add(key)
            output[symbol][expiry.isoformat()] = {
                "open_interest": oi,
                "change_in_oi": change,
                "close": round(close, 6),
            }
        except ValueError as exc:
            invalid[symbol].append(str(exc))

    result = {}
    for symbol in SYMBOLS:
        valid = bool(output[symbol]) and not invalid[symbol]
        result[symbol] = {
            "available": valid,
            "contract_count": len(output[symbol]),
            "by_expiry": dict(sorted(output[symbol].items())),
            "coverage_validated": False,
            "included_in_asset_final": False,
            "reason": None if valid else (
                "; ".join(sorted(set(invalid[symbol])))
                if invalid[symbol] else "no exact FUTIDX rows for this symbol/date"
            ),
        }
    return result


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
                "OptnTp", "StrkPric", "OpnIntrst", "ChngInOpnIntrst", "ClsPric"}
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


def append_archive(archive, trade_date, source_url, payload, symbols, fetched_at, index_futures=None, option_contracts=None):
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
        "index_futures": index_futures or {},
        "option_contracts": option_contracts or {},
    })
    records.sort(key=lambda item: item["date"])
    archive["records"] = records[-KEEP_SESSIONS:]
    archive["schema_version"] = 2
    archive["source"] = "NSE India official F&O UDiFF Common Bhavcopy Final"
    archive["symbols"] = list(SYMBOLS)
    archive["scope"] = "NIFTY and BANKNIFTY index options CE/PE OI, nearest two expiries contract-level closing premium/OI, and FUTIDX price/OI by exact expiry"
    archive["research_only"] = True
    archive["included_in_asset_final"] = False
    return True


def write_archive_atomic(path, archive):
    """Persist a complete NSE OI JSON snapshot and clean up interrupted temp files."""
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
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            archive = json.load(handle)
        if not isinstance(archive, dict) or not isinstance(archive.get("records", []), list):
            raise SystemExit("existing NSE OI archive has invalid structure")
        return archive
    return {"schema_version": 1, "records": []}


def capture_one(archive, trade_date):
    """Capture one exchange date; existing dates are skipped before any HTTP request."""
    date_key = trade_date.isoformat()
    if any(isinstance(item, dict) and item.get("date") == date_key
           for item in archive.get("records", [])):
        return {"date": date_key, "status": "skipped_existing", "date_attempts": 0}
    payload, source_url = fetch_official_bhavcopy(trade_date)
    rows = decode_udiff_zip(payload)
    symbols = aggregate_udiff_rows(rows, trade_date)
    index_futures = aggregate_index_futures_rows(rows, trade_date)
    option_contracts = aggregate_option_contracts(rows, trade_date)
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    changed = append_archive(
        archive, trade_date, source_url, payload, symbols, fetched_at,
        index_futures, option_contracts
    )
    return {
        "date": date_key, "status": "captured" if changed else "skipped_existing",
        "date_attempts": 1, "sha256": hashlib.sha256(payload).hexdigest(),
        "source": source_url, "symbols": {
            symbol: {"expiry_count": value["expiry_count"],
                     "contract_rows": value["contract_rows"],
                     "coverage_validated": value["coverage_validated"],
                     "included_in_asset_final": value["included_in_asset_final"]}
            for symbol, value in symbols.items()
        },
        "index_futures": {
            symbol: {"contract_count": value["contract_count"],
                     "available": value["available"],
                     "coverage_validated": value["coverage_validated"],
                     "included_in_asset_final": value["included_in_asset_final"]}
            for symbol, value in index_futures.items()
        },
        "option_contracts": {
            symbol: {"contract_count": value["contract_count"],
                     "expiry_dates": value["expiry_dates"]}
            for symbol, value in option_contracts.items()
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="One NSE trade date YYYY-MM-DD; defaults to current IST date")
    parser.add_argument("--from-date", help="Start date for bounded historical backfill (YYYY-MM-DD)")
    parser.add_argument("--to-date", help="End date for bounded historical backfill (YYYY-MM-DD)")
    parser.add_argument("--max-sessions", type=int, default=5,
                        help="Maximum weekday dates attempted per backfill run (hard cap 5)")
    parser.add_argument("--delay-seconds", type=float, default=2.0,
                        help="Minimum pause between backfill dates (minimum 2 seconds)")
    parser.add_argument("--archive", default=str(ARCHIVE_PATH))
    args = parser.parse_args()
    if args.date and (args.from_date or args.to_date):
        parser.error("--date cannot be combined with --from-date/--to-date")
    if bool(args.from_date) != bool(args.to_date):
        parser.error("--from-date and --to-date must be supplied together")

    path = Path(args.archive)
    archive = load_archive(path)
    if args.from_date:
        start, end = parse_date(args.from_date), parse_date(args.to_date)
        if end < start:
            parser.error("--to-date must be on or after --from-date")
        if not 1 <= args.max_sessions <= 5:
            parser.error("--max-sessions must be between 1 and the hard cap of 5")
        if args.delay_seconds < 2 or not math.isfinite(args.delay_seconds):
            parser.error("--delay-seconds must be at least 2")
        dates = []
        day = start
        while day <= end:
            if day.weekday() < 5:
                dates.append(day)
            day += dt.timedelta(days=1)
        dates = dates[:args.max_sessions]
        results = []
        for index, day in enumerate(dates):
            try:
                results.append(capture_one(archive, day))
            except Exception as exc:
                results.append({"date": day.isoformat(), "status": "unavailable_or_invalid",
                                "error": str(exc)[:240]})
            if index + 1 < len(dates):
                time.sleep(args.delay_seconds)
        if any(item.get("status") == "captured" for item in results):
            write_archive_atomic(path, archive)
        print(json.dumps({"mode": "bounded_historical_backfill",
                          "attempted_dates": len(dates),
                          "max_date_attempts": args.max_sessions,
                          "delay_seconds": args.delay_seconds,
                          "results": results,
                          "archive_sessions": len(archive.get("records", [])),
                          "research_only": True,
                          "included_in_asset_final": False},
                         ensure_ascii=False, sort_keys=True))
        return 0

    trade_date = parse_date(args.date) if args.date else dt.datetime.now(IST).date()
    result = capture_one(archive, trade_date)
    if result["status"] == "captured":
        write_archive_atomic(path, archive)
    result.update({"archive_sessions": len(archive.get("records", [])),
                   "research_only": True, "included_in_asset_final": False})
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    main()
