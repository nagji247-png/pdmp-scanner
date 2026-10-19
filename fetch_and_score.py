import json, csv, os, datetime as dt
import feedparser, yfinance as yf

TICKERS = {
    "NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK",
    "GOLD": "GC=F", "SILVER": "SI=F", "CRUDEOIL": "CL=F",
    "BITCOIN": "BTC-USD", "NASDAQ": "^IXIC", "DJI": "^DJI",
}

# बहुत सरल शब्द-सूची; बाद में बेहतर कर सकते हैं
POS = {"rally", "surge", "gain", "record high", "bullish", "jump", "rise"}
NEG = {"fall", "slump", "crash", "drag", "loss", "bearish", "drop", "decline", "weigh"}


def headline_score(text):
    t = text.lower()
    return sum(w in t for w in POS) - sum(w in t for w in NEG)


def fetch_news(query):
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    return [e.title for e in feedparser.parse(url).entries[:25]]


def main():
    result = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z"),
              "instruments": {}}

    for name, sym in TICKERS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d", interval="1d")
            change = 0.0
            if len(hist) >= 2:
                change = round((hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100, 2)
        except Exception as e:
            print(f"price error {name}: {e}")
            change = 0.0

        query = f"{name} stock market" if name in ("NIFTY", "SENSEX") else name
        try:
            heads = fetch_news(query)
        except Exception as e:
            print(f"news error {name}: {e}")
            heads = []

        score = round(sum(headline_score(h) for h in heads) / max(len(heads), 1) * 5, 1)
        result["instruments"][name] = {"change_pct": change, "score": score, "headlines": heads[:5]}

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    write_header = not os.path.exists("history.csv")
    with open("history.csv", "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["time_utc", "instrument", "change_pct", "score"])
        for name, d in result["instruments"].items():
            w.writerow([result["updated"], name, d["change_pct"], d["score"]])


if __name__ == "__main__":
    main()
