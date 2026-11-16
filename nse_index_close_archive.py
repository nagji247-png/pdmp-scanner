#!/usr/bin/env python3
"""Incrementally archive official NSE daily index close snapshots.

Each CSV contains the full index universe for one trading date. The archive
backfills a bounded number of calendar days per run and retains 260 sessions.
No retry loop; missing, stale or malformed source files fail closed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import time
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ARCHIVE_PATH = Path("nse_index_close_archive.json")
CALENDAR_PATH = Path("exchange_calendar.json")
BASE_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{date}.csv"
SOURCE = "NSE official Daily Snapshot (ind_close_all)"
KEEP_SESSIONS = 260
DEFAULT_BACKFILL_DAYS = 14
MAX_BACKFILL_DAYS = 31
HISTORY_DAYS = 365
MIN_INDEX_ROWS = 30
PAUSE_SECONDS = 0.6
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports",
}


def parse_date(value):
    raw = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d/%m/%Y", "%d%m%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"invalid NSE index date: {raw!r}")


def number(value):
    raw = str(value if value is not None else "").strip().replace(",", "")
    if not raw or raw in ("-", "—", "NA", "N/A", "null"):
        return None
    try:
        result = float(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 and result == result and result not in (float("inf"), float("-inf")) else None


def norm_header(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())


def norm_index_name(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def first_value(row, aliases):
    normalized = {norm_header(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(norm_header(alias))
        if value not in (None, ""):
            return value
    return None


def parse_index_snapshot_csv(payload, expected_date, min_rows=MIN_INDEX_ROWS):
    if not isinstance(payload, (bytes, bytearray, str)) or not payload:
        raise ValueError("empty NSE daily index snapshot")
    raw = payload.decode("utf-8-sig", errors="replace") if isinstance(payload, (bytes, bytearray)) else payload
    if raw.lstrip().startswith(("<", "{", "[")):
        raise ValueError("NSE daily index snapshot returned HTML/JSON instead of CSV")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        raise ValueError("NSE daily index snapshot CSV header missing")
    headers = {norm_header(item) for item in reader.fieldnames}
    required = {"indexname", "indexdate", "closing"}
    if not required.issubset(headers):
        raise ValueError("NSE daily index snapshot missing Index Name, Index Date or Closing")

    expected = parse_date(expected_date)
    result = {}
    seen = set()
    for row in reader:
        name = str(first_value(row, ("Index Name",)) or "").strip()
        date_raw = first_value(row, ("Index Date",))
        close = number(first_value(row, ("Closing", "Close", "Closing Index Value")))
        if not name or not date_raw:
            raise ValueError("NSE daily index snapshot row missing identity/date")
        day = parse_date(date_raw)
        if day != expected:
            raise ValueError(f"NSE daily index date mismatch: {day} != {expected}")
        if close is None:
            raise ValueError(f"NSE daily index snapshot invalid close for {name}")
        key = norm_index_name(name)
        if not key or key in seen:
            raise ValueError(f"NSE daily index snapshot duplicate/invalid index name: {name}")
        seen.add(key)
        result[name] = round(close, 6)
    if len(result) < min_rows:
        raise ValueError(f"NSE daily index snapshot implausibly small: {len(result)} rows")
    return dict(sorted(result.items(), key=lambda item: item[0].upper()))


def is_exchange_session(day, calendar=None):
    calendar = calendar or {}
    special = calendar.get("special_sessions") or {}
    holidays = calendar.get("holidays") or []
    if day.isoformat() in special:
        return True
    holiday_dates = {
        str(item.get("date") or "") for item in holidays if isinstance(item, dict)
    }
    return day.weekday() < 5 and day.isoformat() not in holiday_dates


def fetch_official_index_snapshot(day, session=None):
    client = session or requests.Session()
    url = BASE_URL.format(date=day.strftime("%d%m%Y"))
    response = client.get(url, headers=HEADERS, timeout=(8, 20))
    if response.status_code == 404:
        raise FileNotFoundError(f"NSE index snapshot not published for {day}")
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"NSE index snapshot HTTP {response.status_code} for {day}")
    return response.content, url


def append_session(archive, day, source_url, payload, indices, captured_at=None):
    day_text = parse_date(day).isoformat()
    digest = hashlib.sha256(payload).hexdigest()
    records = archive.setdefault("records", [])
    existing = next((row for row in records if row.get("date") == day_text), None)
    if existing:
        if existing.get("sha256") != digest:
            raise ValueError(f"different NSE index snapshot already archived for {day_text}")
        return False
    records.append({
        "date": day_text,
        "source": SOURCE,
        "source_url": source_url,
        "sha256": digest,
        "captured_at": captured_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "index_count": len(indices),
        "indices": indices,
        "research_only": True,
        "score_eligible": False,
    })
    records.sort(key=lambda row: row["date"])
    archive["records"] = records[-KEEP_SESSIONS:]
    return True


def capture_one(archive, day, calendar=None, session=None):
    day = parse_date(day)
    if not is_exchange_session(day, calendar):
        return {"date": day.isoformat(), "status": "skipped_non_session", "changed": False}
    if any(row.get("date") == day.isoformat() for row in archive.get("records", [])):
        return {"date": day.isoformat(), "status": "already_captured", "changed": False}
    try:
        payload, url = fetch_official_index_snapshot(day, session=session)
        indices = parse_index_snapshot_csv(payload, day)
        changed = append_session(archive, day, url, payload, indices)
        time.sleep(PAUSE_SECONDS)
        return {"date": day.isoformat(), "status": "captured", "index_count": len(indices), "changed": changed}
    except FileNotFoundError as exc:
        return {"date": day.isoformat(), "status": "skipped_missing_file", "changed": False, "detail": str(exc)}
    except Exception as exc:
        return {"date": day.isoformat(), "status": "unavailable", "changed": False, "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}


def should_continue_backfill_after_current(status):
    # A current-day 404 is expected before EOD publication; historical dates
    # are still attempted. A transient/blocking failure stops the request batch.
    return status != "unavailable"


def build_backfill_dates(cursor, today, days=DEFAULT_BACKFILL_DAYS):
    if not isinstance(days, int) or days < 0 or days > MAX_BACKFILL_DAYS:
        raise ValueError(f"backfill-days must be between 0 and {MAX_BACKFILL_DAYS}")
    floor = today - dt.timedelta(days=HISTORY_DAYS)
    dates = []
    for offset in range(days):
        day = cursor - dt.timedelta(days=offset)
        if day < floor:
            break
        dates.append(day)
    return dates


def load_json(path, fallback):
    target = Path(path)
    if not target.exists():
        return fallback
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"invalid JSON at {target}; refusing overwrite: {exc}")


def write_archive(path, archive):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=str(ARCHIVE_PATH))
    parser.add_argument("--calendar", default=str(CALENDAR_PATH))
    parser.add_argument("--date", help="Capture only this session date (YYYY-MM-DD)")
    parser.add_argument("--today", help="IST date YYYY-MM-DD for deterministic testing")
    parser.add_argument("--backfill-days", type=int, default=DEFAULT_BACKFILL_DAYS)
    args = parser.parse_args()

    today = dt.date.fromisoformat(args.today) if args.today else dt.datetime.now(IST).date()
    archive = load_json(args.archive, {
        "schema_version": 1,
        "source": SOURCE,
        "records": [],
        "backfill_cursor": None,
        "backfill_complete": False,
    })
    if not isinstance(archive, dict) or not isinstance(archive.get("records"), list):
        raise SystemExit("NSE index archive invalid; refusing overwrite")
    calendar = load_json(args.calendar, {"holidays": [], "special_sessions": {}})
    session = requests.Session()
    results = []
    changed = False

    if args.date:
        day = dt.date.fromisoformat(args.date)
        result = capture_one(archive, day, calendar=calendar, session=session)
        results.append(result)
        changed = bool(result.get("changed"))
    else:
        current = capture_one(archive, today, calendar=calendar, session=session)
        results.append(current)
        changed = changed or bool(current.get("changed"))
        stop_backfill = not should_continue_backfill_after_current(current["status"])

        if not archive.get("backfill_complete") and not stop_backfill:
            raw_cursor = archive.get("backfill_cursor")
            cursor = parse_date(raw_cursor) if raw_cursor else today - dt.timedelta(days=1)
            dates = build_backfill_dates(cursor, today, args.backfill_days)
            next_cursor = cursor
            for day in dates:
                result = capture_one(archive, day, calendar=calendar, session=session)
                results.append(result)
                changed = changed or bool(result.get("changed"))
                if result["status"] == "unavailable":
                    next_cursor = day
                    stop_backfill = True
                    break
                next_cursor = day - dt.timedelta(days=1)
            archive["backfill_cursor"] = next_cursor.isoformat()
            if next_cursor < today - dt.timedelta(days=HISTORY_DAYS):
                archive["backfill_complete"] = True

    if changed or (not args.date and archive.get("backfill_cursor")):
        archive["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        archive["retention_sessions"] = KEEP_SESSIONS
        archive["backfill_target_start"] = (today - dt.timedelta(days=HISTORY_DAYS)).isoformat()
        write_archive(args.archive, archive)

    summary = {
        "status": "ok" if not any(row["status"] == "unavailable" for row in results) else "partial",
        "today": today.isoformat(),
        "captured_sessions": sum(row["status"] == "captured" for row in results),
        "index_rows": sum(row.get("index_count", 0) for row in results),
        "skipped_non_sessions": sum(row["status"] == "skipped_non_session" for row in results),
        "skipped_missing_files": sum(row["status"] == "skipped_missing_file" for row in results),
        "unavailable": sum(row["status"] == "unavailable" for row in results),
        "backfill_cursor": archive.get("backfill_cursor"),
        "backfill_complete": bool(archive.get("backfill_complete")),
        "retention_sessions": KEEP_SESSIONS,
        "date_results": [
            {"date": row["date"], "status": row["status"], "detail": row.get("detail")}
            for row in results
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
