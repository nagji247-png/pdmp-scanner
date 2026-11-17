#!/usr/bin/env python3
"""Research-only archive of official BSE SENSEX daily closing values.

Fetches the official BSE historical index CSV once for the bounded period
starting at the CLIENT Futures validation anchor. No retries or paid APIs.
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
ANCHOR_DATE = dt.date(2026, 11, 12)
ARCHIVE_PATH = Path("bse_sensex_close_archive.json")
URL = "https://api.bseindia.com/BseIndiaAPI/api/ProduceCSVForDate/w"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/csv,text/plain,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bseindia.com/indices/IndexArchiveData.html",
}


def parse_date(value):
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid BSE index date: {raw!r}")


def finite_positive(value):
    raw = str(value if value is not None else "").strip().replace(",", "")
    try:
        number = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def normalized_header(value):
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def parse_sensex_history_csv(payload, start_date, end_date):
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        raise ValueError("empty BSE SENSEX historical index CSV")
    raw = bytes(payload).decode("utf-8-sig", errors="replace")
    if raw.lstrip().startswith(("<", "{", "[")):
        raise ValueError("BSE SENSEX history returned HTML/JSON instead of CSV")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise ValueError("BSE SENSEX CSV header missing")
    aliases = {normalized_header(name): name for name in reader.fieldnames}
    date_col = next((aliases[k] for k in ("date", "tradingdate", "dt") if k in aliases), None)
    close_col = next((aliases[k] for k in ("close", "closing", "closeindex", "closingindex", "closingindexvalue", "closeindexvalue") if k in aliases), None)
    if not date_col or not close_col:
        raise ValueError("BSE SENSEX CSV missing Date/Close columns")
    start, end = parse_date(start_date), parse_date(end_date)
    result = {}
    for row in reader:
        day = parse_date(row.get(date_col))
        if day < start or day > end:
            raise ValueError(f"BSE SENSEX row date outside requested range: {day}")
        close = finite_positive(row.get(close_col))
        if close is None:
            raise ValueError(f"invalid BSE SENSEX close for {day}")
        key = day.isoformat()
        if key in result:
            raise ValueError(f"duplicate BSE SENSEX close date: {key}")
        result[key] = round(close, 6)
    if not result:
        raise ValueError("BSE SENSEX history contained no dated closes")
    return dict(sorted(result.items()))


def fetch_sensex_history(start_date, end_date, session=None):
    start, end = parse_date(start_date), parse_date(end_date)
    if end < start:
        raise ValueError("BSE SENSEX end date precedes start date")
    client = session or requests.Session()
    params = {
        "strIndex": "SENSEX",
        "dtFromDate": start.strftime("%d/%m/%Y"),
        "dtToDate": end.strftime("%d/%m/%Y"),
        "period": "D",
    }
    # One BSE website warm-up obtains the exchange session cookie; one data request follows.
    client.get("https://www.bseindia.com/indices/IndexArchiveData.html", headers=HEADERS, timeout=(10, 20))
    response = client.get(URL, params=params, headers=HEADERS, timeout=(10, 30))
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"BSE SENSEX historical index HTTP {response.status_code}")
    return response.content, response.url or URL


def write_archive(path, prices, payload, source_url, captured_at=None):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "date": day, "close": close,
            "source": "BSE official SENSEX historical index archive",
            "source_url": source_url,
            "research_only": True,
            "score_eligible": False,
        }
        for day, close in sorted(prices.items())
    ]
    archive = {
        "schema_version": 1,
        "source": "BSE official SENSEX historical index archive",
        "requested_from": min(prices),
        "requested_to": max(prices),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "captured_at_utc": captured_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "records": records,
        "research_only": True,
        "score_eligible": False,
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default=ANCHOR_DATE.isoformat())
    parser.add_argument("--today", help="IST date YYYY-MM-DD for deterministic runs")
    parser.add_argument("--archive", default=str(ARCHIVE_PATH))
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(IST).date()
    payload, source_url = fetch_sensex_history(args.from_date, today)
    prices = parse_sensex_history_csv(payload, args.from_date, today)
    archive = write_archive(args.archive, prices, payload, source_url)
    print(json.dumps({
        "status": "ok", "source": archive["source"],
        "sessions": len(prices), "first_date": min(prices),
        "last_date": max(prices), "research_only": True,
        "score_eligible": False, "archive": args.archive,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
