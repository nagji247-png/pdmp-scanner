import json, csv, os, time, datetime as dt
import feedparser, yfinance as yf

TICKERS = {
    "NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK",
    "GOLD": "GC=F", "SILVER": "SI=F", "CRUDEOIL": "CL=F",
    "BITCOIN": "BTC-USD", "NASDAQ": "^IXIC", "DJI": "^DJI",
}

# शब्द-सूची: वज़न 1 या 2। जितनी बढ़ाएँगे, स्कोर उतना बेहतर होगा।
POS = {"rally": 2, "surge": 2, "record high": 2, "bullish": 2, "gain": 1,
       "jump": 1, "rise": 1, "climb": 1, "rebound": 1, "higher": 1}
NEG = {"crash": 2, "slump": 2, "bearish": 2, "plunge": 2, "fall": 1,
       "drag": 1, "loss": 1, "drop": 1, "decline": 1, "weigh": 1,
       "lower": 1, "losses": 1, "sell-off": 2, "selloff": 2}

CONTRARIAN_LIMIT = 6.0
DATA_FILE = "data.json"
EVENTS_FILE = "contrarian.json"
HISTORY_FILE = "history.csv"


def headline_score(text):
    t = text.lower()
    return sum(v for k, v in POS.items() if k in t) - sum(v for k, v in NEG.items() if k in t)


def fetch_news(query):
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
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
    """तारीख -> उस दिन का % बदलाव (लगभग 1 महीने का डेटा)"""
    closes = yf.Ticker(sym).history(period="1mo", interval="1d")["Close"]
    out = {}
    for i in range(1, len(closes)):
        d = closes.index[i].strftime("%Y-%m-%d")
        out[d] = round((closes.iloc[i] / closes.iloc[i - 1] - 1) * 100, 2)
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


def main():
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    events = load_json(EVENTS_FILE, [])

    result = {"updated": now_utc.isoformat(timespec="minutes").replace("+00:00", "Z"),
              "instruments": {}}

    for name, sym in TICKERS.items():
        change, returns = 0.0, {}
        try:
            returns = daily_returns(sym)
            if returns:
                change = list(returns.values())[-1]
        except Exception as e:
            print(f"price error {name}: {e}")

        query = f"{name} stock market" if name in ("NIFTY", "SENSEX") else name
        try:
            heads = fetch_news(query)
        except Exception as e:
            print(f"news error {name}: {e}")
            heads = []

        score = round(sum(h["score"] for h in heads) / len(heads) * 5, 1) if heads else 0.0

        result["instruments"][name] = {
            "change_pct": change,
            "score": score,
            "headlines": heads[:8],
        }
        update_contrarian(events, name, score, today_str, returns)

    result["contrarian"] = {
        "events": events[-30:],
        "tracked": len([e for e in events if e["outcome"]]),
        "reversed": len([e for e in events if e["outcome"] == "reversed"]),
        "continued": len([e for e in events if e["outcome"] == "continued"]),
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    write_header = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["time_utc", "instrument", "change_pct", "score"])
        for name, d in result["instruments"].items():
            w.writerow([result["updated"], name, d["change_pct"], d["score"]])


if __name__ == "__main__":
    main()
