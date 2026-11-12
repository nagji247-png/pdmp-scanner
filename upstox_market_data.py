"""Optional Upstox V3 intraday fallback for verified NSE index/equity candles.

Yahoo remains primary. This module is called only when Yahoo returns no usable
bars. It never fabricates prices and never retries a failed Upstox request.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from urllib.parse import quote

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Instrument keys follow Upstox's documented exchange|identifier format.
# Users may extend/override this mapping with UPSTOX_INSTRUMENT_KEYS JSON.
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


def instrument_key_for(symbol, mapping=None):
    keys = dict(DEFAULT_INSTRUMENT_KEYS)
    if isinstance(mapping, dict):
        keys.update({str(k): str(v) for k, v in mapping.items() if k and v})
    raw = os.getenv("UPSTOX_INSTRUMENT_KEYS", "").strip()
    if raw:
        import json
        try:
            extra = json.loads(raw)
            if isinstance(extra, dict):
                keys.update({str(k): str(v) for k, v in extra.items() if k and v})
        except (TypeError, ValueError):
            pass
    return keys.get(str(symbol or "").strip())


def fetch_upstox_candles(symbol, interval_minutes, token=None, session=None):
    """Return validated completed-source candle rows, or [] on any failure."""
    access_token = str(token or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
    instrument_key = instrument_key_for(symbol)
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
                "time": stamp,
                "open": opening,
                "high": high,
                "low": low,
                "close": close,
                "price": close,
                "volume": volume,
                "open_interest": oi,
                "source": "Upstox API V3",
            })
        return sorted(result, key=lambda item: item["time"])
    except Exception:
        # Fallback is deliberately one-shot. The next scheduled scan may retry.
        return []
