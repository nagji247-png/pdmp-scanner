"""Offline, research-only index constituent breadth from NSE CM cash archives.

Requires a dated official constituent roster (symbol + ISIN) and complete
same-session EQ cash rows. This is a diagnostic, never a production score.
"""
from __future__ import annotations

import argparse
import json
import datetime as dt
import math
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
    seen_isins = set()
    normalized = []
    for member in members:
        if not isinstance(member, dict):
            raise ValueError("malformed constituent")
        symbol = str(member.get("symbol") or "").strip().upper()
        instrument_id = str(member.get("instrument_id") or "").strip()
        isin = str(member.get("isin") or "").strip().upper()
        identity = symbol or ("BSE:" + instrument_id if instrument_id else "")
        if not identity or not isin or identity in seen or isin in seen_isins:
            raise ValueError("constituent symbol/instrument_id/ISIN missing or duplicate")
        seen.add(identity)
        seen_isins.add(isin)
        normalized.append((symbol, isin, instrument_id))
    if len(normalized) != int(item.get("expected_count", len(normalized))):
        raise ValueError(f"roster count mismatch for {index_key}")
    source_url = str(item.get("source_url") or "").strip()
    as_of = str(item.get("as_of") or "").strip()
    if not source_url or not as_of:
        raise ValueError(f"roster provenance missing for {index_key}")
    parsed_url = urlparse(source_url)
    host = (parsed_url.hostname or "").lower()
    official_hosts = ("nseindia.com", "niftyindices.com", "bseindia.com", "bseindices.com")
    if parsed_url.scheme != "https" or not any(
        host == domain or host.endswith("." + domain) for domain in official_hosts
    ):
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
    by_instrument_id = {}
    for row in session.get("equity_rows", []):
        symbol = str(row.get("symbol") or "").strip().upper()
        instrument_id = str(row.get("instrument_id") or "").strip()
        if symbol:
            if symbol in by_symbol:
                raise ValueError(f"duplicate archive symbol: {symbol}")
            by_symbol[symbol] = row
        if instrument_id:
            if instrument_id in by_instrument_id:
                raise ValueError(f"duplicate archive instrument_id: {instrument_id}")
            by_instrument_id[instrument_id] = row

    moves = []
    missing = []
    for symbol, isin, instrument_id in members:
        row = by_symbol.get(symbol) if symbol else by_instrument_id.get(instrument_id)
        label = symbol or instrument_id
        if row is None or str(row.get("isin") or "").upper() != isin:
            missing.append(label)
            continue
        try:
            close = float(row["close"])
            previous = float(row["previous_close"])
        except (KeyError, TypeError, ValueError, OverflowError):
            missing.append(label)
            continue
        if not math.isfinite(close) or not math.isfinite(previous) or close <= 0 or previous <= 0:
            missing.append(label)
            continue
        change_pct = (close / previous - 1.0) * 100.0
        if not math.isfinite(change_pct):
            missing.append(label)
            continue
        moves.append((label, change_pct))

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


def calculate_three_index_baskets(archives, roster_bundle, trade_date):
    """Validate and calculate all three official index baskets independently.

    archives maps NIFTY/BANKNIFTY/SENSEX to the relevant exchange cash archive.
    NSE archives serve NIFTY and BANKNIFTY; BSE archive serves SENSEX. Missing
    evidence is withheld, never converted into a zero score.
    """
    expected = {"NIFTY": 50, "BANKNIFTY": 14, "SENSEX": 30}
    results = {}
    for index_key, count in expected.items():
        try:
            if not isinstance(roster_bundle, dict):
                raise ValueError("official roster bundle missing")
            roster_map = roster_bundle.get("rosters", roster_bundle)
            item = roster_map.get(index_key)
            if not isinstance(item, dict):
                raise ValueError(f"official roster missing for {index_key}")
            if int(item.get("expected_count", -1)) != count:
                raise ValueError(f"{index_key} official expected_count must be {count}")
            members = item.get("members")
            if not isinstance(members, list) or len(members) != count:
                raise ValueError(f"{index_key} requires exactly {count} official members")
            archive = archives.get(index_key) if isinstance(archives, dict) else None
            if not isinstance(archive, dict):
                raise ValueError(f"dated cash archive missing for {index_key}")
            results[index_key] = calculate_breadth(
                archive, {index_key: item}, index_key, trade_date
            )
        except (TypeError, ValueError, KeyError) as exc:
            results[index_key] = {
                "index": index_key, "date": trade_date,
                "status": "withheld_unverified", "expected": count,
                "matched": 0, "coverage_pct": 0.0,
                "missing_symbols": [], "score": None,
                "score_eligible": False, "research_only": True,
                "reason": str(exc),
            }
    all_complete = all(
        item.get("status") == "complete_diagnostic" for item in results.values()
    )
    return {
        "date": trade_date,
        "status": "complete_diagnostic" if all_complete else "withheld_incomplete",
        "indices": results, "all_three_complete": all_complete,
        "score_eligible": False, "research_only": True,
        "note": "Diagnostic only; no production Final Score mutation.",
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
