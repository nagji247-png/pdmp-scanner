"""Optional Upstox V3 intraday fallback for verified NSE/BSE/MCX candles.

Yahoo remains primary. Upstox is called only when Yahoo has no usable bars.
Unknown instruments are resolved through Upstox's authenticated Instrument
Search API; results are accepted only when they unambiguously match the
configured exchange/segment and expected symbol family.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from urllib.parse import quote

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

DEFAULT_INSTRUMENT_KEYS = {
    "^NSEI": "NSE_INDEX|Nifty 50",
    "^NSEBANK": "NSE_INDEX|Nifty Bank",
    "RELIANCE.NS": "NSE_EQ|INE002A01018",
    "HDFCBANK.NS": "NSE_EQ|INE040A01034",
    "HINDALCO.NS": "NSE_EQ|INE038A01020",
    "ADANIPORTS.NS": "NSE_EQ|INE742F01042",
    "COALINDIA.NS": "NSE_EQ|INE522F01014",
    "EICHERMOT.NS": "NSE_EQ|INE066A01021",
    "APOLLOHOSP.NS": "NSE_EQ|INE437A01024",
    "SBIN.NS": "NSE_EQ|INE062A01020",
}

# Search criteria are explicit. Commodity keys are expiry-specific and are
# resolved at runtime, never hard-coded or guessed.
INSTRUMENT_SEARCH = {
    "^BSESN": {"query": "SENSEX", "exchanges": "BSE", "segments": "INDEX", "instrument_types": "INDEX", "match": "sensex"},
    "TATAMOTORS.NS": {"query": "TATAMOTORS", "exchanges": "NSE", "segments": "EQ", "instrument_types": "EQ", "match": "tatamotors"},
    "GC=F": {"query": "GOLD", "exchanges": "MCX", "segments": "FO", "instrument_types": "FUT", "match": "gold", "expiry": "near_month"},
    "SI=F": {"query": "SILVER", "exchanges": "MCX", "segments": "FO", "instrument_types": "FUT", "match": "silver", "expiry": "near_month"},
    "CL=F": {"query": "CRUDEOIL", "exchanges": "MCX", "segments": "FO", "instrument_types": "FUT", "match": "crude", "expiry": "near_month"},
}
_RESOLVED_KEYS = {}


def instrument_key_for(symbol, mapping=None):
    keys = dict(DEFAULT_INSTRUMENT_KEYS)
    if isinstance(mapping, dict):
        keys.update({str(k): str(v) for k, v in mapping.items() if k and v})
    raw = os.getenv("UPSTOX_INSTRUMENT_KEYS", "").strip()
    if raw:
        try:
            extra = json.loads(raw)
            if isinstance(extra, dict):
                keys.update({str(k): str(v) for k, v in extra.items() if k and v})
        except (TypeError, ValueError):
            pass
    return keys.get(str(symbol or "").strip())


def resolve_instrument_key(symbol, token=None, session=None):
    """Resolve only allow-listed symbols; cache successful exact matches."""
    symbol = str(symbol or "").strip()
    direct = instrument_key_for(symbol)
    if direct:
        return direct
    if symbol in _RESOLVED_KEYS:
        return _RESOLVED_KEYS[symbol]
    cfg = INSTRUMENT_SEARCH.get(symbol)
    access_token = str(token or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
    if not cfg or not access_token:
        return None
    try:
        client = session or requests
        params = {
            "query": cfg["query"],
            "exchanges": cfg["exchanges"],
            "segments": cfg["segments"],
            "instrument_types": cfg["instrument_types"],
            "page_number": 1,
            "records": 30,
        }
        if cfg.get("expiry"):
            params["expiry"] = cfg["expiry"]
        response = client.get(
            "https://api.upstox.com/v2/instruments/search",
            params=params,
            headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
            timeout=(5, 12),
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        rows = payload.get("data") if isinstance(payload, dict) and payload.get("status") == "success" else None
        if not isinstance(rows, list):
            return None
        needle = cfg["match"]
        candidates = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = str(row.get("instrument_key") or "")
            segment = str(row.get("segment") or "")
            exchange = str(row.get("exchange") or "")
            kind = str(row.get("instrument_type") or "").upper()
            text = " ".join(str(row.get(k) or "") for k in ("name", "trading_symbol", "short_name")).lower()
            if (not key or segment != ("BSE_INDEX" if symbol == "^BSESN" else "MCX_FO" if cfg["exchanges"] == "MCX" else "NSE_EQ")
                    or exchange != cfg["exchanges"] or needle not in text):
                continue
            if cfg["instrument_types"] == "FUT":
                if kind != "FUT" or not row.get("expiry"):
                    continue
                candidates.append((str(row["expiry"]), key))
            else:
                if kind != "INDEX" and symbol == "^BSESN":
                    continue
                candidates.append(("", key))
        if not candidates:
            return None
        # Futures: choose nearest future expiry returned by the broker.
        # Non-futures: accept only a unique match to avoid wrong securities.
        if cfg["instrument_types"] == "FUT":
            key = sorted(candidates, key=lambda item: item[0])[0][1]
        else:
            unique = sorted({item[1] for item in candidates})
            if len(unique) != 1:
                return None
            key = unique[0]
        _RESOLVED_KEYS[symbol] = key
        return key
    except Exception:
        return None


def fetch_upstox_candles(symbol, interval_minutes, token=None, session=None):
    """Return validated completed-source candle rows, or [] on any failure."""
    access_token = str(token or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
    instrument_key = resolve_instrument_key(symbol, token=access_token, session=session)
    if not access_token or not instrument_key:
        return []
    try:
        interval = int(interval_minutes)
        if interval < 1 or interval > 300:
            return []
        encoded_key = quote(instrument_key, safe="")
        url = (
            "https://api.upstox.com/v3/historical-candle/intraday/"
            f"{encoded_key}/minutes/{interval}"
        )
        client = session or requests
        response = client.get(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "TRINETRA-Market-Seer/1.0",
            },
            timeout=(5, 12),
        )
        if response.status_code != 200:
            return []
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != "success":
            return []
        candles = ((payload.get("data") or {}).get("candles") or [])
        result = []
        for row in candles:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            stamp = dt.datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=IST)
            else:
                stamp = stamp.astimezone(dt.timezone.utc)
            values = [float(row[i]) for i in range(1, 6)]
            opening, high, low, close, volume = values
            if (not all(math.isfinite(x) for x in values)
                    or min(opening, high, low, close) <= 0 or volume < 0
                    or high < max(opening, close) or low > min(opening, close)
                    or high < low):
                continue
            oi = None
            if len(row) > 6 and row[6] is not None:
                try:
                    candidate_oi = float(row[6])
                    oi = candidate_oi if math.isfinite(candidate_oi) else None
                except (TypeError, ValueError, OverflowError):
                    oi = None
            result.append({
                "time": stamp, "open": opening, "high": high, "low": low,
                "close": close, "price": close, "volume": volume,
                "open_interest": oi, "source": "Upstox API V3",
            })
        return sorted(result, key=lambda item: item["time"])
    except Exception:
        # Fallback is deliberately one-shot. The next scheduled scan may retry.
        return []
