import json, csv, os, time, math, datetime as dt
from urllib.parse import quote_plus
import feedparser, yfinance as yf
import requests

# ---- इंडेक्स और कमोडिटी ----
# (yfinance सिंबल, न्यूज़ खोज शब्द)
INDEXES = {
    "NIFTY": ("^NSEI", "Nifty 50 stock market"),
    "SENSEX": ("^BSESN", "Sensex stock market"),
    "BANKNIFTY": ("^NSEBANK", "Bank Nifty"),
    "GOLD": ("GC=F", "gold price"),
    "SILVER": ("SI=F", "silver price"),
    "CRUDEOIL": ("CL=F", "crude oil price"),
    "BITCOIN": ("BTC-USD", "bitcoin price"),
    "NASDAQ": ("^IXIC", "Nasdaq stock market"),
    "DJI": ("^DJI", "Dow Jones stock market"),
}

# ---- स्टॉक वॉचलिस्ट ----
# अपने स्टॉक यहाँ जोड़ें या हटाएँ। NSE स्टॉक के लिए सिंबल के आगे ".NS" लगता है।
STOCKS = {
    "RELIANCE": ("RELIANCE.NS", "Reliance Industries share"),
    "HDFCBANK": ("HDFCBANK.NS", "HDFC Bank share"),
    "TATAMOTORS": ("TATAMOTORS.NS", "Tata Motors share"),
    "HINDALCO": ("HINDALCO.NS", "Hindalco share"),
    "ADANIPORTS": ("ADANIPORTS.NS", "Adani Ports share"),
    "COALINDIA": ("COALINDIA.NS", "Coal India share"),
    "EICHERMOT": ("EICHERMOT.NS", "Eicher Motors share"),
    "APOLLOHOSP": ("APOLLOHOSP.NS", "Apollo Hospitals share"),
    "SBIN": ("SBIN.NS", "SBI share"),
}

# शब्द-सूची: वज़न 1 या 2। जितनी बढ़ाएँगे, स्कोर उतना बेहतर होगा।
POS = {"rally": 2, "surge": 2, "record high": 2, "bullish": 2, "gain": 1,
       "jump": 1, "rise": 1, "climb": 1, "rebound": 1, "higher": 1, "profit": 1,
       "beats": 1, "upgrade": 2, "buy": 1}
NEG = {"crash": 2, "slump": 2, "bearish": 2, "plunge": 2, "fall": 1,
       "drag": 1, "loss": 1, "drop": 1, "decline": 1, "weigh": 1,
       "lower": 1, "losses": 1, "sell-off": 2, "selloff": 2, "downgrade": 2,
       "misses": 1, "sell": 1}

# Google Trends: डर-संबंधी खोजें (हर खोज अपने 7-दिन के औसत से तुलना होती है)
FEAR_TERMS = ["nifty crash", "stock market crash", "sensex fall"]
TRENDS_RETRIES = 2

CONTRARIAN_LIMIT = 6.0
DATA_FILE = "data.json"
EVENTS_FILE = "contrarian.json"
HISTORY_FILE = "history.csv"


def clean(obj):
    """NaN या infinity को 0 से बदलता है, ताकि JSON फ़ाइल सही बने।"""
    if isinstance(obj, float):
        return 0.0 if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def headline_score(text):
    t = text.lower()
    return sum(v for k, v in POS.items() if k in t) - sum(v for k, v in NEG.items() if k in t)


def fetch_news(query):
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    feed = feedparser.parse(url)
    items = []
    now = time.time()
    for e in feed.entries[:15]:
        age_h = None
        if getattr(e, "published_parsed", None):
            age_h = round((now - time.mktime(e.published_parsed)) / 3600, 1)
        title = e.title
        source = ""
        if " - " in title:
            title, source = title.rsplit(" - ", 1)
        items.append({"title": title, "source": source,
                      "score": headline_score(title), "age_h": age_h})
    items.sort(key=lambda x: (x["age_h"] is None, x["age_h"] or 0))
    return items


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def daily_returns(sym):
    """तारीख -> उस दिन का % बदलाव (लगभग 1 महीने का डेटा). खाली दिन छोड़े जाते हैं।"""
    closes = yf.Ticker(sym).history(period="1mo", interval="1d")["Close"]
    out = {}
    for i in range(1, len(closes)):
        prev, cur = float(closes.iloc[i - 1]), float(closes.iloc[i])
        if math.isnan(prev) or math.isnan(cur) or prev == 0:
            continue
        d = closes.index[i].strftime("%Y-%m-%d")
        out[d] = round((cur / prev - 1) * 100, 2)
    return out


def update_contrarian(events, name, score, today_str, returns):
    """±6 से ज़्यादा स्कोर दर्ज करें और पुराने इवेंट का नतीजा भरें"""
    key = f"{today_str}|{name}"
    if abs(score) >= CONTRARIAN_LIMIT and not any(e["key"] == key for e in events):
        events.append({"key": key, "date": today_str, "instrument": name,
                       "score": score, "outcome": None, "next_change": None})

    for e in events:
        if e["outcome"] is not None or e["instrument"] != name:
            continue
        later = sorted(d for d in returns if d > e["date"])
        if later:
            nxt = returns[later[0]]
            e["next_change"] = nxt
            same_sign = (nxt >= 0) == (e["score"] >= 0)
            e["outcome"] = "continued" if same_sign else "reversed"


def process(name, sym, query, kind, events, today_str, instruments):
    change, returns = 0.0, {}
    try:
        returns = daily_returns(sym)
        if returns:
            change = list(returns.values())[-1]
    except Exception as e:
        print(f"price error {name}: {e}")

    try:
        heads = fetch_news(query)
    except Exception as e:
        print(f"news error {name}: {e}")
        heads = []

    score = round(sum(h["score"] for h in heads) / len(heads) * 5, 1) if heads else 0.0

    instruments[name] = {
        "type": kind,
        "change_pct": change,
        "score": score,
        "headlines": heads[:8],
    }
    update_contrarian(events, name, score, today_str, returns)


def nifty_range():
    """India VIX से अगले सत्र का 68% संभावना वाला दायरा।
    सूत्र: दैनिक σ = VIX/100 ÷ √252, फिर अंतिम बंद × σ।"""
    try:
        vix_s = yf.Ticker("^INDIAVIX").history(period="5d")["Close"].dropna()
        nifty_s = yf.Ticker("^NSEI").history(period="5d")["Close"].dropna()
        if vix_s.empty or nifty_s.empty:
            raise ValueError("VIX या निफ़्टी का डेटा खाली है")
        vix = float(vix_s.iloc[-1])
        last = float(nifty_s.iloc[-1])
        pct = vix / 100 / math.sqrt(252)
        pts = last * pct
        return {"ok": True, "vix": round(vix, 2), "last_close": round(last, 2),
                "move_pts": round(pts, 1), "move_pct": round(pct * 100, 2),
                "low": round(last - pts, 1), "high": round(last + pts, 1)}
    except Exception as e:
        return {"ok": False, "error": f"रेंज नहीं निकली: {e}"}


def fetch_fii_dii():
    """NSE से FII/DII नेट फ़्लो। NSE अक्सर क्लाउड सर्वर को ब्लॉक करता है,
    इसलिए फ़ेल होने पर {"ok": False} लौटता है।"""
    try:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.nseindia.com/",
        })
        s.get("https://www.nseindia.com", timeout=15)
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=15)
        r.raise_for_status()
        rows = r.json()

        fii = dii = None
        date = None
        for row in rows:
            cat = str(row.get("category", "")).upper()
            net_raw = str(row.get("netValue", "0")).replace(",", "").strip()
            net = float(net_raw) if net_raw not in ("", "-") else 0.0
            date = row.get("date") or date
            if "FII" in cat or "FPI" in cat:
                fii = net
            elif "DII" in cat:
                dii = net

        if fii is None or dii is None:
            raise ValueError("FII या DII की संख्या नहीं मिली")
        return {"ok": True, "as_of": date, "fii": fii, "dii": dii}
    except Exception as e:
        return {"ok": False, "error": f"FII/DII नहीं मिला: {e}"}


def _trends_once():
    """एक बार Google Trends से डेटा लेता है। 429 या कोई भी एरर ऊपर फेंकता है।"""
    from pytrends.request import TrendReq

    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    py.build_payload(FEAR_TERMS, timeframe="now 7-d", geo="IN")
    df = py.interest_over_time()
    if df is None or df.empty:
        raise ValueError("Google से खाली डेटा मिला")
    df = df[FEAR_TERMS].fillna(0)

    base = float(df.mean(axis=1).mean())
    recent = float(df.tail(24).mean(axis=1).mean())
    if base <= 0:
        raise ValueError("बेसलाइन शून्य है")
    fear_vs_avg = round((recent / base - 1) * 100)

    per_term = []
    for t in FEAR_TERMS:
        b = float(df[t].mean())
        r = float(df[t].tail(24).mean())
        per_term.append({"term": t, "vs_avg": round((r / b - 1) * 100) if b > 0 else 0})

    spikes = []
    try:
        time.sleep(5)
        py.build_payload(["nifty", "sensex"], timeframe="now 7-d", geo="IN")
        rq = py.related_queries()
        for kw in ("nifty", "sensex"):
            r = rq.get(kw, {}).get("rising")
            if r is not None and not r.empty:
                for _, row in r.head(6).iterrows():
                    q = row["query"]
                    stock = next((s for s in STOCKS if s.lower() in q.lower()), None)
                    spikes.append({"query": q, "value": str(row["value"]), "stock": stock})
    except Exception as e:
        print(f"rising queries skipped: {e}")

    return {"ok": True, "fear_vs_avg": fear_vs_avg,
            "per_term": per_term, "spikes": spikes[:10]}


def fetch_trends():
    """Google 429 देने पर थोड़ी देर रुककर दोबारा कोशिश करता है।
    सब फेल हो तो {"ok": False, "error": ...} लौटता है।"""
    try:
        import pytrends  # noqa: F401
    except Exception as e:
        return {"ok": False, "error": f"pytrends नहीं मिला: {e}"}

    last_err = ""
    for attempt in range(TRENDS_RETRIES):
        try:
            return _trends_once()
        except Exception as e:
            last_err = str(e)
            print(f"trends attempt {attempt + 1} failed: {last_err}")
            if attempt < TRENDS_RETRIES - 1:
                time.sleep(20)
    return {"ok": False, "error": f"Google Trends फेल: {last_err}"}


def pick_with_fallback(fresh, prev):
    """ताज़ा सफल हो तो वही; वरना पिछला सफल डेटा 'stale' चिह्न के साथ।"""
    if fresh.get("ok"):
        fresh["stale"] = False
        return fresh
    if prev.get("ok"):
        stale = dict(prev)
        stale["stale"] = True
        stale["error"] = fresh.get("error", "")
        return stale
    fresh["stale"] = False
    return fresh


def main():
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    updated = now_utc.isoformat(timespec="minutes").replace("+00:00", "Z")
    events = load_json(EVENTS_FILE, [])
    previous = load_json(DATA_FILE, {})

    result = {"updated": updated, "instruments": {}}

    for name, (sym, query) in INDEXES.items():
        process(name, sym, query, "index", events, today_str, result["instruments"])

    for name, (sym, query) in STOCKS.items():
        process(name, sym, query, "stock", events, today_str, result["instruments"])

    result["contrarian"] = {
        "events": events[-30:],
        "tracked": len([e for e in events if e["outcome"]]),
        "reversed": len([e for e in events if e["outcome"] == "reversed"]),
        "continued": len([e for e in events if e["outcome"] == "continued"]),
    }

    # Nifty रेंज (VIX से) हर रन पर ताज़ा
    result["range"] = nifty_range()

    # FII/DII: ताज़ा मिले तो वही, वरना पिछला सफल डेटा
    fii = pick_with_fallback(fetch_fii_dii(), previous.get("fii_dii") or {})
    if fii.get("ok") and not fii.get("stale"):
        fii["as_of_run"] = updated
    result["fii_dii"] = fii

    # Google Trends: ताज़ा मिले तो वही, वरना पिछला सफल डेटा
    trends = pick_with_fallback(fetch_trends(), previous.get("trends") or {})
    if trends.get("ok") and not trends.get("stale"):
        trends["as_of"] = updated
    result["trends"] = trends

    result = clean(result)
    events = clean(events)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2, allow_nan=False)

    write_header = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["time_utc", "instrument", "change_pct", "score"])
        for name, d in result["instruments"].items():
            w.writerow([result["updated"], name, d["change_pct"], d["score"]])


if __name__ == "__main__":
    main()
