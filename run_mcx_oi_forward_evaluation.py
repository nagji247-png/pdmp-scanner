"""Build a persisted, offline-only MCX GOLD/SILVER price-OI research report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcx_oi_forward_backtest import evaluate_forward_price_oi


def build_report(archive, min_signal_sessions=60):
    records = archive.get("records") if isinstance(archive, dict) else None
    if not isinstance(records, list):
        raise ValueError("MCX archive records missing or malformed")
    evaluation = evaluate_forward_price_oi(
        archive, min_signal_sessions=min_signal_sessions
    )
    return {
        "schema_version": 1,
        "source": "MCX India official FUTCOM Bhavcopy archive",
        "archive_sessions": len(records),
        "first_archive_date": records[0].get("date") if records else None,
        "last_archive_date": records[-1].get("date") if records else None,
        "minimum_signal_sessions_per_symbol": int(min_signal_sessions),
        "evaluation": evaluation,
        "research_only": True,
        "included_in_asset_final": False,
        "trading_signal": False,
    }


def write_json_atomic(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default="mcx_bhavcopy_archive.json")
    parser.add_argument("--output", default="mcx_oi_forward_evaluation.json")
    parser.add_argument("--min-signal-sessions", type=int, default=60)
    args = parser.parse_args()
    if args.min_signal_sessions < 1:
        parser.error("--min-signal-sessions must be at least 1")
    archive_path = Path(args.archive)
    if not archive_path.is_file():
        raise SystemExit("MCX_ARCHIVE_MISSING: refusing to create an empty evaluation")
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    report = build_report(archive, args.min_signal_sessions)
    write_json_atomic(args.output, report)
    print(json.dumps({
        "status": report["evaluation"]["status"],
        "archive_sessions": report["archive_sessions"],
        "signal_sessions_by_symbol": report["evaluation"]["signal_sessions_by_symbol"],
        "minimum_signal_sessions_per_symbol": args.min_signal_sessions,
        "output": args.output,
        "research_only": True,
        "included_in_asset_final": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
