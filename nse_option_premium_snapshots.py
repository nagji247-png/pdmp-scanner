"""Capture one verified NSE NIFTY option-chain premium snapshot.

This intentionally stores LTP observations, not fabricated OHLC candles.
The scheduled workflow controls the polling interval; NSE timestamps remain
the source timestamps and failed/blocked requests never replace good data.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OUT = Path("nse_option_premium_snapshots.json")
BASE = "https://www.nseindia.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
    "Connection": "keep-alive",
}


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _source_time(value):
    text = str(value or "").strip()
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed
    except ValueError as exc:
        raise ValueError("NSE option-chain timestamp is missing or invalid") from exc


def parse_option_chain(payload, expiry, fetched_at=None):
    if not isinstance(payload, dict):
        raise ValueError("NSE option-chain response is not an object")
    records = payload.get("records")
    if not isinstance(records, dict) or not isinstance(records.get("data"), list):
        raise ValueError("NSE option-chain response has no records.data array")
    source_stamp = _source_time(records.get("timestamp"))
    if fetched_at is None:
        fetched_at = dt.datetime.now(dt.timezone.utc)
    rows = []
    for item in records["data"]:
        if not isinstance(item, dict) or item.get("expiryDate") != expiry:
            continue
        strike = _number(item.get("strikePrice"))
        if strike is None or strike <= 0:
            continue
        for side in ("PE", "CE"):
            leg = item.get(side)
            if not isinstance(leg, dict):
                continue
            ltp = _number(leg.get("lastPrice"))
            if ltp is None or ltp <= 0:
                continue
            rows.append({
                "strike": round(strike, 2),
                "side": side,
                "ltp": round(ltp, 4),
                "volume": int(_number(leg.get("totalTradedVolume")) or 0),
                "oi": int(_number(leg.get("openInterest")) or 0),
            })
    if not rows:
        raise ValueError("NSE option-chain response has no valid traded premiums for nearest expiry")
    return {
        "source_timestamp": source_stamp.isoformat(),
        "fetched_at": fetched_at.astimezone(dt.timezone.utc).isoformat(),
        "expiry": expiry,
        "underlying": _number(records.get("underlyingValue")),
        "points": rows,
    }


def fetch_nifty_snapshot(session=None):
    client = session or requests.Session()
    client.headers.update(HEADERS)
    # One page warm-up establishes the NSE cookie/session context.
    warm = client.get(BASE + "/option-chain", timeout=(10, 20))
    warm.raise_for_status()
    info_response = client.get(
        BASE + "/api/option-chain-contract-info",
        params={"symbol": "NIFTY"},
        timeout=(10, 20),
    )
    info_response.raise_for_status()
    info = info_response.json()
    expiries = info.get("expiryDates") if isinstance(info, dict) else None
    if not isinstance(expiries, list) or not expiries:
        raise ValueError("NSE did not publish NIFTY expiry dates")
    expiry = str(expiries[0]).strip()
    chain_response = client.get(
        BASE + "/api/option-chain-v3",
        params={"type": "Indices", "symbol": "NIFTY", "expiry": expiry},
        timeout=(10, 25),
    )
    chain_response.raise_for_status()
    return parse_option_chain(chain_response.json(), expiry)


def update_archive(path=OUT, snapshot=None):
    if snapshot is None:
        snapshot = fetch_nifty_snapshot()
    if not isinstance(snapshot, dict) or not snapshot.get("points"):
        raise ValueError("refusing to save an empty option snapshot")
    archive = {"schema_version": 1, "symbol": "NIFTY", "source": "NSE India option-chain-v3", "snapshots": []}
    if Path(path).exists():
        existing = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(existing, dict) or existing.get("schema_version") != 1:
            raise ValueError("existing option snapshot archive schema is invalid")
        archive = existing
    snapshots = archive.setdefault("snapshots", [])
    stamp = snapshot["source_timestamp"]
    if snapshots and snapshots[-1].get("source_timestamp") == stamp:
        return False
    snapshots.append(snapshot)
    # About one trading week at a 10-minute schedule; keep file size bounded.
    archive["snapshots"] = snapshots[-250:]
    target = Path(path)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(archive, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temp.replace(target)
    return True


if __name__ == "__main__":
    changed = update_archive()
    print("NSE NIFTY option premium snapshot saved" if changed else "NSE returned an already-saved snapshot")
