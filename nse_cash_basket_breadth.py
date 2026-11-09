"""Offline, research-only index constituent breadth from NSE CM cash archives.

Requires a dated official constituent roster (symbol + ISIN) and complete
same-session EQ cash rows. This is a diagnostic, never a production score.
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
from pathlib import Path
from urllib.parse import urlparse


def _valid_roster(roster, index_key, trade_date, max_roster_age_days=180):
    if not isinstance(roster, dict) or not isinstance(roster.get(index_key), dict):
        raise ValueError(f"missing official roster for {index_key}")
    item = roster[index_key]
    members = item.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError(f"empty roster for {index_key}")
    seen = set()
    normalized = []
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("malformed constituent")
        symbol = str(member.get("symbol") or "").strip().upper()
        isin = str(member.get("isin") or "").strip().upper()
        if not symbol or not isin or symbol in seen:
            raise ValueError("constituent symbol/ISIN missing or duplicate")
        seen.add(symbol)
        normalized.append((symbol, isin))
    if len(normalized) != int(item.get("expected_count", len(normalized))):
        raise ValueError(f"roster count mismatch for {index_key}")
    source_url = str(item.get("source_url") or "").strip()
    as_of = str(item.get("as_of") or "").strip()
    if not source_url or not as_of:
        raise ValueError(f"roster provenance missing for {index_key}")
    host = (urlparse(source_url).hostname or "").lower()
    official_hosts = ("nseindia.com", "niftyindices.com", "bseindia.com", "bseindices.com")
    if not any(host == domain or host.endswith("." + domain) for domain in official_hosts):
        raise ValueError(f"non-official roster source for {index_key}")
    try:
        roster_day = dt.date.fromisoformat(as_of)
        trade_day = dt.date.fromisoformat(trade_date)
    except ValueError as exc:
        raise ValueError(f"invalid roster/trade date for {index_key}") from exc
    age_days = (trade_day - roster_day).days
    if age_days < 0:
        raise ValueError(f"roster is newer than requested trade date for {index_key}")
    if age_days > max_roster_age_days:
        raise ValueError(f"stale constituent roster for {index_key}: {age_days} days old")
    return normalized, item


def calculate_breadth(archive, roster, index_key, trade_date, max_roster_age_days=180):
    members, meta = _valid_roster(roster, index_key, trade_date, max_roster_age_days)
    records = archive.get("records", []) if isinstance(archive, dict) else []
    session = next((r for r in records if isinstance(r, dict) and r.get("date") == trade_date), None)
    if not session:
        raise ValueError(f"cash archive session missing: {trade_date}")
    by_symbol = {}
    for row in session.get("equity_rows", []):
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol in by_symbol:
            raise ValueError(f"duplicate archive symbol: {symbol}")
        by_symbol[symbol] = row

    moves = []
    missing = []
    for symbol, isin in members:
        row = by_symbol.get(symbol)
        if row is None or str(row.get("isin") or "").upper() != isin:
            missing.append(symbol)
            continue
        close = float(row["close"])
        previous = float(row["previous_close"])
        if close <= 0 or previous <= 0:
            missing.append(symbol)
            continue
        change_pct = (close / previous - 1.0) * 100.0
        moves.append((symbol, change_pct))

    coverage = len(moves) / len(members)
    if missing:
        return {
            "index": index_key, "date": trade_date, "status": "withheld_incomplete",
            "roster_as_of": meta["as_of"], "expected": len(members),
            "matched": len(moves), "coverage_pct": round(coverage * 100, 2),
            "missing_symbols": missing, "score": None,
            "score_eligible": False, "research_only": True,
        }

    advances = sum(change > 0 for _, change in moves)
    declines = sum(change < 0 for _, change in moves)
    unchanged = len(moves) - advances - declines
    score = 10.0 * (advances - declines) / len(moves)
    return {
        "index": index_key, "date": trade_date, "status": "complete_diagnostic",
        "roster_as_of": meta["as_of"], "expected": len(members),
        "matched": len(moves), "coverage_pct": 100.0,
        "advances": advances, "declines": declines, "unchanged": unchanged,
        "advance_pct": round(100 * advances / len(moves), 2),
        "decline_pct": round(100 * declines / len(moves), 2),
        "equal_weight_mean_change_pct": round(sum(x for _, x in moves) / len(moves), 4),
        "score": round(max(-10.0, min(10.0, score)), 2),
        "score_eligible": False, "research_only": True,
        "method": "10 * (advances - declines) / official constituent count; equal member count",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default="nse_cm_bhavcopy_archive.json")
    parser.add_argument("--rosters", default="index_constituent_rosters.json")
    parser.add_argument("--date", required=True)
    parser.add_argument("--index", choices=("NIFTY", "BANKNIFTY", "SENSEX"), required=True)
    args = parser.parse_args()
    archive = json.loads(Path(args.archive).read_text(encoding="utf-8"))
    rosters = json.loads(Path(args.rosters).read_text(encoding="utf-8"))
    result = calculate_breadth(archive, rosters, args.index, args.date)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
