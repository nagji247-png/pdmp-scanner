"""Offline daily three-index cash basket replay; never changes production scores."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from nse_cash_basket_breadth import calculate_three_index_baskets
from stock_basket_freshness import exchange_sessions_in_window, is_exchange_session, load_exchange_calendar

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def load_json(path, default):
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"refusing to overwrite unreadable {path}: {exc}") from exc


def append_diagnostic(output_path, result):
    archive = load_json(output_path, {"schema_version": 1, "records": []})
    if not isinstance(archive, dict) or not isinstance(archive.get("records"), list):
        raise RuntimeError("cash basket diagnostic archive structure invalid")
    day = result["date"]
    existing = next((row for row in archive["records"]
                     if isinstance(row, dict) and row.get("date") == day), None)
    if existing:
        if existing == result:
            return False
        # A one-shot EOD fetch can fail while the exchange archive is publishing.
        # Permit a same-session retry to upgrade a withheld record only when the
        # new result has strictly more fully verified index baskets. Never allow
        # a retry to downgrade or silently replace an equally complete record.
        def complete_count(record):
            indices = record.get("indices") if isinstance(record, dict) else None
            if not isinstance(indices, dict):
                return int(bool(record.get("all_three_complete")))
            return sum(
                1 for key in ("NIFTY", "SENSEX", "BANKNIFTY")
                if isinstance(indices.get(key), dict)
                and indices[key].get("status") == "complete_diagnostic"
            )
        if complete_count(result) > complete_count(existing):
            archive["records"] = [
                result if row is existing else row for row in archive["records"]
            ]
            archive["records"].sort(key=lambda row: row["date"])
            archive["schema_version"] = 1
            archive["research_only"] = True
            archive["score_eligible"] = False
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(
                json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(target)
            return True
        # Keep an equally complete or more complete record. Incomplete
        # sessions are retried on later archive runs and may be upgraded once
        # official exchange files arrive; a retry must never downgrade data.
        return False
    archive["records"].append(result)
    archive["records"].sort(key=lambda row: row["date"])
    archive["records"] = archive["records"][-260:]
    archive["schema_version"] = 1
    archive["research_only"] = True
    archive["score_eligible"] = False
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(archive, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(target)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="One cash session date YYYY-MM-DD")
    parser.add_argument("--backfill-days", type=int, default=7,
                        help="Rebuild diagnostics for archived sessions in this rolling window")
    parser.add_argument("--nse-archive", default="nse_cm_bhavcopy_archive.json")
    parser.add_argument("--bse-archive", default="bse_cm_bhavcopy_archive.json")
    parser.add_argument("--rosters", default="index_constituent_rosters.json")
    parser.add_argument("--output", default="index_cash_basket_diagnostics.json")
    args = parser.parse_args()
    if args.backfill_days < 1 or args.backfill_days > 31:
        parser.error("--backfill-days must be between 1 and 31")
    nse_archive = load_json(args.nse_archive, {"records": []})
    bse_archive = load_json(args.bse_archive, {"records": []})
    roster_bundle = load_json(args.rosters, {})
    calendar = load_exchange_calendar()
    saved = load_json(args.output, {"records": []})
    completed_days = set()
    for row in saved.get("records", []) if isinstance(saved, dict) else []:
        indices = row.get("indices", {}) if isinstance(row, dict) else {}
        complete = sum(
            1 for key in ("NIFTY", "SENSEX", "BANKNIFTY")
            if isinstance(indices.get(key), dict)
            and indices[key].get("status") == "complete_diagnostic"
        )
        if complete == 3:
            completed_days.add(str(row.get("date")))
    if args.date:
        requested_day = dt.date.fromisoformat(args.date).isoformat()
        days = [] if requested_day in completed_days or not is_exchange_session(requested_day, calendar) else [requested_day]
    else:
        today = dt.datetime.now(IST).date()
        # Include every exchange session in the window, not only dates found
        # in one of the archives. Missing NSE/BSE files therefore create an
        # explicit withheld record instead of silently reusing an older day.
        sessions = exchange_sessions_in_window(today, args.backfill_days, calendar)
        days = sorted(day.isoformat() for day in sessions if day.isoformat() not in completed_days)
    results = []
    for day in days:
        result = calculate_three_index_baskets(
            {"NIFTY": nse_archive, "BANKNIFTY": nse_archive, "SENSEX": bse_archive},
            roster_bundle, day,
        )
        changed = append_diagnostic(args.output, result)
        results.append({
            "date": day, "status": result["status"],
            "indices": {
                key: {"status": value.get("status"), "matched": value.get("matched"),
                      "expected": value.get("expected"), "score": value.get("score")}
                for key, value in result["indices"].items()
            },
            "all_three_complete": result["all_three_complete"],
            "diagnostic_written": changed, "score_eligible": False,
        })
    print(json.dumps({"results": results, "sessions_processed": len(results),
                      "score_eligible": False, "research_only": True},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
