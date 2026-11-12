"""Offline daily three-index cash basket replay; never changes production scores."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from nse_cash_basket_breadth import calculate_three_index_baskets

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
        raise ValueError(f"cash basket diagnostic already exists for {day}; refusing overwrite")
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
    if args.date:
        days = [dt.date.fromisoformat(args.date).isoformat()]
    else:
        today = dt.datetime.now(IST).date()
        first = today - dt.timedelta(days=args.backfill_days - 1)
        archived_days = {
            str(row.get("date")) for archive in (nse_archive, bse_archive)
            for row in archive.get("records", [])
            if isinstance(row, dict) and row.get("date")
            and first.isoformat() <= str(row["date"]) <= today.isoformat()
        }
        days = sorted(archived_days)
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
