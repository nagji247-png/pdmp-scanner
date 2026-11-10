#!/usr/bin/env python3
"""Read-only audit of NSE participant-wise OI CSVs for special weekend sessions."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
BASE_URL = "https://archives.nseindia.com/content/nsccl/fao_participant_oi_{date}.csv"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}
PARTICIPANTS = ("FII", "DII", "PRO", "CLIENT")
FIELD_ALIASES = {
    "future_index_long": ("futureindexlong",),
    "future_index_short": ("futureindexshort",),
    "index_call_long": ("optionindexcalllong", "indexcalllong"),
    "index_call_short": ("optionindexcallshort", "indexcallshort"),
    "index_put_long": ("optionindexputlong", "indexputlong"),
    "index_put_short": ("optionindexputshort", "indexputshort"),
    "future_stock_long": ("futurestocklong",),
    "future_stock_short": ("futurestockshort",),
    "stock_call_long": ("optionstockcalllong", "stockcalllong"),
    "stock_call_short": ("optionstockcallshort", "stockcallshort"),
    "stock_put_long": ("optionstockputlong", "stockputlong"),
    "stock_put_short": ("optionstockputshort", "stockputshort"),
}
REQUIRED_INDEX_FIELDS = (
    "future_index_long", "future_index_short",
    "index_call_long", "index_call_short",
    "index_put_long", "index_put_short",
)


def normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).replace("\ufeff", "").lower()).strip()


def parse_participant_csv(text: str) -> dict:
    """Parse the preamble + CSV format used by the existing NSE OI collector."""
    raw_lines = [line for line in text.lstrip("\ufeff").splitlines() if line.strip()]
    header_at = next(
        (i for i, line in enumerate(raw_lines)
         if "client type" in line.lower() or "client_type" in line.lower()),
        None,
    )
    if header_at is None:
        return {
            "header_row_found": False,
            "participants": {},
            "missing_columns": list(REQUIRED_INDEX_FIELDS),
            "missing_participants": list(PARTICIPANTS),
            "participants_missing_required_values": list(PARTICIPANTS),
            "status": "available_incomplete",
        }

    reader = csv.DictReader(raw_lines[header_at:])
    if not reader.fieldnames:
        return {
            "header_row_found": True,
            "participants": {},
            "missing_columns": list(REQUIRED_INDEX_FIELDS),
            "missing_participants": list(PARTICIPANTS),
            "participants_missing_required_values": list(PARTICIPANTS),
            "status": "available_incomplete",
        }

    fields = {normalize_header(key): key for key in reader.fieldnames if key}
    type_key = next(
        (fields[key] for key in ("clienttype", "participant", "participanttype") if key in fields),
        None,
    )
    colmap = {
        output: next((fields[key] for key in aliases if key in fields), None)
        for output, aliases in FIELD_ALIASES.items()
    }
    missing_columns = [key for key in REQUIRED_INDEX_FIELDS if not colmap.get(key)]
    participants = {}
    duplicate_participants = []
    invalid_required_values = []

    for row in reader:
        label = str(row.get(type_key, "")).strip().upper() if type_key else ""
        if label not in PARTICIPANTS:
            continue
        if label in participants:
            duplicate_participants.append(label)
            continue
        values = {}
        for output, column in colmap.items():
            raw = row.get(column) if column else None
            try:
                number = int(float(str(raw).replace(",", ""))) if raw is not None else None
            except (TypeError, ValueError):
                number = None
            values[output] = number
        if any(values.get(key) is None for key in REQUIRED_INDEX_FIELDS):
            invalid_required_values.append(label)
        for prefix in ("future_index", "index_call", "index_put", "future_stock"):
            long_value = values.get(prefix + "_long")
            short_value = values.get(prefix + "_short")
            values[prefix + "_net"] = (
                long_value - short_value
                if long_value is not None and short_value is not None
                else None
            )
        participants[label] = values

    missing_participants = [name for name in PARTICIPANTS if name not in participants]
    status = (
        "available_complete"
        if not missing_columns and not missing_participants
        and not invalid_required_values and not duplicate_participants
        else "available_incomplete"
    )
    return {
        "header_row_found": True,
        "participants": participants,
        "missing_columns": missing_columns,
        "missing_participants": missing_participants,
        "participants_missing_required_values": sorted(set(invalid_required_values)),
        "duplicate_participant_rows": sorted(set(duplicate_participants)),
        "status": status,
    }


def audit_one_date(day: dt.date, session=None) -> dict:
    client = session or requests.Session()
    filename_date = day.strftime("%d%m%Y")
    url = BASE_URL.format(date=filename_date)
    result = {
        "date": day.isoformat(),
        "url": url,
        "source": "NSE official participant-wise EOD OI CSV",
    }
    try:
        response = client.get(url, headers=HEADERS, timeout=15)
    except requests.RequestException as exc:
        result.update({
            "http_status": None,
            "content_bytes": 0,
            "availability_status": "request_error",
            "error": str(exc)[:200],
        })
        return result

    result["http_status"] = response.status_code
    result["content_bytes"] = len(response.content or b"")
    if response.status_code == 404:
        result["availability_status"] = "not_found"
        return result
    if response.status_code != 200:
        result["availability_status"] = f"http_{response.status_code}"
        return result
    if not response.text.strip():
        result["availability_status"] = "empty_file"
        return result

    parsed = parse_participant_csv(response.text)
    result.update(parsed)
    result["availability_status"] = parsed["status"]
    return result


def run_audit(dates: list[dt.date], session=None, sleep_fn=time.sleep) -> dict:
    if not dates:
        raise ValueError("at least one exact session date is required")
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate audit dates are not allowed")
    client = session or requests.Session()
    results = []
    for index, day in enumerate(dates):
        results.append(audit_one_date(day, session=client))
        if index + 1 < len(dates):
            sleep_fn(0.5)
    return {
        "schema_version": 1,
        "audit_status": "completed",
        "source": "NSE official participant-wise EOD OI CSV archive",
        "results": results,
        "provider_calls": len(dates),
        "production_archive_changed": False,
        "production_backtest_changed": False,
        "live_score_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates",
        nargs="+",
        type=dt.date.fromisoformat,
        default=[dt.date(2026, 2, 1), dt.date(2026, 11, 8)],
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "special_session_oi_audit.json",
    )
    args = parser.parse_args()
    report = run_audit(args.dates)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "audit_status": report["audit_status"],
        "results": [
            {
                "date": row["date"],
                "http_status": row["http_status"],
                "availability_status": row["availability_status"],
                "participants_found": sorted(row.get("participants", {})),
                "missing_columns": row.get("missing_columns", []),
                "missing_participants": row.get("missing_participants", []),
            }
            for row in report["results"]
        ],
        "provider_calls": report["provider_calls"],
        "production_archive_changed": False,
        "live_score_changed": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
