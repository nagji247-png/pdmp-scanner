"""Publish verified NIFTY 5-minute OHLC candles for the dashboard.

One Yahoo Finance request per normal PDMP scan. No synthetic candles or fallback feed.
"""
import json
import math
import datetime as dt
from pathlib import Path

import yfinance as yf

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OUT = Path("nifty_chart_data.json")


def main():
    fetched = dt.datetime.now(dt.timezone.utc)
    try:
        frame = yf.Ticker("^NSEI").history(period="5d", interval="5m", prepost=False)
        candles = []
        if frame is not None and not frame.empty:
            for stamp, row in frame.iterrows():
                start = stamp.to_pydatetime() if hasattr(stamp, "to_pydatetime") else stamp
                if start.tzinfo is None:
                    start = start.replace(tzinfo=dt.timezone.utc)
                else:
                    start = start.astimezone(dt.timezone.utc)
                # Yahoo timestamps identify the candle start; publish only completed bars.
                if start + dt.timedelta(minutes=5) > fetched:
                    continue
                values = {key: float(row[key]) for key in ("Open", "High", "Low", "Close")}
                if not all(math.isfinite(v) and v > 0 for v in values.values()):
                    continue
                if values["High"] < max(values["Open"], values["Close"], values["Low"]):
                    continue
                if values["Low"] > min(values["Open"], values["Close"], values["High"]):
                    continue
                candles.append({
                    "time": start.isoformat().replace("+00:00", "Z"),
                    "open": round(values["Open"], 2),
                    "high": round(values["High"], 2),
                    "low": round(values["Low"], 2),
                    "close": round(values["Close"], 2),
                })
        if not candles:
            raise RuntimeError("Yahoo returned no completed NIFTY 5-minute OHLC candles")
        payload = {
            "status": "ok",
            "symbol": "^NSEI",
            "interval": "5m",
            "source": "Yahoo Finance",
            "fetched_at": fetched.isoformat().replace("+00:00", "Z"),
            "last_candle_at": candles[-1]["time"],
            "timezone": "Asia/Kolkata",
            "candles": candles[-500:],
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f"Published {len(payload['candles'])} completed NIFTY 5m OHLC candles; last={payload['last_candle_at']}")
    except Exception as exc:
        # Preserve the last successful archive; the dashboard independently marks it stale.
        print(f"NIFTY chart refresh unavailable; existing archive preserved: {str(exc)[:240]}")
        if not OUT.exists():
            OUT.write_text(json.dumps({
                "status": "unavailable", "symbol": "^NSEI", "interval": "5m",
                "source": "Yahoo Finance", "fetched_at": fetched.isoformat().replace("+00:00", "Z"),
                "candles": [], "error": str(exc)[:180],
            }, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
