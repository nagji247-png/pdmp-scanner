import json
import math
import time
import datetime as dt
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "sector-analysis.json"
OUTPUT = ROOT / "sector-analysis.json"
MAX_ATTEMPTS = 2


def expected_nse_session(now_ist):
    day = now_ist.date()
    if now_ist.weekday() >= 5:
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
    elif (now_ist.hour, now_ist.minute) < (15, 45):
        day -= dt.timedelta(days=1)
        while day.weekday() >= 5:
            day -= dt.timedelta(days=1)
    return day


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def rsi14(closes):
    if len(closes) < 15:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain = sum(gains[:14]) / 14
    avg_loss = sum(losses[:14]) / 14
    for i in range(14, len(gains)):
        avg_gain = (avg_gain * 13 + gains[i]) / 14
        avg_loss = (avg_loss * 13 + losses[i]) / 14
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 2)


def unavailable(old, reason, date=None):
    return {
        "name": old.get("name"),
        "symbol": old.get("symbol"),
        "source": "Yahoo Finance daily candles; no stale fallback",
        "ok": False,
        "error": reason,
        "date": date,
        "price": None,
        "change_pct": None,
        "volume": None,
        "sma20": None,
        "sma50": None,
        "sma200": None,
        "rsi14": None,
        "support20": None,
        "resistance20": None,
        "market_cap": None,
        "pe": None,
        "forward_pe": None,
        "eps": None,
        "roe_pct": None,
        "debt": None,
        "revenue_growth_pct": None,
        "profit_margin_pct": None,
        "sector": old.get("sector") or "अज्ञात",
        "industry": old.get("industry") or "",
        "trend": "डेटा अनुपलब्ध",
    }


def fetch_company(old, expected_date):
    name, symbol = old.get("name"), old.get("symbol")
    last_error = "ताज़ा दैनिक भाव उपलब्ध नहीं"
    hist = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            hist = yf.Ticker(symbol).history(
                period="1y", interval="1d", auto_adjust=False, actions=False, timeout=20
            )
            if hist is not None and not hist.empty and "Close" in hist.columns:
                hist = hist.dropna(subset=["Close"])
                if not hist.empty:
                    break
            last_error = "Yahoo Finance ने खाली दैनिक candle लौटाई"
        except Exception as exc:
            last_error = str(exc)[:180]
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(3 * (attempt + 1))

    if hist is None or hist.empty:
        return unavailable(old, last_error)

    last_index = hist.index[-1]
    try:
        latest_date = last_index.date()
    except Exception:
        latest_date = dt.date.fromisoformat(str(last_index)[:10])
    if latest_date != expected_date:
        return unavailable(
            old,
            f"ताज़ा NSE सत्र {expected_date.isoformat()} की candle नहीं मिली; आख़िरी उपलब्ध तारीख {latest_date.isoformat()}",
            latest_date.isoformat(),
        )

    closes = [number(x) for x in hist["Close"].tolist()]
    closes = [x for x in closes if x is not None and x > 0]
    if len(closes) < 2:
        return unavailable(old, "तकनीकी गणना के लिए पर्याप्त वैध भाव नहीं", latest_date.isoformat())

    row = hist.iloc[-1]
    previous_close = closes[-2]
    price = closes[-1]
    change_pct = (price / previous_close - 1) * 100 if previous_close else None

    def sma(n):
        return round(sum(closes[-n:]) / n, 2) if len(closes) >= n else None

    lows = [number(x) for x in hist["Low"].tail(20).tolist()] if "Low" in hist else []
    highs = [number(x) for x in hist["High"].tail(20).tolist()] if "High" in hist else []
    lows = [x for x in lows if x is not None and x > 0]
    highs = [x for x in highs if x is not None and x > 0]

    info = {}
    try:
        info = yf.Ticker(symbol).get_info() or {}
    except Exception as exc:
        print(f"Fundamentals unavailable {symbol}: {str(exc)[:120]}")
    sector = info.get("sector") or old.get("sector") or "अज्ञात"
    industry = info.get("industry") or old.get("industry") or ""

    s20, s50, s200 = sma(20), sma(50), sma(200)
    trend = "मिला-जुला"
    if s20 is not None and s50 is not None:
        trend = "तेज़ी" if price > s20 and price > s50 else "मंदी" if price < s20 and price < s50 else "मिला-जुला"

    def pct(key):
        x = number(info.get(key))
        return round(x * 100, 2) if x is not None else None

    return {
        "name": name,
        "symbol": symbol,
        "source": "Yahoo Finance daily candles (delayed data possible)",
        "ok": True,
        "date": latest_date.isoformat(),
        "price": round(price, 2),
        "change_pct": round(change_pct, 2) if change_pct is not None else None,
        "volume": int(number(row.get("Volume")) or 0),
        "sma20": s20,
        "sma50": s50,
        "sma200": s200,
        "rsi14": rsi14(closes),
        "support20": round(min(lows), 2) if lows else None,
        "resistance20": round(max(highs), 2) if highs else None,
        "market_cap": number(info.get("marketCap")),
        "pe": number(info.get("trailingPE")),
        "forward_pe": number(info.get("forwardPE")),
        "eps": number(info.get("trailingEps")),
        "roe_pct": pct("returnOnEquity"),
        "debt": number(info.get("totalDebt")),
        "revenue_growth_pct": pct("revenueGrowth"),
        "profit_margin_pct": pct("profitMargins"),
        "sector": sector,
        "industry": industry,
        "trend": trend,
    }


def main():
    if not INPUT.exists():
        raise SystemExit("sector-analysis.json missing; cannot recover watchlist")
    previous = json.loads(INPUT.read_text(encoding="utf-8"))
    companies = previous.get("companies") or []
    if not companies:
        raise SystemExit("No companies in existing sector watchlist")

    now_utc = dt.datetime.now(dt.timezone.utc)
    now_ist = now_utc + dt.timedelta(hours=5, minutes=30)
    expected_date = expected_nse_session(now_ist)
    output = []
    for index, company in enumerate(companies, 1):
        result = fetch_company(company, expected_date)
        output.append(result)
        print(
            f"[{index}/{len(companies)}] {result['name']}: "
            f"{'OK' if result['ok'] else 'UNAVAILABLE'} "
            f"date={result.get('date')} {result.get('error', '')}"
        )
        time.sleep(0.35)

    available = sum(1 for x in output if x["ok"])
    payload = {
        "generated_at": now_utc.isoformat(timespec="seconds"),
        "expected_market_date": expected_date.isoformat(),
        "source_note": (
            "Yahoo Finance daily candles; data may be delayed. "
            "Only the expected latest NSE session is accepted. "
            "Stale prices and estimated values are never carried forward; "
            "missing data is marked unavailable."
        ),
        "companies": output,
        "summary": {
            "total": len(output),
            "available": available,
            "unavailable": len(output) - available,
        },
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Sector data written: {available}/{len(output)} available for {expected_date.isoformat()}")


if __name__ == "__main__":
    main()
