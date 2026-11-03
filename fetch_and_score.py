import json, csv, os, re, time, math, datetime as dt
from urllib.parse import quote_plus
import feedparser, yfinance as yf
import requests

# ---- इंडेक्स और कमोडिटी ----
# (yfinance सिंबल, न्यूज़ खोज शब्द)
INDEXES = {
    "NIFTY": ("^NSEI", '"Nifty 50" OR Nifty index OR Nifty 50 stocks India'),
    "SENSEX": ("^BSESN", '"BSE Sensex" OR Sensex index India'),
    "BANKNIFTY": ("^NSEBANK", '"Bank Nifty" OR Nifty Bank index OR banking index India'),
    "USDINR": ("INR=X", "USD INR exchange rate India"),
    "GOLD": ("GC=F", "gold price"),
    "SILVER": ("SI=F", "silver price"),
    "CRUDEOIL": ("BZ=F", "Brent crude oil price"),
    "BITCOIN": ("BTC-USD", "bitcoin price"),
    "NASDAQ": ("^IXIC", "Nasdaq stock market"),
    "DJI": ("^DJI", "Dow Jones stock market"),
}

# ---- स्टॉक वॉचलिस्ट ----
# अपने स्टॉक यहाँ जोड़ें या हटाएँ। NSE स्टॉक के लिए सिंबल के आगे ".NS" लगता है।
STOCKS = {
    "RELIANCE": ("RELIANCE.NS", "Reliance Industries share"),
    "HDFCBANK": ("HDFCBANK.NS", "HDFC Bank share"),
    "TATAMOTORS": ("TMPV.NS", "Tata Motors Passenger Vehicles share"),
    "HINDALCO": ("HINDALCO.NS", "Hindalco share"),
    "ADANIPORTS": ("ADANIPORTS.NS", "Adani Ports share"),
    "COALINDIA": ("COALINDIA.NS", "Coal India share"),
    "EICHERMOT": ("EICHERMOT.NS", "Eicher Motors share"),
    "APOLLOHOSP": ("APOLLOHOSP.NS", "Apollo Hospitals share"),
    "SBIN": ("SBIN.NS", "SBI share"),
}

# Google Trends में स्टॉक का नाम पहचानने के लिए वैकल्पिक नाम।
# नया स्टॉक जोड़ें तो यहाँ भी एक लाइन जोड़ें।
STOCK_ALIASES = {
    "RELIANCE": ["reliance"],
    "HDFCBANK": ["hdfc bank", "hdfcbank", "hdfc"],
    "TATAMOTORS": ["tata motors", "tatamotors"],
    "HINDALCO": ["hindalco"],
    "ADANIPORTS": ["adani ports", "adaniports"],
    "COALINDIA": ["coal india", "coalindia"],
    "EICHERMOT": ["eicher", "eichermot"],
    "APOLLOHOSP": ["apollo hospital", "apollohosp", "apollo"],
    "SBIN": ["sbi", "sbin", "state bank"],
}

# शब्द-सूची: वज़न 1 या 2। मिलान शब्द की शुरुआत से होता है।
# "again" में "gain" नहीं गिना जाता, क्योंकि वह शब्द के बीच में है।
POS = {"rally": 2, "rallies": 2, "surge": 2, "record high": 2, "bullish": 2, "gain": 1,
       "jump": 1, "rise": 1, "rose": 1, "climb": 1, "rebound": 1, "higher": 1, "profit": 1,
       "beat": 1, "upgrade": 2, "buy": 1}
NEG = {"crash": 2, "slump": 2, "bearish": 2, "plunge": 2, "tumble": 2, "fall": 1, "fell": 1,
       "slid": 1, "slip": 1, "dip": 1, "drag": 1, "loss": 1, "drop": 1, "decline": 1,
       "weigh": 1, "lower": 1, "sell-off": 2, "selloff": 2, "downgrade": 2, "miss": 1}

# Google Trends: डर-संबंधी खोजें (फ़ियर मेट्रिक के लिए, एक ही अनुरोध)
FEAR_TERMS = ["nifty crash", "stock market crash", "sensex fall"]

# भीड़ के मूड के लिए शब्द: आम लोग जैसे बोलते हैं, English और हिन्दी दोनों।
# Google Trends हर अनुरोध में अधिकतम 5 शब्द लेता है, इसलिए शब्द 4-4 के समूहों में जाते हैं,
# और हर समूह के साथ ANCHOR शब्द जोड़ा जाता है, ताकि अलग अनुरोधों के नंबर तुलनीय बनें।
ANCHOR = "nifty"
# Nifty/Sensex से जुड़े खोज-वाक्यांश। Google Trends सापेक्ष रुचि देता है, वास्तविक search count नहीं।
BULL_TERMS = [
    # प्रचलित English + Hindi/roman Hindi खोजें; कम-volume शब्दों को भी रखा है,
    # ताकि एक-दो शब्द शून्य होने पर पूरा Trends स्कैन विफल न हो।
    "nifty rally", "nifty rise", "nifty bullish", "sensex rise",
    "nifty target", "nifty up", "share market teji", "nifty badhega",
]
BEAR_TERMS = [
    # बुलिश सूची के समान आकार की bearish खोजें; दोनों पक्षों का संतुलित कवरेज।
    "nifty fall", "nifty crash", "nifty bearish", "sensex fall",
    "nifty down", "nifty low", "share market girawat", "nifty girega",
]
TERM_CHUNK = 4

# भीड़ का मूड तभी दिखेगा जब दोनों तरफ़ के शब्दों में कम से कम इतनी खोज हो।
# यह मान "निफ़्टी" की खोज के प्रतिशत में है। शुरुआती मान है, डैशबोर्ड पर असली अनुपात दिखता है ताकि बदला जा सके।
MIN_SIDE_PCT = 0.01
TRENDS_RETRIES = 3  # 429 (rate limit) पर थोड़ा रुककर फिर कोशिश; कुल समय सीमित
TRENDS_MAX_AGE_MINUTES = 150  # इससे पुरानी Google Trends reading डैशबोर्ड पर नहीं दिखेगी

# बाज़ार पर असर वाली ट्रेंडिंग खबरें: हर विषय की एक खोज
MARKET_NEWS_TOPICS = [
    ("भारतीय बाज़ार", "India stock market Nifty Sensex today"),
    ("कच्चा तेल", "crude oil prices today"),
    ("अमेरिकी Fed और ब्याज दर", "Federal Reserve interest rate decision"),
    ("RBI नीति", "RBI monetary policy India rates"),
    ("व्यापार और टैरिफ", "global trade tariffs stock markets"),
    ("सोना, डॉलर और रुपया", "gold price dollar rupee today"),
]
# खबर को बाज़ार से जुड़ा मानने के शब्द (पूरे शब्द या वाक्यांश के रूप में मिलने चाहिए)
MARKET_IMPACT_WORDS = [
    "market", "markets", "stock", "stocks", "shares", "sensex", "nifty", "crude", "oil",
    "interest rate", "interest rates", "rate cut", "rate hike", "repo rate", "fed", "rbi",
    "inflation", "tariff", "tariffs", "war", "gdp", "bond", "bonds", "dollar", "rupee",
    "earnings", "budget", "gold", "bitcoin", "recession", "sanctions", "opec", "fii", "fpi",
    "yield", "yields",
]

# भीड़ की सोच: इस सीमा से ऊपर/नीचे का मतलब "सोच एकतरफ़ा" है
CROWD_EXTREME = 70
CROWD_LOW = 30
# Nifty के वॉच-स्तर (आप यहाँ अपने लेवल जोड़ सकते हैं)
NIFTY_WATCH_LEVELS = [21000, 22000, 23000]

# ⚡ संकेत: स्कोर और कीमत की दिशा अलग हो, इन सीमाओं के साथ
DIV_SCORE_MIN = 1.0
DIV_CHANGE_MIN = 0.2

# ---- संकेत-बदलाव लॉग ----
# भारतीय बाज़ार पर ज़ोर: इन इंस्ट्रूमेंट के संकेत में बदलाव दर्ज होता है।
# इंडेक्स (NIFTY, BANKNIFTY) का वॉल्यूम और VWAP yfinance पर नहीं मिलते, इसलिए वहाँ खाली रहेंगे।
# स्टॉक (RELIANCE, HDFCBANK) पर वॉल्यूम और VWAP मिलते हैं।
SIGNAL_WATCH = {
    "NIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "RELIANCE": "RELIANCE.NS",
    "HDFCBANK": "HDFCBANK.NS",
}
SIG_SCORE_BAND = 1.0      # स्कोर इतने से ज़्यादा बदले, तो भावना बदली मानी जाए
SIG_PRICE_BAND = 0.2      # कीमत इतने % से ज़्यादा हो, तो उसकी दिशा मानी जाए
SIG_MOVE_BAND = 0.1       # बाद की चाल इतने % से कम हो तो "लगभग स्थिर"
SIG_VOL_HIGH = 2.0        # औसत से दोगुना वॉल्यूम "ऊँचा" माना जाए
SIG_LOG_KEEP = 200

CONTRARIAN_LIMIT = 6.0
# बाज़ार बंद/छुट्टी होने पर नए इवेंट नहीं बनते (main में सेट होता है)
SKIP_EVENTS = False
# NSE की आधिकारिक छुट्टियाँ "YYYY-MM-DD" में यहाँ भरें (Google/आधिकारिक सूची से)
NSE_HOLIDAYS = set()
DATA_FILE = "data.json"
EVENTS_FILE = "contrarian.json"
CROWD_FILE = "crowd_events.json"
DIV_FILE = "divergence_events.json"
SIG_STATE_FILE = "signal_state.json"
SIG_LOG_FILE = "signal_log.json"
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


def _word_hits(text, words):
    """शब्दों की गिनती। हर शब्द सिर्फ़ शब्द की शुरुआत से मिलता है।"""
    hits = 0
    for k, v in words.items():
        if re.search(r"(?<![a-z])" + re.escape(k), text):
            hits += v
    return hits


NEG_WORD_RE = r"(?:\bnot|\bno|\bnever|\bfails?\s+to|\bunlikely\s+to)\s+(?:\w+\s+)?$"
SOURCE_WEIGHTS = {
    "reuters": 1.5, "bloomberg": 1.5, "economic times": 1.4, "moneycontrol": 1.3,
    "livemint": 1.3, "business standard": 1.3, "ndtv profit": 1.3, "cnbc tv18": 1.3,
    "the hindu": 1.2, "business today": 1.2, "the times of india": 1.2, "hindustan times": 1.2,
    "ad-hoc-news": 0.6, "univest": 0.6, "marketsmojo": 0.6, "scanx": 0.6,
    "goodreturns": 0.7, "simply wall street": 0.7, "tradingview": 0.8,
}


def source_weight(src):
    s = (src or "").lower()
    for k, v in SOURCE_WEIGHTS.items():
        if k in s:
            return v
    return 1.0


def recency_weight(age_h):
    if age_h is None:
        return 0.5
    if age_h <= 12:
        return 1.0
    if age_h <= 48:
        return 0.6
    return 0.3


def headline_score(text):
    """खबर का स्कोर। 'not/no/fails to' के बाद का शब्द उल्टा गिना जाता है।
    'again' में 'gain' नहीं गिना जाता; शब्द की शुरुआत से मिलान होता है।"""
    t = text.lower()
    total = 0
    for words, sign in ((POS, 1), (NEG, -1)):
        for k, v in words.items():
            for m in re.finditer(r"(?<![a-z])" + re.escape(k), t):
                negated = re.search(NEG_WORD_RE, t[:m.start()])
                total += -sign * v if negated else sign * v
    return total


def _title_tokens(t):
    return set(re.findall(r"[a-z]{3,}", t.lower()))


def dedupe_heads(heads):
    """एक ही खबर कई वेबसाइट पर आती है। मिलते-जुलते शीर्षक (60%+ शब्द समान) एक बार गिने जाते हैं।"""
    kept = []
    for h in heads:
        tk = _title_tokens(h["title"])
        if not tk:
            continue
        dup = False
        for kt, _ in kept:
            if len(tk & kt) / max(1, len(tk | kt)) >= 0.6:
                dup = True
                break
        if not dup:
            kept.append((tk, h))
    return [h for _, h in kept]


def weighted_score(heads):
    """हर खबर का वज़न = स्रोत-वज़न × ताज़गी-वज़न। पूरे इंस्ट्रूमेंट का स्कोर औसत × 5।"""
    num = 0.0
    den = 0.0
    for h in heads:
        w = source_weight(h.get("source")) * recency_weight(h.get("age_h"))
        num += h["score"] * w
        den += w
    return round(num / den * 5, 1) if den > 0 else 0.0

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
                      "link": getattr(e, "link", "") or "",
                      "score": headline_score(title), "age_h": age_h})
    items.sort(key=lambda x: (x["age_h"] is None, x["age_h"] or 0))
    return items


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default



# ---- NSE official MCP quotes (primary for NSE cash market) ----
NSE_MCP_URL = "https://mcp.nseindia.in/cmmkt/mcp"
NSE_MCP_HEADERS = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "User-Agent": "Mozilla/5.0 Trinetra"}
NSE_QUOTE_CACHE = {"stocks": None, "loaded_at": 0}

def nse_mcp_call(tool_name, arguments):
    """One fresh MCP session per call; NSE Streamable HTTP may expire sessions between calls."""
    try:
        with requests.Session() as session:
            init = session.post(NSE_MCP_URL, headers=NSE_MCP_HEADERS, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                           "clientInfo": {"name": "trinetra", "version": "1.0"}}
            }, timeout=25)
            init.raise_for_status()
            headers = dict(NSE_MCP_HEADERS)
            sid = init.headers.get("Mcp-Session-Id")
            if sid:
                headers["Mcp-Session-Id"] = sid
            response = session.post(NSE_MCP_URL, headers=headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments}
            }, timeout=35)
            response.raise_for_status()
            try:
                payload = response.json()
            except ValueError:
                payload = None
                for line in response.text.splitlines():
                    if line.startswith("data:"):
                        try:
                            payload = json.loads(line[5:].strip())
                            break
                        except ValueError:
                            continue
            if not isinstance(payload, dict) or payload.get("error"):
                return None
            contents = (payload.get("result") or {}).get("content") or []
            for item in contents:
                if item.get("type") == "text":
                    try:
                        return json.loads(item.get("text", ""))
                    except (ValueError, TypeError):
                        continue
    except Exception as exc:
        print(f"NSE MCP {tool_name} unavailable: {str(exc)[:180]}")
    return None

def nse_stock_universe():
    now = time.time()
    if NSE_QUOTE_CACHE["stocks"] is not None and now - NSE_QUOTE_CACHE["loaded_at"] < 240:
        return NSE_QUOTE_CACHE["stocks"]
    data = nse_mcp_call("cm_get_equity_stocks", {"limit": 500, "symbolFilter": ""})
    stocks = data.get("stocks", []) if isinstance(data, dict) else []
    if stocks:
        NSE_QUOTE_CACHE["stocks"] = {str(x.get("symbol", "")).upper(): x for x in stocks}
        NSE_QUOTE_CACHE["loaded_at"] = now
        return NSE_QUOTE_CACHE["stocks"]
    return NSE_QUOTE_CACHE["stocks"] or {}

def nse_cash_quote(name, sym):
    """Return actual NSE quote and exchange timestamp; never replace it with scan time."""
    if name == "NIFTY":
        data = nse_mcp_call("cm_get_index_quote", {"indexName": "NIFTY 50"})
        idx = (data or {}).get("index", {})
        if idx.get("last") and data.get("nseTimestamp"):
            return {"price": float(idx["last"]), "stamp": data["nseTimestamp"],
                    "source": "NSE"}
    elif name == "BANKNIFTY":
        data = nse_mcp_call("cm_get_index_quote", {"indexName": "NIFTY BANK"})
        idx = (data or {}).get("index", {})
        if idx.get("last") and data.get("nseTimestamp"):
            return {"price": float(idx["last"]), "stamp": data["nseTimestamp"],
                    "source": "NSE"}
    elif sym.endswith(".NS"):
        symbol = sym[:-3].upper()
        if symbol == "TMPV":
            symbol = "TMPV"
        item = nse_stock_universe().get(symbol)
        if item and item.get("lastTradedPrice") and item.get("latestTimestamp"):
            return {"price": float(item["lastTradedPrice"]),
                    "stamp": item["latestTimestamp"], "source": "NSE"}
    return None

def nse_stamp_fields(stamp):
    """NSE timestamps are exchange-local; output DD/MM/YYYY and 12-hour IST."""
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%d-%b-%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            value = dt.datetime.strptime(str(stamp), fmt)
            return value.strftime("%d/%m/%Y"), value.strftime("%I:%M %p IST")
        except (TypeError, ValueError):
            pass
    return None, None


PRICE_CACHE = {}
SILVER_IMPORT_DUTY = 0.15  # अंतरराष्ट्रीय भाव से अनुमानित MCX-समतुल्य भाव तक
GST_RATE = 0.03  # दुकान/खरीद का अनुमान; एक्सचेंज भाव में GST नहीं
MCX_SILVER_FILE = "mcx_silver.json"

MCX_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-silver-price/"

def refresh_mcx_silver_reference():
    """Try to read public MCX SILVER quote from Upstox; never substitute SI=F."""
    path = MCX_SILVER_FILE
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(MCX_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        # The public page's main quote is normally rendered as ₹1,96,100.00.
        # Use a conservative value range to avoid picking unrelated prices.
        matches = re.findall(r"(?:₹|&#8377;|&#x20b9;|INR\s*)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{5,6}(?:\.[0-9]{1,2})?)", html, re.I)
        candidates = []
        for item in matches:
            try:
                value = float(item.replace(",", ""))
                if 50000 <= value <= 500000:
                    candidates.append(value)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("public page quote not found or outside validation range")
        # First matching price in the page is usually the headline quote.
        current = round(candidates[0], 2)
        data = load_json(path, {})
        old = data.get("mcx_price_per_kg")
        try:
            old_num = float(old)
        except (TypeError, ValueError):
            old_num = None
        if old_num and old_num > 0 and old_num != current:
            data["previous_mcx_price_per_kg"] = old_num
        data.update({
            "mcx_price_per_kg": current,
            "date": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date().isoformat(),
            "source": "Upstox public MCX Silver quote (automatically fetched; verify if page format changes)",
            "source_url": MCX_PUBLIC_URL,
            "source_time": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST"),
            "note": "Public-page quote, not exchange-certified live feed. Dashboard display applies 3% GST estimate."
        })
        with open(path, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX silver public quote refreshed: ₹{current:,.2f}/kg")
        return True
    except Exception as exc:
        print(f"MCX silver auto-refresh failed; retaining last reference and its original timestamp: {exc}")
        return False

def silver_display_price(international_inr_per_kg=None):
    """केवल सत्यापित mcx_silver.json MCX भाव पर 3% GST जोड़ें; अंतरराष्ट्रीय भाव को MCX न बताएं."""
    try:
        mcx = load_json(MCX_SILVER_FILE, {})
        raw = mcx.get("mcx_price_per_kg")
        value = float(raw) if raw is not None else None
        if value is not None and math.isfinite(value) and value > 0:
            return round(value * (1 + GST_RATE), 2), str(mcx.get("date", "")), "MCX quote + 3% GST Estimate"
    except Exception as e:
        print(f"MCX silver manual file error: {e}")
    return None, "", "MCX भाव उपलब्ध नहीं — अनुमान नहीं दिखाया गया"

GOLD_MCX_FILE = "mcx_gold.json"
GOLD_PUBLIC_URL = "https://upstox.com/commodity-market-trading/mcx-gold-price/"

def refresh_mcx_gold_reference():
    """Fetch a public MCX gold quote; only update when a plausible ₹/10g quote is found."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
        response = requests.get(GOLD_PUBLIC_URL, headers=headers, timeout=15)
        response.raise_for_status()
        html = response.text
        matches = re.findall(r"(?:₹|&#8377;|&#x20b9;|INR\s*)\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]{5,6}(?:\.[0-9]{1,2})?)", html, re.I)
        candidates = []
        for item in matches:
            try:
                value = float(item.replace(",", ""))
                if 50000 <= value <= 500000:
                    candidates.append(value)
            except ValueError:
                pass
        if not candidates:
            raise ValueError("public page quote not found or outside ₹50,000–₹5,00,000 per 10g validation range")
        current = round(candidates[0], 2)
        data = load_json(GOLD_MCX_FILE, {})
        old = data.get("mcx_price_per_10g")
        try:
            old_num = float(old)
        except (TypeError, ValueError):
            old_num = None
        if old_num and old_num > 0 and old_num != current:
            data["previous_mcx_price_per_10g"] = old_num
        now_ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
        data.update({
            "mcx_price_per_10g": current,
            "date": now_ist.date().isoformat(),
            "source": "Upstox public MCX Gold page quote; not an exchange-certified live feed",
            "source_url": GOLD_PUBLIC_URL,
            "source_time": now_ist.strftime("%Y-%m-%d %H:%M IST"),
            "note": "Reference quote per 10g; dashboard display adds 3% GST estimate. Jewellery making charges are not included."
        })
        with open(GOLD_MCX_FILE, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        print(f"MCX gold public quote refreshed: ₹{current:,.2f}/10g")
        return True
    except Exception as exc:
        print(f"MCX gold auto-refresh failed; retaining last reference and its original timestamp: {exc}")
        return False

def gold_display_price():
    """MCX reference per 10g plus 3% GST; no jewellery making charges."""
    try:
        data = load_json(GOLD_MCX_FILE, {})
        value = float(data.get("mcx_price_per_10g"))
        if math.isfinite(value) and value > 0:
            return round(value * (1 + GST_RATE), 2), str(data.get("date", "")), "MCX quote × 3% GST"
    except Exception as exc:
        print(f"MCX gold reference unavailable: {exc}")
    return None, "", "MCX Gold भाव उपलब्ध नहीं — अनुमान नहीं दिखाया गया"

def compact_ist_time(value):
    """Convert a stored YYYY-MM-DD HH:MM IST timestamp to a short 12-hour label."""
    try:
        stamp = dt.datetime.strptime(str(value), "%Y-%m-%d %H:%M IST")
        return stamp.strftime("%I.%M %p IST").lstrip("0")
    except (TypeError, ValueError):
        return None


def daily_returns(sym):
    """तारीख -> उस दिन का % बदलाव; कीमत को जरूरत के अनुसार रुपये में दिखाने हेतु कैश करें।"""
    closes = yf.Ticker(sym).history(period="1mo", interval="1d")["Close"]
    today_utc = dt.datetime.now(dt.timezone.utc).date()
    # Yahoo भारतीय शेयर/इंडेक्स की daily candle तारीख IST में देता है।
    # UTC तारीख से तुलना करने पर आधी रात के बाद (IST में) पिछला पूरा दिन
    # गलती से छँट जाता था; भारतीय symbols के लिए IST की तारीख इस्तेमाल करें।
    ist_now = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
    indian = sym.endswith(".NS") or sym in ("^NSEI", "^BSESN", "^NSEBANK", "^INDIAVIX")
    today_market_date = ist_now.date() if indian else today_utc
    indian_closed = indian and ist_now.weekday() < 5 and (ist_now.hour, ist_now.minute) >= (15, 45)
    keep = [(d.date() < today_market_date) or (indian_closed and d.date() == ist_now.date()) for d in closes.index]
    closes = closes[keep]
    last_close = float(closes.iloc[-1]) if len(closes) else None
    if last_close is not None and not math.isfinite(last_close):
        last_close = None
    # Yahoo GC=F और SI=F अमेरिकी डॉलर प्रति ट्रॉय औंस में हैं।
    # USD/INR से बदलकर भारत में प्रचलित इकाई दिखाएँ: Gold ₹/10 ग्राम, Silver ₹/किलो।
    if last_close is not None and sym in ("GC=F", "SI=F"):
        try:
            fx = yf.Ticker("INR=X").history(period="5d", interval="1d")["Close"].dropna()
            rate = float(fx.iloc[-1]) if len(fx) else None
            if rate is not None and math.isfinite(rate) and rate > 0:
                last_close = last_close * rate
                if sym == "GC=F":
                    last_close *= (10.0 / 31.1034768)  # INR प्रति 10 ग्राम
                else:
                    last_close *= (1000.0 / 31.1034768)  # INR प्रति किलो
            else:
                last_close = None
        except Exception:
            last_close = None
    PRICE_CACHE[sym] = round(last_close, 2) if last_close is not None else None
    PRICE_CACHE[sym + "_PREV_CLOSE"] = last_close
    if sym == "BTC-USD":
        # Bitcoin trades 24/7: use the latest completed hourly candle, not a
        # UTC daily candle that can make the card look one day stale in India.
        try:
            hourly = yf.Ticker(sym).history(period="5d", interval="1h")["Close"].dropna()
            now_utc = dt.datetime.now(dt.timezone.utc)
            cutoff = now_utc - dt.timedelta(hours=1)
            hourly = hourly[[idx.to_pydatetime().astimezone(dt.timezone.utc).replace(tzinfo=None) <= cutoff.replace(tzinfo=None) for idx in hourly.index]]
            if len(hourly) >= 25:
                btc_now = float(hourly.iloc[-1])
                btc_prev = float(hourly.iloc[-25])
                if math.isfinite(btc_now) and math.isfinite(btc_prev) and btc_now > 0 and btc_prev > 0:
                    PRICE_CACHE[sym] = round(btc_now, 2)
                    PRICE_CACHE["BTC-USD_CHANGE_PCT"] = round((btc_now / btc_prev - 1) * 100, 2)
                    last_time = hourly.index[-1].to_pydatetime()
                    if last_time.tzinfo is None:
                        last_time = last_time.replace(tzinfo=dt.timezone.utc)
                    PRICE_CACHE["BTC-USD_DATE"] = (last_time.astimezone(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M IST")
                else:
                    PRICE_CACHE["BTC-USD_CHANGE_PCT"] = None
            else:
                PRICE_CACHE["BTC-USD_CHANGE_PCT"] = None
        except Exception as exc:
            print(f"Bitcoin hourly price unavailable: {exc}")
            PRICE_CACHE["BTC-USD_CHANGE_PCT"] = None
    if sym == "GC=F":
        gold_price, gold_date, gold_source = gold_display_price()
        PRICE_CACHE[sym] = gold_price
        PRICE_CACHE["GC=F_SOURCE"] = gold_source
        PRICE_CACHE["GC=F_DATE"] = gold_date
        gold_meta = load_json(GOLD_MCX_FILE, {})
        PRICE_CACHE["GC=F_TIME"] = compact_ist_time(gold_meta.get("source_time"))
        gold = load_json(GOLD_MCX_FILE, {})
        try:
            previous_gold = float(gold.get("previous_mcx_price_per_10g"))
            current_gold = float(gold.get("mcx_price_per_10g"))
            PRICE_CACHE["GC=F_CHANGE_PCT"] = round((current_gold / previous_gold - 1) * 100, 2) if previous_gold > 0 and current_gold > 0 else None
        except (TypeError, ValueError):
            PRICE_CACHE["GC=F_CHANGE_PCT"] = None
    if sym == "SI=F":
        silver_price, silver_date, silver_source = silver_display_price(last_close)
        PRICE_CACHE[sym] = silver_price
        PRICE_CACHE["SI=F_SOURCE"] = silver_source
        PRICE_CACHE["SI=F_DATE"] = silver_date
        silver_meta = load_json(MCX_SILVER_FILE, {})
        PRICE_CACHE["SI=F_TIME"] = compact_ist_time(silver_meta.get("source_time"))
        # Yahoo SI=F का प्रतिशत बदलाव MCX के ₹/kg भाव का बदलाव नहीं है।
        # MCX का पिछला भाव फाइल में न हो तो गलत प्रतिशत न दिखाएँ।
        mcx = load_json(MCX_SILVER_FILE, {})
        previous_mcx = mcx.get("previous_mcx_price_per_kg")
        current_mcx = mcx.get("mcx_price_per_kg")
        try:
            previous_mcx = float(previous_mcx)
            current_mcx = float(current_mcx)
            PRICE_CACHE["SI=F_CHANGE_PCT"] = round((current_mcx / previous_mcx - 1) * 100, 2) if previous_mcx > 0 and current_mcx > 0 else None
        except (TypeError, ValueError):
            PRICE_CACHE["SI=F_CHANGE_PCT"] = None
    out = {}
    for i in range(1, len(closes)):
        prev, cur = float(closes.iloc[i - 1]), float(closes.iloc[i])
        if math.isnan(prev) or math.isnan(cur) or prev == 0:
            continue
        d = closes.index[i].strftime("%Y-%m-%d")
        out[d] = round((cur / prev - 1) * 100, 2)
    return out



def intraday_quote(sym):
    """Best-effort fresh Yahoo 5-minute quote; timestamps are displayed in India time."""
    indian_cash = sym.endswith(".NS") or sym in ("^NSEI", "^BSESN", "^NSEBANK")
    supported = indian_cash or sym in ("INR=X", "BZ=F")
    if not supported:
        return None
    try:
        h = yf.Ticker(sym).history(period="1d", interval="5m", prepost=False)
        if h is None or h.empty or "Close" not in h.columns:
            return None
        stamp = h.index[-1].to_pydatetime()
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        stamp_utc = stamp.astimezone(dt.timezone.utc)
        now_utc = dt.datetime.now(dt.timezone.utc)
        age = (now_utc - stamp_utc).total_seconds() / 60
        bar_ist = stamp_utc + dt.timedelta(hours=5, minutes=30)
        today_ist = (now_utc + dt.timedelta(hours=5, minutes=30)).date()
        max_age = 15 if indian_cash else 60
        if age < -2 or age > max_age or (indian_cash and bar_ist.date() != today_ist):
            return None
        price = float(h["Close"].iloc[-1])
        if not math.isfinite(price) or price <= 0:
            return None
        return {"price": round(price, 4 if sym == "INR=X" else 2),
                "date": bar_ist.date().isoformat(),
                "time": bar_ist.strftime("%I.%M %p IST").lstrip("0"),
                "source": "Yahoo Finance 5-minute quote"}
    except Exception as exc:
        print(f"intraday quote unavailable {sym}: {exc}")
        return None


def fetch_participant_oi(base_date=None):
    """NSE official participant-wise OI: daily EOD, not a live feed.
    base_date lets the caller fetch the latest archived snapshot on/before a target date."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv,text/plain,*/*",
               "Referer": "https://www.nseindia.com/"}
    last_error = "NSE participant OI CSV unavailable"
    if base_date is None:
        base_date = dt.datetime.now(dt.timezone.utc).date()
    elif isinstance(base_date, str):
        base_date = dt.date.fromisoformat(base_date)
    for offset in range(0, 8):
        day = base_date - dt.timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        url = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{day.strftime('%d%m%Y')}.csv"
        try:
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code != 200 or not response.text.strip():
                last_error = f"NSE returned HTTP {response.status_code}"
                continue
            # NSE archive files can include a title/preamble before the actual CSV header.
            raw_lines = [line for line in response.text.lstrip("\ufeff").splitlines() if line.strip()]
            header_at = next((i for i, line in enumerate(raw_lines)
                              if "client type" in line.lower() or "client_type" in line.lower()), None)
            if header_at is None:
                last_error = "NSE CSV header row not found"
                continue
            reader = csv.DictReader(raw_lines[header_at:])
            rows = list(reader)
            if not rows or not reader.fieldnames:
                last_error = "NSE CSV has no data rows"
                continue
            def norm(value):
                return re.sub(r"[^a-z0-9]", "", str(value).replace("\ufeff", "").lower()).strip()
            fields = {norm(k): k for k in reader.fieldnames if k}
            type_key = next((fields[k] for k in ("clienttype", "participant", "participanttype") if k in fields), None)
            if not type_key:
                last_error = "NSE CSV participant column not recognized after header row"
                continue
            wanted = {
                "future_index_long": ("futureindexlong",),
                "future_index_short": ("futureindexshort",),
                "index_call_long": ("optionindexcalllong", "indexcalllong"),
                "index_call_short": ("optionindexcallshort", "indexcallshort"),
                "index_put_long": ("optionindexputlong", "indexputlong"),
                "index_put_short": ("optionindexputshort", "indexputshort"),
                "future_stock_long": ("futurestocklong",),
                "future_stock_short": ("futurestockshort",),
                "stock_call_long": ("optionstockcalllong", "stockcalllong"),
                "stock_call_short": ("optionstockcallshort", "stockcallshort"),
                "stock_put_long": ("optionstockputlong", "stockputlong"),
                "stock_put_short": ("optionstockputshort", "stockputshort"),
            }
            colmap = {out: next((fields[k] for k in aliases if k in fields), None)
                      for out, aliases in wanted.items()}
            if not any(colmap.values()):
                last_error = "NSE CSV position columns not recognized"
                continue
            participants = {}
            for row in rows:
                label = str(row.get(type_key, "")).strip().lower()
                if label not in ("client", "dii", "fii", "pro"):
                    continue
                item = {}
                for out, col in colmap.items():
                    try:
                        item[out] = int(float(str(row.get(col, "0")).replace(",", ""))) if col else None
                    except (ValueError, TypeError):
                        item[out] = None
                for prefix in ("future_index", "index_call", "index_put", "future_stock"):
                    item[prefix + "_net"] = (item.get(prefix + "_long") or 0) - (item.get(prefix + "_short") or 0)
                participants[label.upper()] = item
            if len(participants) < 4:
                last_error = "NSE CSV missing participant rows"
                continue
            return {"ok": True, "stale": False, "date": day.isoformat(),
                    "source": "NSE official participant-wise OI",
                    "scope": "F&O participant totals; stock F&O is aggregate, not per individual stock",
                    "participants": participants}
        except Exception as exc:
            last_error = str(exc)[:180]
    return {"ok": False, "stale": True, "date": None,
            "source": "NSE official participant-wise OI", "error": last_error,
            "participants": {}}


def update_contrarian(events, name, score, today_str, returns):
    """±6 से ज़्यादा स्कोर दर्ज करें और पुराने इवेंट का नतीजा भरें"""
    key = f"{today_str}|{name}"
    if abs(score) >= CONTRARIAN_LIMIT and not SKIP_EVENTS and not any(e["key"] == key for e in events):
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


def update_divergence(events, name, score, change, today_str, returns, headlines=None):
    """⚡ संकेत दर्ज करें: स्कोर और कीमत की दिशा अलग हो।
    नतीजा उसी दिन के सत्र से भरता है जिस दिन संकेत बना।
    'sentiment' = खबर की दिशा में चाल, 'price' = कीमत की दिशा में चाल।
    यह इतिहास का मिलान है, भविष्य की गारंटी नहीं।"""
    diverging = (abs(score) >= DIV_SCORE_MIN and abs(change) >= DIV_CHANGE_MIN
                 and (score > 0) != (change > 0) and not SKIP_EVENTS)
    key = f"{today_str}|{name}|div"
    if diverging and not any(e["key"] == key for e in events):
        events.append({
            "key": key, "date": today_str, "instrument": name,
            "score": score, "price_change": change,
            "sentiment_up": score > 0,
            "headlines": [
                {"title": h.get("title", ""), "source": h.get("source", ""),
                 "link": h.get("link", ""), "score": h.get("score", 0)}
                for h in (headlines or [])[:5]
            ],
            "outcome": None, "next_change": None,
        })

    for e in events:
        if e.get("outcome") is not None or e["instrument"] != name:
            continue
        same_or_later = sorted(d for d in returns if d >= e["date"])
        if not same_or_later:
            continue
        nxt = returns[same_or_later[0]]
        e["next_change"] = nxt
        move_up = nxt >= 0
        e["outcome"] = "sentiment" if move_up == e["sentiment_up"] else "price"


def _rsi_series(closes, n=14):
    """Wilder RSI हर बार के लिए (पहले n बार None)।"""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _pivots(values, kind, k=3):
    """स्थानीय निम्न (kind='low') या उच्च (kind='high') बिंदु। आख़िरी k बार पर पुष्टि नहीं होती।"""
    idx = []
    for i in range(k, len(values) - k):
        win = values[i - k:i + k + 1]
        if kind == "low" and values[i] == min(win) and win.count(values[i]) == 1:
            idx.append(i)
        if kind == "high" and values[i] == max(win) and win.count(values[i]) == 1:
            idx.append(i)
    return idx


def rsi_divergence(closes, recent_bars=40):
    """RSI विचलन (सही दिशा):
    - Bullish: कीमत का निचला निम्न, पर RSI का ऊँचा निम्न।
    - Bearish: कीमत का ऊँचा उच्च, पर RSI का नीचा उच्च।
    सिर्फ़ हाल के बार (recent_bars) में पुष्ट बिंदुओं पर। न मिले तो None।"""
    if len(closes) < 60:
        return None
    rsi = _rsi_series(closes)
    if rsi[-1] is None:
        return None
    last = len(closes) - 1
    lows = [i for i in _pivots(closes, "low") if i >= last - recent_bars and rsi[i] is not None]
    highs = [i for i in _pivots(closes, "high") if i >= last - recent_bars and rsi[i] is not None]
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if closes[b] < closes[a] and rsi[b] > rsi[a]:
            return {"label": "⚡ Bullish divergence", "reason": f"दैनिक कीमत निचला निम्न, RSI ऊँचा निम्न ({rsi[a]:.1f} → {rsi[b]:.1f})"}
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if closes[b] > closes[a] and rsi[b] < rsi[a]:
            return {"label": "⚡ Bearish divergence", "reason": f"दैनिक कीमत ऊँचा उच्च, RSI नीचा उच्च ({rsi[a]:.1f} → {rsi[b]:.1f})"}
    return None


def derive_card_indicator(name, sym, score, change):
    """
    Card labels must be evidence-based:
    - SILVER "still building" only when Yahoo returns same-contract open-interest
      rising alongside falling price; otherwise unavailable.
    - BITCOIN bullish divergence only when completed 30m candles show price lower-low
      while RSI makes a higher-low. This is a technical pattern, not a prediction.
    """
    if name == "SILVER":
        try:
            h = yf.Ticker(sym).history(period="5d", interval="30m")
            if h is None or len(h) < 4 or "Open Interest" not in h.columns:
                return {"indicator_label": "BUILDUP DATA UNAVAILABLE",
                        "indicator_reason": "एक ही कॉन्ट्रैक्ट का भरोसेमंद Open Interest डेटा उपलब्ध नहीं"}
            oi = h["Open Interest"].dropna()
            close = h["Close"].dropna()
            if len(oi) < 3 or len(close) < 3:
                return {"indicator_label": "BUILDUP DATA UNAVAILABLE",
                        "indicator_reason": "Open Interest/कीमत के पर्याप्त पूरे बार नहीं"}
            oi_delta = float(oi.iloc[-1] - oi.iloc[-2])
            price_delta = float(close.iloc[-1] / close.iloc[-2] - 1)
            if oi_delta > 0 and price_delta < 0:
                return {"indicator_label": "BEARISH BUILDUP",
                        "indicator_reason": "पूरे हुए 30-मिनट बार में कीमत नीचे और Open Interest ऊपर"}
            if oi_delta > 0 and price_delta > 0:
                return {"indicator_label": "BULLISH BUILDUP",
                        "indicator_reason": "पूरे हुए 30-मिनट बार में कीमत और Open Interest दोनों ऊपर"}
            return {"indicator_label": "NO CLEAR BUILDUP",
                    "indicator_reason": "कीमत और Open Interest से स्पष्ट नया buildup नहीं मिला"}
        except Exception as exc:
            return {"indicator_label": "BUILDUP DATA UNAVAILABLE",
                    "indicator_reason": str(exc)[:120]}

    if name in ("NIFTY", "SENSEX", "BANKNIFTY"):
        try:
            closes = [float(x) for x in yf.Ticker(sym).history(period="6mo", interval="1d")["Close"].dropna().tolist()]
            div = rsi_divergence(closes)
            if div:
                return {"indicator_label": div["label"]}
        except Exception as exc:
            print(f"index RSI divergence skipped {name}: {exc}")
        return {}

    if name == "BITCOIN":
        # Primary: Yahoo Finance; fallback: Binance public spot klines (no API key).
        # Both sources use completed 30-minute candles only.
        closes = []
        try:
            h = yf.Ticker(sym).history(period="5d", interval="30m")
            if h is not None and len(h) >= 20 and "Close" in h.columns:
                now = dt.datetime.now(dt.timezone.utc)
                idx = h.index
                last_time = idx[-1].to_pydatetime()
                if last_time.tzinfo is None:
                    last_time = last_time.replace(tzinfo=dt.timezone.utc)
                if (now - last_time.astimezone(dt.timezone.utc)).total_seconds() < 30 * 60:
                    h = h.iloc[:-1]
                closes = [float(v) for v in h["Close"].dropna().tolist()]
        except Exception:
            closes = []

        source = "Yahoo Finance"
        if len(closes) < 20:
            try:
                url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=30m&limit=100"
                response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                rows = response.json()
                now_ms = int(time.time() * 1000)
                # Kline index 6 is close-time in milliseconds; discard any unfinished candle.
                closes = [float(row[4]) for row in rows if len(row) > 6 and int(row[6]) < now_ms]
                source = "Binance public spot candles"
            except Exception as exc:
                return {}

        if len(closes) < 20:
            return {}
        # Wilder-style RSI approximation using rolling 14-bar average gains/losses.
        rsi = [None] * len(closes)
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        for i in range(14, len(closes)):
            window = deltas[i-14:i]
            avg_gain = sum(max(x, 0.0) for x in window) / 14
            avg_loss = sum(max(-x, 0.0) for x in window) / 14
            if avg_loss == 0:
                rsi[i] = 100.0 if avg_gain > 0 else 50.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100.0 - (100.0 / (1.0 + rs))
        # Compare last six completed candles to the six before them.
        p1, p2 = closes[-6:], closes[-12:-6]
        r1 = [x for x in rsi[-6:] if x is not None]
        r2 = [x for x in rsi[-12:-6] if x is not None]
        if len(r1) >= 3 and len(r2) >= 3 and min(p1) < min(p2) and min(r1) > min(r2):
            return {"indicator_label": "⚡ Bullish divergence",
                    "indicator_reason": "30-मिनट कीमत lower low, RSI higher low · स्रोत: " + source}
        return {}
    return {}


def process(name, sym, query, kind, events, today_str, instruments, div_events, all_returns):
    returns = {}
    change = 0.0
    try:
        returns = daily_returns(sym)
        if returns:
            change = returns[max(returns)]
    except Exception as e:
        print(f"price error {name}: {e}")
    all_returns[name] = returns

    # NSE official quote is primary for Indian cash indices/stocks; Yahoo is backup.
    nse_quote = nse_cash_quote(name, sym)
    yahoo_quote = intraday_quote(sym) if not nse_quote else None
    live_quote = nse_quote or yahoo_quote
    if live_quote:
        PRICE_CACHE[sym] = live_quote["price"]
        prev_close = PRICE_CACHE.get(sym + "_PREV_CLOSE")
        if prev_close and prev_close > 0:
            change = round((live_quote["price"] / prev_close - 1) * 100, 2)
    quote_date, quote_time = nse_stamp_fields(live_quote["stamp"]) if nse_quote else (
        (live_quote["date"], live_quote["time"]) if live_quote else (None, None))
    price_time = quote_time if live_quote else (
        PRICE_CACHE.get("GC=F_TIME") if sym == "GC=F" else
        PRICE_CACHE.get("SI=F_TIME") if sym == "SI=F" else
        compact_ist_time(PRICE_CACHE.get("BTC-USD_DATE")) if sym == "BTC-USD" else None
    )

    try:
        heads = fetch_news(query)
    except Exception as e:
        print(f"news error {name}: {e}")
        heads = []

    heads = dedupe_heads(heads)
    score = weighted_score(heads)

    instruments[name] = {
        "type": kind,
        "change_pct": PRICE_CACHE.get("SI=F_CHANGE_PCT") if sym == "SI=F" else PRICE_CACHE.get("BTC-USD_CHANGE_PCT") if sym == "BTC-USD" else change,
        "price": PRICE_CACHE.get(sym),
        "price_time": price_time,
        "price_as_of": quote_date if nse_quote else live_quote["date"] if live_quote else (PRICE_CACHE.get("SI=F_DATE") or max(returns)) if sym == "SI=F" and (PRICE_CACHE.get("SI=F_DATE") or returns) else PRICE_CACHE.get("BTC-USD_DATE") if sym == "BTC-USD" else (max(returns) if returns else None),
        "price_unit": ("₹/kg (Estimate)" if sym == "SI=F" else "₹/10g" if sym == "GC=F" else ""),
        "price_source": live_quote["source"] if live_quote else PRICE_CACHE.get("SI=F_SOURCE") if sym == "SI=F" else PRICE_CACHE.get("GC=F_SOURCE") if sym == "GC=F" else None,
        "score": score,
        "headlines": heads[:8],
        "pos_n": sum(1 for h in heads if h["score"] > 0),
        "neg_n": sum(1 for h in heads if h["score"] < 0),
        **derive_card_indicator(name, sym, score, change),
    }
    update_contrarian(events, name, score, today_str, returns)
    update_divergence(div_events, name, score, change, today_str, returns, heads)


# ---- संकेत-बदलाव लॉग ----

def intraday_snapshot(sym):
    """30-मिनट के बार से ताज़ा कीमत, आज का VWAP और वॉल्यूम का अनुपात।
    डेटा न मिले तो None लौटता है।"""
    try:
        h = yf.Ticker(sym).history(period="5d", interval="30m")
        if h is None or h.empty:
            return None

        # अधूरी चलती 30-मिनट कैंडल को संकेत में शामिल न करें।
        # Yahoo candle index आम तौर पर bar-start होता है; केवल वही bar लें
        # जिसका 30-मिनट समय पूरा हो चुका है।
        idx_utc = h.index
        if getattr(idx_utc, "tz", None) is None:
            idx_utc = idx_utc.tz_localize("UTC")
        else:
            idx_utc = idx_utc.tz_convert("UTC")
        now_utc = dt.datetime.now(dt.timezone.utc)
        completed = idx_utc + dt.timedelta(minutes=30) <= now_utc
        h = h.loc[completed]
        if h.empty:
            return None

        last = h.iloc[-1]
        price = float(last["Close"])
        vol_total = float(h["Volume"].sum())
        snap = {"price": price, "vwap": None, "vol_ratio": None, "vol_ok": vol_total > 0}
        if snap["vol_ok"]:
            today = h.index[-1].date()
            td = h[[d.date() == today for d in h.index]]
            tv = float(td["Volume"].sum())
            if tv > 0:
                tp = (td["High"] + td["Low"] + td["Close"]) / 3
                snap["vwap"] = float((tp * td["Volume"]).sum() / tv)
            avg = float(h["Volume"].mean())
            if avg > 0:
                snap["vol_ratio"] = float(last["Volume"]) / avg
        return snap
    except Exception as e:
        print(f"intraday error {sym}: {e}")
        return None


def _band(x, band):
    if x >= band:
        return 1
    if x <= -band:
        return -1
    return 0


def update_signals(instruments, state, log, now_iso):
    """हर देखे जाने वाले इंस्ट्रूमेंट का संकेत-स्नैपशॉट बनाता है।
    अगर भावना, कीमत-दिशा, VWAP-पक्ष या वॉल्यूम बदले, तो लॉग में दर्ज होता है।
    पिछले बदलाव के बाद की कीमत अगले रन पर भर जाती है।"""
    now = dt.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))

    for name, sym in SIGNAL_WATCH.items():
        d = instruments.get(name)
        if not d:
            continue
        snap = intraday_snapshot(sym)
        price_now = snap["price"] if snap else None

        # 1) पिछले बदलावों की बाद की कीमत भरें (नए इवेंट से पहले, ताकि नया इवेंट उसी रन में न भरे)
        if price_now is not None:
            for ev in log:
                if ev["instrument"] != name or ev.get("price_after") is not None:
                    continue
                if not ev.get("price_at_change"):
                    continue
                mv = (price_now / ev["price_at_change"] - 1) * 100
                ev["price_after"] = round(price_now, 4)
                ev["move_pct"] = round(mv, 2)
                ev["after_minutes"] = round(
                    (now - dt.datetime.fromisoformat(ev["time"].replace("Z", "+00:00"))).total_seconds() / 60)
                if mv >= SIG_MOVE_BAND:
                    ev["direction"] = "ऊपर"
                elif mv <= -SIG_MOVE_BAND:
                    ev["direction"] = "नीचे"
                else:
                    ev["direction"] = "लगभग स्थिर"

        vwap_side = None
        vol_hi = None
        if snap:
            if snap["vwap"] is not None:
                vwap_side = 1 if snap["price"] > snap["vwap"] else -1
            if snap["vol_ratio"] is not None:
                vol_hi = snap["vol_ratio"] >= SIG_VOL_HIGH

        cur = {
            "score": d["score"],
            "sent": _band(d["score"], SIG_SCORE_BAND),
            "price_dir": _band(d["change_pct"], SIG_PRICE_BAND),
            "vwap_side": vwap_side,
            "vol_hi": vol_hi,
            "vol_ok": bool(snap and snap["vol_ok"]),
            "price_now": price_now,
            "time": now_iso,
        }

        prev = state.get(name)
        if prev is None:
            cur["since"] = now_iso
            state[name] = cur
            continue

        changed = []
        if cur["sent"] != prev["sent"] or abs(cur["score"] - prev["score"]) >= SIG_SCORE_BAND:
            changed.append("भावना")
        if cur["price_dir"] != prev["price_dir"]:
            changed.append("कीमत")
        if cur["vwap_side"] is not None and prev.get("vwap_side") is not None \
                and cur["vwap_side"] != prev["vwap_side"]:
            changed.append("VWAP")
        if cur["vol_hi"] is not None and prev.get("vol_hi") is not None \
                and cur["vol_hi"] != prev["vol_hi"]:
            changed.append("वॉल्यूम")

        if changed:
            since = dt.datetime.fromisoformat(prev["since"].replace("Z", "+00:00"))
            log.append({
                "time": now_iso,
                "instrument": name,
                "prev_score": prev["score"],
                "new_score": cur["score"],
                "changed": changed,
                "vol_data": cur["vol_ok"],
                "held_minutes": round((now - since).total_seconds() / 60),
                "price_at_change": price_now,
                "price_after": None,
                "move_pct": None,
                "after_minutes": None,
                "direction": None,
            })
            if len(log) > SIG_LOG_KEEP:
                del log[:len(log) - SIG_LOG_KEEP]
            cur["since"] = now_iso
        else:
            cur["since"] = prev["since"]
        state[name] = cur


def signal_summary(state):
    out = {}
    for name, s in state.items():
        out[name] = {
            "score": s.get("score"),
            "sent": s.get("sent"),
            "price_dir": s.get("price_dir"),
            "vwap_side": s.get("vwap_side"),
            "vol_hi": s.get("vol_hi"),
            "vol_ok": s.get("vol_ok"),
            "since": s.get("since"),
        }
    return out


# ---- बाकी हिस्से ----

def is_market_news(title):
    """खबर बाज़ार से जुड़ी है या नहीं, यह पूरे शब्द या वाक्यांश मिलाकर तय होता है।"""
    t = title.lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in MARKET_IMPACT_WORDS)


def impact_label(score):
    if score >= 2:
        return "सकारात्मक असर"
    if score <= -2:
        return "नकारात्मक असर"
    return "तटस्थ"


def fetch_market_news():
    """बाज़ार पर असर डालने वाली ताज़ा खबरें, कई विषयों से।"""
    seen = set()
    items = []
    for topic, query in MARKET_NEWS_TOPICS:
        try:
            heads = fetch_news(query)
        except Exception as e:
            print(f"market news error {topic}: {e}")
            continue
        for h in heads[:8]:
            key = h["title"].lower()[:80]
            if key in seen or not is_market_news(h["title"]):
                continue
            seen.add(key)
            items.append({
                "topic": topic,
                "title": h["title"],
                "source": h["source"],
                "link": h["link"],
                "score": h["score"],
                "impact": impact_label(h["score"]),
                "age_h": h["age_h"],
            })
    if not items:
        return {"ok": False, "error": "बाज़ार से जुड़ी खबरें इस बार नहीं मिलीं"}
    items.sort(key=lambda x: (x["age_h"] is None, x["age_h"] or 0))
    return {"ok": True, "items": items[:12]}


def _num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def summarise_fundamentals(info, price):
    """yfinance के info से कंपनी के आँकड़े। जो फ़ील्ड नहीं मिलता, वह None रहता है; कुछ भी बनाया नहीं जाता।
    'ग्राहक' और 'प्रमोटर/FII/DII' का पूरा विभाजन यहाँ नहीं मिलता, इसलिए वह नहीं भरा जाता।"""
    mcap = _num(info.get("marketCap"))
    target = _num(info.get("targetMeanPrice"))
    hi = _num(info.get("fiftyTwoWeekHigh"))
    lo = _num(info.get("fiftyTwoWeekLow"))
    out = {
        "market_cap_cr": round(mcap / 1e7, 0) if mcap else None,
        "pe_trailing": _num(info.get("trailingPE")),
        "pe_forward": _num(info.get("forwardPE")),
        "eps_trailing": _num(info.get("trailingEps")),
        "roe_pct": round(_num(info.get("returnOnEquity")) * 100, 1) if _num(info.get("returnOnEquity")) is not None else None,
        "operating_margin_pct": round(_num(info.get("operatingMargins")) * 100, 1) if _num(info.get("operatingMargins")) is not None else None,
        "revenue_growth_pct": round(_num(info.get("revenueGrowth")) * 100, 1) if _num(info.get("revenueGrowth")) is not None else None,
        "earnings_growth_pct": round(_num(info.get("earningsGrowth")) * 100, 1) if _num(info.get("earningsGrowth")) is not None else None,
        "insiders_pct": round(_num(info.get("heldPercentInsiders")) * 100, 1) if _num(info.get("heldPercentInsiders")) is not None else None,
        "institutions_pct": round(_num(info.get("heldPercentInstitutions")) * 100, 1) if _num(info.get("heldPercentInstitutions")) is not None else None,
        "analyst_target": round(target, 2) if target else None,
        "upside_to_target_pct": None,
        "w52_high": round(hi, 2) if hi else None,
        "w52_low": round(lo, 2) if lo else None,
        "position_in_52w_pct": None,
        "sector": info.get("sector") or "अज्ञात",
        "industry": info.get("industry") or "",
        "customers": None,
        "customers_note": "ग्राहक डेटा का भरोसेमंद मुफ़्त स्रोत अभी नहीं जुड़ा है",
    }
    if price and target:
        out["upside_to_target_pct"] = round((target / price - 1) * 100, 1)
    if price and hi and lo and hi > lo:
        out["position_in_52w_pct"] = round((price - lo) / (hi - lo) * 100, 1)
    return out


def fetch_stock_fundamentals(sym, price):
    try:
        info = yf.Ticker(sym).info or {}
        if price is None:
            price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
        return {"ok": True, **summarise_fundamentals(info, price)}
    except Exception as e:
        return {"ok": False, "error": f"कंपनी के आँकड़े नहीं मिले: {str(e)[:120]}"}



OPP_STOCKS = {
    "SUZLON": ("SUZLON.NS", "Suzlon Energy"),
    "DLINKINDIA": ("DLINKINDIA.NS", "D-Link (India)"),
    "VEDL": ("VEDL.NS", "Vedanta"),
    "APOLLOMICRO": ("APOLLO.NS", "Apollo Micro Systems"),
    "MSUMI": ("MSUMI.NS", "Motherson Sumi Wiring India"),
    "PARAS": ("PARAS.NS", "Paras Defence and Space Technologies"),
    "IOC": ("IOC.NS", "Indian Oil Corporation"),
    "GULPOLY": ("GULPOLY.NS", "Gulshan Polyols"),
    "GPPL": ("GPPL.NS", "Gujarat Pipavav Port"),
    "JAGRAN": ("JAGRAN.NS", "Jagran Prakashan"),
}
OPP_FACTORS = ["valuation", "growth", "profitability", "trend", "rsi", "analyst_upside"]


def _rsi14(closes):
    if len(closes) < 15:
        return None
    gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, len(closes))]
    ag = sum(gains[:14]) / 14
    al = sum(losses[:14]) / 14
    for i in range(14, len(gains)):
        ag = (ag * 13 + gains[i]) / 14
        al = (al * 13 + losses[i]) / 14
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


def _sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def opportunity_raw(sym):
    """एक स्टॉक के कच्चे आँकड़े (कोई खबर या भीड़ नहीं)। जो नहीं मिलता वह None।"""
    out = {"ok": False}
    try:
        t = yf.Ticker(sym)
        info = t.info or {}
        hist = t.history(period="1y", interval="1d")["Close"].dropna()
        closes = [float(x) for x in hist.tolist()]
        price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice")) or (closes[-1] if closes else None)
        pe = _num(info.get("trailingPE"))
        rg = _num(info.get("revenueGrowth"))
        eg = _num(info.get("earningsGrowth"))
        roe = _num(info.get("returnOnEquity"))
        om = _num(info.get("operatingMargins"))
        tgt = _num(info.get("targetMeanPrice"))
        s50, s200 = _sma(closes, 50), _sma(closes, 200)
        trend = None
        if price and s50 and s200:
            trend = (1 if price > s50 else 0) * 0.5 + (1 if price > s200 else 0) * 0.5
        growth_vals = [x for x in (rg, eg) if x is not None]
        prof_vals = [x for x in (roe, om) if x is not None]
        out.update({
            "ok": True,
            "price": round(price, 2) if price else None,
            "sector": info.get("sector") or "अज्ञात",
            "industry": info.get("industry") or "अज्ञात",
            "valuation": pe if (pe is not None and pe > 0) else None,
            "growth": (sum(growth_vals) / len(growth_vals)) if growth_vals else None,
            "growth_factor": (sum(growth_vals) / len(growth_vals)) if growth_vals else None,
            "profitability": (sum(prof_vals) / len(prof_vals)) if prof_vals else None,
            "trend": trend,
            "rsi": _rsi14(closes),
            "analyst_upside": ((tgt / price - 1) * 100) if (tgt and price) else None,
            "_holding": {
                "insiders_pct": round(_num(info.get("heldPercentInsiders")) * 100, 1) if _num(info.get("heldPercentInsiders")) is not None else None,
                "institutions_pct": round(_num(info.get("heldPercentInstitutions")) * 100, 1) if _num(info.get("heldPercentInstitutions")) is not None else None,
            },
        })
    except Exception as e:
        out["error"] = f"आँकड़े नहीं मिले: {str(e)[:120]}"
    return out


def _cr(v):
    """रुपये -> करोड़ (2 दशमलव)। नहीं मिला तो None।"""
    try:
        x = float(v)
        return round(x / 1e7, 2) if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _series_val(df, row_names):
    if df is None or getattr(df, "empty", True):
        return None
    for rn in row_names:
        if rn in df.index:
            return df.loc[rn]
    return None


def opportunity_extra(sym, market_1y, info_holding):
    """केवल वे आँकड़े जो सच में मिलें; बाकी कुछ नहीं जोड़ा जाता।"""
    out = {}
    try:
        t = yf.Ticker(sym)
        hist = t.history(period="1y", interval="1d")["Close"].dropna()
        if len(hist) >= 200 and float(hist.iloc[0]) > 0:
            out["return_1y_pct"] = round((float(hist.iloc[-1]) / float(hist.iloc[0]) - 1) * 100, 2)
        if market_1y is not None:
            out["market_1y_pct"] = market_1y

        q = None
        for attr in ("quarterly_financials", "quarterly_income_stmt"):
            try:
                q = getattr(t, attr)
                if q is not None and not q.empty:
                    break
            except Exception:
                q = None
        rev_q = _series_val(q, ["Total Revenue"])
        prf_q = _series_val(q, ["Net Income", "Net Income Common Stockholders"])
        quarters = []
        if q is not None and not q.empty:
            for c in list(q.columns)[:5]:
                r = _cr(rev_q[c]) if rev_q is not None else None
                pr = _cr(prf_q[c]) if prf_q is not None else None
                if r is None and pr is None:
                    continue
                quarters.append({"period": c.strftime("%b '%y"), "revenue_cr": r, "profit_cr": pr})
            quarters.reverse()
        if quarters:
            out["quarterly"] = quarters

        a = None
        for attr in ("financials", "income_stmt"):
            try:
                a = getattr(t, attr)
                if a is not None and not a.empty:
                    break
            except Exception:
                a = None
        rev_a = _series_val(a, ["Total Revenue"])
        prf_a = _series_val(a, ["Net Income", "Net Income Common Stockholders"])
        growth = {}
        def _vals(series):
            if series is None:
                return []
            return [float(series[c]) for c in series.index if series[c] == series[c]]
        rv, pv = _vals(rev_a), _vals(prf_a)
        if len(rv) >= 2 and rv[1] > 0:
            growth["revenue_1y_pct"] = round((rv[0] / rv[1] - 1) * 100, 1)
        if len(pv) >= 2 and pv[1] > 0:
            growth["profit_1y_pct"] = round((pv[0] / pv[1] - 1) * 100, 1)
        if len(rv) >= 4 and rv[0] > 0 and rv[3] > 0:
            growth["revenue_3y_cagr_pct"] = round(((rv[0] / rv[3]) ** (1 / 3) - 1) * 100, 1)
        if len(pv) >= 4 and pv[0] > 0 and pv[3] > 0:
            growth["profit_3y_cagr_pct"] = round(((pv[0] / pv[3]) ** (1 / 3) - 1) * 100, 1)
        if growth:
            out["growth"] = growth
    except Exception:
        pass

    holding = {k: v for k, v in info_holding.items() if v is not None}
    if holding:
        out["holding"] = holding
    return out


def _pct_rank(value, values, higher_is_better=True):
    """बाकी स्टॉक के मुकाबले 0–100 का स्थान। बराबर मान पर आधा अंक।"""
    if value is None or not values:
        return None
    if len(values) == 1:
        return 50.0
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    rank = (below + 0.5 * equal) / len(values) * 100
    return round(rank if higher_is_better else 100 - rank, 1)


def score_opportunities(raws):
    """हर वैक्टर का 0–100 स्कोर सूची के भीतर तुलना से। उपलब्ध वैक्टर का औसत = कुल स्कोर।
    RSI: कम RSI (ज़्यादा बिका हुआ) को ज़्यादा अंक; ज़्यादा RSI को कम अंक।"""
    spec = {
        "valuation": False,   # P/E कम हो तो बेहतर
        "growth": True,
        "profitability": True,
        "trend": True,
        "rsi": False,         # RSI कम हो तो बेहतर (ज़्यादा बिका)
        "analyst_upside": True,
    }
    ok = {k: v for k, v in raws.items() if v.get("ok")}
    for name, r in ok.items():
        scores = {}
        for f in OPP_FACTORS:
            source_key = "growth_factor" if f == "growth" else f
            vals = [x[source_key] for x in ok.values()
                    if isinstance(x.get(source_key), (int, float)) and math.isfinite(x[source_key])]
            scores[f] = _pct_rank(r.get(source_key), vals, spec[f])
        avail = [s for s in scores.values() if s is not None]
        r["scores"] = scores
        r["total"] = round(sum(avail) / len(avail), 1) if avail else None
        r["missing"] = [f for f in OPP_FACTORS if scores[f] is None]
    return raws


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


def build_levels(range_info):
    """Nifty के वॉच-स्तर और अंतिम बंद से उनकी दूरी (%)।"""
    if not range_info or not range_info.get("ok"):
        return []
    last = range_info["last_close"]
    out = []
    for lvl in NIFTY_WATCH_LEVELS:
        out.append({"level": lvl, "dist_pct": round((lvl / last - 1) * 100, 2)})
    return out


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


def match_relevant(query):
    """उभरती खोज को तभी स्वीकार करता है जब वह Nifty/Sensex से जुड़ी हो
    या हमारी वॉचलिस्ट के किसी स्टॉक से।"""
    q = query.lower()
    for stock, aliases in STOCK_ALIASES.items():
        if any(a in q for a in aliases):
            return True, stock
    if "nifty" in q or "sensex" in q or "निफ़्टी" in q or "सेंसेक्स" in q:
        return True, None
    return False, None


def crowd_decision(bull_pct_sum, bear_pct_sum):
    """भीड़ की सोच: EXTREMELY BULLISH / EXTREMELY BEARISH / NEUTRAL।
    Google Trends सापेक्ष खोज रुचि है, वास्तविक search count नहीं।"""
    if bull_pct_sum < MIN_SIDE_PCT or bear_pct_sum < MIN_SIDE_PCT:
        return None, "डेटा अपर्याप्त — NO TRADE"
    total = bull_pct_sum + bear_pct_sum
    pct = round(bull_pct_sum / total * 100)
    if pct >= CROWD_EXTREME:
        return pct, "EXTREMELY BULLISH"
    if pct <= CROWD_LOW:
        return pct, "EXTREMELY BEARISH"
    return pct, "NEUTRAL"


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _trends_request(py, terms, timeframe="now 7-d"):
    """एक Google Trends अनुरोध: ANCHOR + ज़्यादा से ज़्यादा 4 शब्द।"""
    py.build_payload([ANCHOR] + terms, timeframe=timeframe, geo="IN")
    df = py.interest_over_time()
    if df is None or df.empty:
        raise ValueError("Google से खाली डेटा मिला")
    return df[[ANCHOR] + terms].fillna(0)


def _ratio(df, term, recent_points=24):
    """शब्द की खोज nifty के अनुपात में हाल की अवधि और पूरे समय के औसत के रूप में।"""
    a_recent = float(df[ANCHOR].tail(recent_points).mean())
    a_avg = float(df[ANCHOR].mean())
    if a_recent <= 0 or a_avg <= 0:
        return 0.0, 0.0
    t_recent = float(df[term].tail(recent_points).mean())
    t_avg = float(df[term].mean())
    return t_recent / a_recent, t_avg / a_avg


def _period_ratio(df, term, day_str):
    """IST कैलेंडर दिन में शब्द की औसत रुचि / anchor की औसत रुचि (%); raw search count नहीं।"""
    idx = df.index
    try:
        if getattr(idx, "tz", None) is None:
            idx = idx.tz_localize("Asia/Kolkata")
        else:
            idx = idx.tz_convert("Asia/Kolkata")
        mask = idx.strftime("%Y-%m-%d") == day_str
        part = df.loc[mask]
        if part.empty:
            return None
        anchor_mean = float(part[ANCHOR].mean())
        if anchor_mean <= 0:
            return None
        return round(float(part[term].mean()) / anchor_mean * 100, 2)
    except Exception as e:
        print(f"daily Trends ratio error for {term}: {e}")
        return None


TQ_BASE_TERMS = ["nifty", "sensex"]
TQ_BULL_WORDS = ["target", "rally", "rise", "up", "high", "record", "buy", "bull", "bullish",
                 "jump", "surge", "gain", "teji", "tez", "badhega", "badhegi", "upar", "chadhega",
                 "टारगेट", "रैली", "तेज़ी", "तेजी", "उछाल", "ऊपर", "बुलिश", "खरीद", "बढ़ेगा", "बढ़ेगी"]
TQ_BEAR_WORDS = ["fall", "crash", "down", "drop", "low", "sell", "bear", "bearish", "slump",
                 "decline", "sell-off", "girawat", "girega", "giregi", "neeche", "mandi", "tutega",
                 "गिरावट", "गिरेगा", "गिरेगी", "नीचे", "मंदी", "बेयरिश", "बिकवाली", "टूटेगा"]
# सामान्य/दिशाहीन खोजों को स्पष्ट neutral bucket में रखें; अज्ञात queries को mood में न गिनें।
TQ_NEUTRAL_WORDS = ["today", "live", "price", "news", "chart", "index", "market", "stock",
                    "share", "sensex", "nifty", "what", "meaning", "history", "hours",
                    "आज", "भाव", "समाचार", "चार्ट", "शेयर", "बाजार", "बाज़ार", "निफ्टी", "सेंसेक्स"]
TQ_MIN_WEIGHT = 1.0  # दोनों दिशाओं में कम-से-कम इतना Trends weight जरूरी


def tq_dir(q):
    """खोज-वाक्यांश की दिशा: bull/bear/neutral; अस्पष्ट query को None रखें।"""
    text = str(q or "").lower()
    tk = set(re.findall(r"[\w\u0900-\u097F-]+", text))
    bull = any(w.lower() in tk for w in TQ_BULL_WORDS)
    bear = any(w.lower() in tk for w in TQ_BEAR_WORDS)
    if bull and not bear:
        return "bull"
    if bear and not bull:
        return "bear"
    if not bull and not bear and any(w.lower() in tk for w in TQ_NEUTRAL_WORDS):
        return "neutral"
    return None


def tq_weight(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 100.0  # 'Breakout' जैसे मान


def tq_aggregate(queries):
    """असली खोजें (related queries) -> भीड़ का मूड, स्कोर और सूचियाँ।"""
    bull_w = bear_w = 0.0
    crowd_terms, spikes = [], []
    for item in queries.values():
        d = tq_dir(item["term"])
        if d == "bull":
            bull_w += item["weight"]
        elif d == "bear":
            bear_w += item["weight"]
        if d:
            crowd_terms.append({"term": item["term"], "dir": d, "now": round(item["weight"], 1),
                                "avg": round(item["weight"], 1), "today_pct": None, "yesterday_pct": None})
        if item.get("rising"):
            ok, stock = match_relevant(item["term"])
            if ok:
                spikes.append({"query": item["term"], "value": str(round(item["weight"])), "stock": stock})
    crowd_terms.sort(key=lambda r: r["now"], reverse=True)
    if bull_w < TQ_MIN_WEIGHT or bear_w < TQ_MIN_WEIGHT:
        pct, label = None, "पर्याप्त खोज डेटा नहीं"
        bull_score = bear_score = neutral_score = None
        sentiment = "NO DATA"
    else:
        total = bull_w + bear_w
        pct = round(bull_w / total * 100)
        if pct >= CROWD_EXTREME:
            label = "ज़्यादातर बुलिश सोच"
        elif pct <= CROWD_LOW:
            label = "ज़्यादातर बियरिश सोच"
        else:
            label = "सोच बँटी हुई"
        bull_score = round(max(0.0, bull_w - bear_w) / total * 100, 1)
        bear_score = round(max(0.0, bear_w - bull_w) / total * 100, 1)
        neutral_score = round(max(0.0, 100.0 - bull_score - bear_score), 1)
        # Direction label compares bullish vs bearish search interest directly.
        # Residual neutral score measures strength/uncertainty; it is not a vote.
        sentiment = ("BULLISH" if bull_w > bear_w
                     else "BEARISH" if bear_w > bull_w else "NEUTRAL")
    rising_all = [it for it in queries.values() if it.get("rising")]
    return {
        "crowd_bull_pct": pct, "crowd_label": label,
        "bull_sum_pct": round(bull_w, 1), "bear_sum_pct": round(bear_w, 1),
        "min_side_pct": TQ_MIN_WEIGHT,
        "crowd_terms": crowd_terms[:20],
        "spikes": spikes[:10],
        "hidden_spikes": max(0, len(rising_all) - len(spikes)),
        "bull_score_pct": bull_score, "bear_score_pct": bear_score,
        "neutral_score_pct": neutral_score, "sentiment_label": sentiment,
        "today_bull_pct": None, "today_label": "डेटा उपलब्ध नहीं", "today_basis": "related_queries_7d",
        "yesterday_bull_pct": None, "yesterday_label": "कल का डेटा उपलब्ध नहीं",
        "queries_total": len(queries),
    }


def _trends_once(timeframe="now 7-d", recent_points=24):
    """Google Trends: anchor के साथ संतुलित bull/bear शब्दों की सापेक्ष रुचि।
    7-दिन डेटा अपर्याप्त हो तो caller 3-महीने के दैनिक डेटा पर fallback करता है।"""
    from pytrends.request import TrendReq

    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    py.build_payload(TQ_BASE_TERMS, timeframe=timeframe, geo="IN")
    base_df = py.interest_over_time()
    if base_df is None or base_df.empty:
        raise ValueError("Google Trends से खाली आधार डेटा मिला")
    base_df = base_df[TQ_BASE_TERMS].fillna(0)
    if float(base_df.values.max()) <= 0:
        raise ValueError("Google Trends का आधार डेटा शून्य है")
    source_data_time = None
    if timeframe == "now 1-d":
        # Google Trends का आख़िरी observation भी हाल का होना चाहिए;
        # केवल workflow का नया timestamp पुराने sample को नया नहीं बना सकता।
        last_value = base_df.index[-1]
        last_dt = last_value.to_pydatetime() if hasattr(last_value, "to_pydatetime") else last_value
        if last_dt.tzinfo is None:
            # pytrends converts Google's epoch-second timestamps with
            # pandas.to_datetime(..., unit="s"), which produces naive UTC.
            # Treating this as IST shifts the observation 5h30m backwards.
            last_dt = last_dt.replace(tzinfo=dt.timezone.utc)
        last_utc = last_dt.astimezone(dt.timezone.utc)
        age_minutes = (dt.datetime.now(dt.timezone.utc) - last_utc).total_seconds() / 60
        if age_minutes < -10 or age_minutes > 180:
            raise ValueError(f"Google Trends का आख़िरी observation {age_minutes:.0f} मिनट पुराना/भविष्य का है; ताज़ा डेटा नहीं")
        source_data_time = last_utc.isoformat()
    base = float(base_df.mean(axis=1).mean())
    recent = float(base_df.tail(recent_points).mean(axis=1).mean())
    attention = round(recent - base, 1)

    queries = {}
    for direction, terms in (("bull", BULL_TERMS), ("bear", BEAR_TERMS)):
        for chunk in _chunks(terms, TERM_CHUNK):
            df = _trends_request(py, chunk, timeframe=timeframe)
            for term in chunk:
                recent_ratio, average_ratio = _ratio(df, term, recent_points=recent_points)
                queries[term.lower()] = {
                    "term": term, "weight": round(max(0.0, recent_ratio) * 100, 2),
                    "avg_weight": round(max(0.0, average_ratio) * 100, 2),
                    "rising": False, "direction": direction
                }

    bull_total = sum(x["weight"] for x in queries.values() if x["direction"] == "bull")
    bear_total = sum(x["weight"] for x in queries.values() if x["direction"] == "bear")
    if bull_total < TQ_MIN_WEIGHT or bear_total < TQ_MIN_WEIGHT:
        raise ValueError(
            f"Google Trends में दोनों पक्षों का पर्याप्त डेटा नहीं "
            f"(bull={bull_total:.2f}, bear={bear_total:.2f}, minimum={TQ_MIN_WEIGHT})"
        )

    total = bull_total + bear_total
    bull_pct = round(bull_total / total * 100)
    bull_score = round(max(0.0, bull_total - bear_total) / total * 100, 1)
    bear_score = round(max(0.0, bear_total - bull_total) / total * 100, 1)
    neutral_score = round(max(0.0, 100.0 - bull_score - bear_score), 1)
    label = ("ज़्यादातर बुलिश सोच" if bull_pct >= CROWD_EXTREME
             else "ज़्यादातर बियरिश सोच" if bull_pct <= CROWD_LOW else "सोच बँटी हुई")
    # Classify direction from bullish vs bearish interest, not residual neutral score.
    sentiment = ("BULLISH" if bull_total > bear_total
                 else "BEARISH" if bear_total > bull_total else "NEUTRAL")

    crowd_terms = [{
        "term": x["term"], "dir": x["direction"], "now": x["weight"],
        "avg": x["avg_weight"], "today_pct": None, "yesterday_pct": None
    } for x in queries.values()]
    crowd_terms.sort(key=lambda x: x["now"], reverse=True)
    print(f"Google Trends validated ({timeframe}): bull={bull_total:.2f}, bear={bear_total:.2f}, crowd_bull={bull_pct}%")
    return {
        "ok": True, "unit": "anchor-relative points", "fear_vs_avg": attention,
        "crowd_bull_pct": bull_pct, "crowd_label": label,
        "bull_sum_pct": round(bull_total, 2), "bear_sum_pct": round(bear_total, 2),
        "min_side_pct": TQ_MIN_WEIGHT, "crowd_terms": crowd_terms[:20],
        "spikes": [], "hidden_spikes": 0,
        "bull_score_pct": bull_score, "bear_score_pct": bear_score,
        "neutral_score_pct": neutral_score, "sentiment_label": sentiment,
        "today_bull_pct": None, "today_label": "डेटा उपलब्ध नहीं",
        "today_basis": timeframe + "_anchor_relative", "source_timeframe": timeframe,
        "source_data_time": source_data_time,
        "yesterday_label": "कल का डेटा उपलब्ध नहीं",
        "queries_total": len(queries)
    }


def _trends_related_queries(timeframe="now 1-d"):
    """Google Trends की असली related searches से भीड़ का मूड निकालें।
    हर seed की अपनी 0-100 scale होती है, इसलिए पहले हर seed के भीतर प्रतिशत
    निकालकर फिर seed percentages का औसत लिया जाता है; अलग scales को सीधे नहीं जोड़ते।
    """
    from pytrends.request import TrendReq

    seeds = ["nifty", "sensex", "share market", "stock market"]
    py = TrendReq(hl="en-IN", tz=-330, timeout=(10, 25))
    py.build_payload(seeds, timeframe=timeframe, geo="IN")
    related = py.related_queries()
    per_seed = []
    all_terms = {}

    for seed in seeds:
        pack = (related or {}).get(seed) or {}
        top = pack.get("top")
        if top is None or top.empty or "query" not in top or "value" not in top:
            continue

        bull = bear = neutral = 0.0
        rows = 0
        for _, row in top.iterrows():
            term = str(row.get("query", "")).strip()
            if not term:
                continue
            try:
                weight = float(row.get("value", 0) or 0)
            except (TypeError, ValueError):
                continue
            if weight <= 0:
                continue
            direction = tq_dir(term)
            # अनजान/general queries को mood प्रतिशत में न मिलाएँ; केवल पहचानी दिशा गिनें।
            if direction is None:
                continue
            rows += 1
            if direction == "bull":
                bull += weight
            elif direction == "bear":
                bear += weight
            else:
                neutral += weight
            key = term.casefold()
            entry = {"term": term, "weight": weight, "direction": direction}
            if key not in all_terms or weight > all_terms[key]["weight"]:
                all_terms[key] = entry

        total = bull + bear + neutral
        if rows >= 3 and total > 0:
            per_seed.append((bull / total * 100, bear / total * 100, neutral / total * 100))

    if len(per_seed) < 2:
        raise ValueError("Google Trends related searches में कम-से-कम 2 विषयों का पर्याप्त वर्गीकृत डेटा नहीं मिला")

    bull_pct = round(sum(x[0] for x in per_seed) / len(per_seed), 1)
    bear_pct = round(sum(x[1] for x in per_seed) / len(per_seed), 1)
    neutral_pct = round(sum(x[2] for x in per_seed) / len(per_seed), 1)
    if bull_pct < TQ_MIN_WEIGHT or bear_pct < TQ_MIN_WEIGHT:
        raise ValueError(
            f"Google Trends में दोनों दिशाओं की पर्याप्त खोज नहीं "
            f"(bull={bull_pct:.1f}%, bear={bear_pct:.1f}%, minimum={TQ_MIN_WEIGHT}%)"
        )
    if bull_pct >= CROWD_EXTREME:
        label, sentiment = "EXTREMELY BULLISH", "BULLISH"
    elif bear_pct >= CROWD_EXTREME:
        label, sentiment = "EXTREMELY BEARISH", "BEARISH"
    else:
        label, sentiment = "NEUTRAL", "NEUTRAL"

    terms = []
    for item in all_terms.values():
        terms.append({
            "term": item["term"], "dir": item["direction"],
            "now": round(item["weight"], 1), "avg": round(item["weight"], 1),
            "today_pct": None, "yesterday_pct": None
        })
    terms.sort(key=lambda x: x["now"], reverse=True)

    return {
        "ok": True, "unit": "Google Trends related-query share (%)",
        "crowd_bull_pct": round(bull_pct), "crowd_label": label,
        "bull_sum_pct": bull_pct, "bear_sum_pct": bear_pct,
        "min_side_pct": None, "crowd_terms": terms[:20],
        "spikes": [], "hidden_spikes": 0,
        "bull_score_pct": bull_pct, "bear_score_pct": bear_pct,
        "neutral_score_pct": neutral_pct, "sentiment_label": sentiment,
        "today_bull_pct": bull_pct, "today_label": "पिछले 24 घंटे की related searches",
        "today_basis": "related_queries_7d",
        "source_timeframe": timeframe + " related queries",
        "fallback_used": False, "queries_total": len(all_terms),
        "related_seed_count": len(per_seed)
    }


def fetch_trends():
    """पहले पिछले 24 घंटे का Google Trends डेटा लें।
    7-दिन/3-महीने के नमूने ऐतिहासिक संदर्भ हैं, आज का crowd mood नहीं।"""
    try:
        import pytrends  # noqa: F401
    except Exception as e:
        return {"ok": False, "error": f"pytrends नहीं मिला: {e}"}

    last_err = ""
    # प्राथमिक स्रोत: Google Trends का now 1-d डेटा।
    for attempt in range(TRENDS_RETRIES):
        try:
            result = _trends_related_queries(timeframe="now 1-d")
            result.setdefault("fear_vs_avg", None)
            result.setdefault("per_term", [])
            result["fallback_used"] = False
            result["today_bull_pct"] = result["crowd_bull_pct"]
            result["today_label"] = "पिछले 24 घंटे की Google Trends खोज-रुचि"
            result["today_basis"] = "now_1d_anchor_relative"
            result["source_timeframe"] = "now 1-d"
            return result
        except Exception as e:
            last_err = str(e)
            print(f"Google Trends now 1-d attempt {attempt + 1} failed: {last_err}")
            if attempt < TRENDS_RETRIES - 1:
                rate_limited = "429" in last_err or "too many requests" in last_err.lower()
                time.sleep(120 if rate_limited else 45)

    # पुराने 7-दिन/related-query स्कोर को live mood बनाकर कभी न दिखाएँ।
    return {
        "ok": False, "stale": False,
        "error": f"पिछले 24 घंटे का नया Google Trends डेटा नहीं मिला: {last_err}"
    }


def update_crowd(events, crowd_pct, today_str, nifty_ret):
    """भीड़ एकतरफ़ा हो तो उस दिन दर्ज करें। अगले सत्र की Nifty चाल से नतीजा भरें।
    crowd_pct None हो (पर्याप्त डेटा नहीं) तो कुछ दर्ज नहीं होता।"""
    if crowd_pct is not None and (crowd_pct >= CROWD_EXTREME or crowd_pct <= CROWD_LOW) and not SKIP_EVENTS:
        key = f"{today_str}|crowd"
        if not any(e["key"] == key for e in events):
            events.append({
                "key": key, "date": today_str,
                "direction": "bull" if crowd_pct >= CROWD_EXTREME else "bear",
                "crowd_pct": crowd_pct, "next_change": None, "outcome": None,
            })

    for e in events:
        if e.get("outcome") is not None:
            continue
        later = sorted(d for d in nifty_ret if d > e["date"])
        if not later:
            continue
        nxt = nifty_ret[later[0]]
        e["next_change"] = nxt
        crowd_up = e["direction"] == "bull"
        price_up = nxt >= 0
        e["outcome"] = "followed" if crowd_up == price_up else "trap"


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

def trends_within_freshness(data, now_utc=None):
    """Google Trends fetch timestamp की उम्र जाँचें; पुराना डेटा कभी ताज़ा न मानें।"""
    if not data or not data.get("ok") or not data.get("as_of"):
        return False
    try:
        stamp = dt.datetime.fromisoformat(str(data["as_of"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        now = now_utc or dt.datetime.now(dt.timezone.utc)
        age_minutes = (now - stamp.astimezone(dt.timezone.utc)).total_seconds() / 60
        return -5 <= age_minutes <= TRENDS_MAX_AGE_MINUTES
    except (TypeError, ValueError):
        return False



def market_closed_today():
    """भारतीय बाज़ार आज बंद है? (सप्ताहांत, सूची में दी गई छुट्टी, या शाम 4 बजे के बाद
    भी आज का NIFTY बार न होना)। सुबह की छुट्टी सूची के बिना नहीं पकड़ी जा सकती।"""
    ist = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)
    today = ist.date().isoformat()
    if today in NSE_HOLIDAYS or ist.weekday() >= 5:
        return True
    if ist.hour < 16:
        return False
    try:
        h = yf.Ticker("^NSEI").history(period="5d", interval="1d")
        dates = {d.date().isoformat() for d in h.index}
        return today not in dates
    except Exception as e:
        print(f"market status check failed: {e}")
        return False


STOCK_REFRESH_HOURS_IST = (10, 16)


def stock_refresh_slot(now_utc):
    """अभी की स्टॉक-विश्लेषण स्लॉट (IST 10:00 या 16:00 में से पिछली)। इससे पहले का स्लॉट कल का होता है।"""
    ist = (now_utc + dt.timedelta(hours=5, minutes=30)).replace(tzinfo=None)
    slots = []
    for day_off in (0, -1):
        day = (ist + dt.timedelta(days=day_off)).date()
        for h in STOCK_REFRESH_HOURS_IST:
            slots.append(dt.datetime(day.year, day.month, day.day, h))
    past = [x for x in slots if x <= ist]
    return max(past).isoformat() if past else None


def retail_adjust(po):
    """रिटेल (CLIENT) की इंडेक्स ऑप्शन स्थिति से स्कोर का समायोजन (-2 से +2)।
    CE का Long हिस्सा PE के Long हिस्से से जितना ज़्यादा, उतना बुलिश। (CE% − PE%) ÷ 10, सीमा ±2।
    यह कल का (EOD) डेटा है। न मिले तो 0।"""
    if not po or not po.get("ok"):
        return 0.0, None
    c = (po.get("participants") or {}).get("CLIENT") or {}
    def share(l, sh):
        l, sh = c.get(l), c.get(sh)
        if l is None or sh is None or (l + sh) <= 0:
            return None
        return round(l / (l + sh) * 100, 1)
    ce = share("index_call_long", "index_call_short")
    pe = share("index_put_long", "index_put_short")
    if ce is None or pe is None:
        return 0.0, None
    adj = round(max(-2.0, min(2.0, (ce - pe) / 10)), 2)
    bias = "Bullish" if adj > 0 else ("Bearish" if adj < 0 else "Neutral")
    return adj, {"ce_pct": ce, "pe_pct": pe, "bias": bias, "date": po.get("date"), "adj": adj}


def participant_changes(today, prev):
    """आज और पिछले उपलब्ध दिन के NSE participant आँकड़ों का अंतर (बदलाव)।
    पिछला दिन data.json से लिया जाता है; उसी तारीख का हो तो कुछ नहीं बनता।"""
    if not today.get("ok") or not prev.get("ok") or prev.get("date") == today.get("date"):
        return {"ok": False, "prev_date": None, "by_group": {}}
    P, Q = today.get("participants", {}), prev.get("participants", {})
    keys = ["future_index_long", "future_index_short", "index_call_long",
            "index_call_short", "index_put_long", "index_put_short"]
    out = {}
    for grp in ["FII", "DII", "PRO", "CLIENT"]:
        if grp in P and grp in Q:
            d = {}
            for k in keys:
                a, b = P[grp].get(k), Q[grp].get(k)
                d[k] = (a - b) if (a is not None and b is not None) else None
            out[grp] = d
    return {"ok": bool(out), "prev_date": prev.get("date"), "by_group": out}


def main():
    global SKIP_EVENTS
    refresh_mcx_silver_reference()
    refresh_mcx_gold_reference()
    now_utc = dt.datetime.now(dt.timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")
    updated = now_utc.isoformat(timespec="minutes").replace("+00:00", "Z")
    events = load_json(EVENTS_FILE, [])
    crowd_events = load_json(CROWD_FILE, [])
    div_events = load_json(DIV_FILE, [])
    sig_state = load_json(SIG_STATE_FILE, {})
    sig_log = load_json(SIG_LOG_FILE, [])
    previous = load_json(DATA_FILE, {})

    result = {"updated": updated, "instruments": {}, "market_closed": SKIP_EVENTS}
    all_returns = {}
    SKIP_EVENTS = market_closed_today()

    for name, (sym, query) in INDEXES.items():
        process(name, sym, query, "index", events, today_str, result["instruments"],
                div_events, all_returns)

    for name, (sym, query) in STOCKS.items():
        process(name, sym, query, "stock", events, today_str, result["instruments"],
                div_events, all_returns)

    # संकेत-बदलाव: CRUDEOIL और DJI के लिए
    update_signals(result["instruments"], sig_state, sig_log, updated)

    result["signals"] = {
        "state": signal_summary(sig_state),
        "events": sig_log[-15:],
        "watch": list(SIGNAL_WATCH.keys()),
    }

    result["contrarian"] = {
        "events": events[-30:],
        "tracked": len([e for e in events if e["outcome"]]),
        "reversed": len([e for e in events if e["outcome"] == "reversed"]),
        "continued": len([e for e in events if e["outcome"] == "continued"]),
    }

    div_done = [e for e in div_events if e.get("outcome")]
    result["divergence"] = {
        "tracked": len(div_done),
        "sentiment": len([e for e in div_done if e["outcome"] == "sentiment"]),
        "price": len([e for e in div_done if e["outcome"] == "price"]),
        "events": div_events[-12:],
    }

    try:
        slot_now = stock_refresh_slot(now_utc)
        prev_sa = previous.get("stock_analysis") or {}
        expected_keys = set(STOCKS.keys()) | set(OPP_STOCKS.keys())
        if (prev_sa and slot_now and previous.get("stock_analysis_slot") == slot_now
                and set(prev_sa.keys()) == expected_keys):
            # इसी स्लॉट का डेटा पहले से है: कंपनी के आँकड़े दोबारा नहीं माँगते
            result["stock_analysis"] = prev_sa
            result["stock_analysis_slot"] = slot_now
            result["stock_analysis_as_of"] = previous.get("stock_analysis_as_of")
        else:
            result["stock_analysis"] = {}
            sector_universe = {k: (v[0], v[1]) for k, v in STOCKS.items()}
            for k, (sym, _n) in OPP_STOCKS.items():
                sector_universe[k] = (sym, _n)
            for name, (sym, _q) in sector_universe.items():
                price = result["instruments"].get(name, {}).get("price")
                result["stock_analysis"][name] = fetch_stock_fundamentals(sym, price)
            result["stock_analysis_slot"] = slot_now
            result["stock_analysis_as_of"] = updated
        prev_opp = previous.get("opportunity") or {}
        if prev_opp and slot_now and previous.get("opportunity_slot") == slot_now:
            result["opportunity"] = prev_opp
            result["opportunity_slot"] = slot_now
            result["opportunity_as_of"] = previous.get("opportunity_as_of")
        else:
            market_1y = None
            try:
                mh = yf.Ticker("^NSEI").history(period="1y", interval="1d")["Close"].dropna()
                if len(mh) >= 200 and float(mh.iloc[0]) > 0:
                    market_1y = round((float(mh.iloc[-1]) / float(mh.iloc[0]) - 1) * 100, 2)
            except Exception:
                market_1y = None
            raws = {k: opportunity_raw(sym) for k, (sym, _n) in OPP_STOCKS.items()}
            for k, (sym, _n) in OPP_STOCKS.items():
                r = raws[k]
                holding = r.pop("_holding", {}) if isinstance(r, dict) else {}
                if r.get("ok"):
                    r.update(opportunity_extra(sym, market_1y, holding))
            score_opportunities(raws)
            for k, r in raws.items():
                r.pop("growth_factor", None)  # scoring-only field; keep Dashboard growth details unchanged
                r["name"] = OPP_STOCKS[k][1]
            result["opportunity"] = raws
            result["opportunity_slot"] = slot_now
            result["opportunity_as_of"] = updated
    except Exception as e:
        print(f"stock and opportunity analysis skipped: {e}")
        result.setdefault("stock_analysis", {})
        result.setdefault("opportunity", {})
    result["range"] = nifty_range()
    result["levels"] = build_levels(result["range"])

    # संयुक्त इंडेक्स समाचार में समान/मिलते-जुलते शीर्षक को एक ही बार गिनें।
    # हर कार्ड का अपना समाचार और स्कोर अलग रहता है; यह केवल कुल भावना सारांश है।
    index_heads = []
    for index_name in ("NIFTY", "SENSEX", "BANKNIFTY"):
        index_heads.extend(result["instruments"].get(index_name, {}).get("headlines", []))
    unique_index_heads = dedupe_heads(index_heads)
    idx_pos = sum(1 for h in unique_index_heads if h.get("score", 0) > 0)
    idx_neg = sum(1 for h in unique_index_heads if h.get("score", 0) < 0)
    result["headline_split"] = {
        "pos": idx_pos, "neg": idx_neg,
        "unique_headlines": len(unique_index_heads),
        "scope": "NIFTY+SENSEX+BANKNIFTY; duplicate titles removed",
    }

    fii = pick_with_fallback(fetch_fii_dii(), previous.get("fii_dii") or {})
    if fii.get("ok") and not fii.get("stale"):
        fii["as_of_run"] = updated
    result["fii_dii"] = fii
    # NSE participant-wise OI daily EOD data है, live feed नहीं।
    # आज उपलब्ध नवीनतम archive से पहले की तारीख का archive अलग fetch करें,
    # ताकि बार-बार उसी दिन का data.json snapshot होने पर भी daily change न खोए।
    participant_today = fetch_participant_oi()
    prior_snapshot = {}
    if participant_today.get("ok") and participant_today.get("date"):
        try:
            target_prev = dt.date.fromisoformat(participant_today["date"]) - dt.timedelta(days=1)
            prior_snapshot = fetch_participant_oi(base_date=target_prev)
        except (TypeError, ValueError):
            prior_snapshot = {}
    # अगर NSE का पिछला archive अस्थायी रूप से उपलब्ध न हो, तो केवल सही पुराना
    # snapshot fallback में लें; समान/नई तारीख को पिछला दिन न मानें।
    if not prior_snapshot.get("ok"):
        candidates = [
            previous.get("participant_oi_previous_day") or {},
            previous.get("participant_oi") or {},
        ]
        today_date = participant_today.get("date") or ""
        prior_snapshot = next(
            (p for p in candidates if p.get("ok") and p.get("date") and p.get("date") < today_date),
            {}
        )
    # तीसरे बॉक्स की तारीख भी NSE archive से लें, weekday अनुमान से नहीं।
    # इससे NSE holidays के बाद भी तारीख सही रहेगी।
    prior_prior_snapshot = {}
    if prior_snapshot.get("ok") and prior_snapshot.get("date"):
        try:
            target_two_days_ago = dt.date.fromisoformat(prior_snapshot["date"]) - dt.timedelta(days=1)
            prior_prior_snapshot = fetch_participant_oi(base_date=target_two_days_ago)
        except (TypeError, ValueError):
            prior_prior_snapshot = {}
    if not prior_prior_snapshot.get("ok"):
        cached_two_days_ago = previous.get("participant_oi_two_days_ago") or {}
        if (cached_two_days_ago.get("ok") and cached_two_days_ago.get("date")
                and cached_two_days_ago.get("date") < (prior_snapshot.get("date") or "")):
            prior_prior_snapshot = cached_two_days_ago
    participant_today["two_days_ago_date"] = prior_prior_snapshot.get("date") if prior_prior_snapshot.get("ok") else None

    result["participant_oi"] = participant_today
    result["participant_oi_previous_day"] = prior_snapshot
    result["participant_oi_two_days_ago"] = prior_prior_snapshot
    result["participant_oi"]["changes"] = participant_changes(
        participant_today, prior_snapshot)
    adj, rinfo = retail_adjust(result["participant_oi"])
    for _n in ("NIFTY", "SENSEX", "BANKNIFTY"):
        _d = result["instruments"].get(_n)
        if _d and rinfo is not None:
            _d["headline_score"] = _d["score"]
            _d["retail_adj"] = adj
            _d["score"] = round(_d["score"] + adj, 1)
    result["retail_mood"] = rinfo

    market_news = pick_with_fallback(fetch_market_news(), previous.get("market_news") or {})
    if market_news.get("ok") and not market_news.get("stale"):
        market_news["as_of"] = updated
    result["market_news"] = market_news

    # Google Trends केवल तय समय पर चलाएँ: 09:10, 12:30 और 21:00 IST.
    # बाकी हर 30-मिनट वाले PDMP रन में पिछली रीडिंग को दोबारा fetch न करें।
    previous_trends = previous.get("trends") or {}
    previous_crowd_terms = previous_trends.get("crowd_terms") or []
    previous_trends_all_zero = (
        not previous_crowd_terms
        or all(float(p.get("now", 0) or 0) == 0 and float(p.get("avg", 0) or 0) == 0
               for p in previous_crowd_terms)
        or (float(previous_trends.get("bull_sum_pct", 0) or 0) == 0
            and float(previous_trends.get("bear_sum_pct", 0) or 0) == 0)
    )
    previous_trends_has_scores = all(
        previous_trends.get(k) is not None
        for k in ("bull_score_pct", "bear_score_pct", "neutral_score_pct")
    )
    trends_scan = os.getenv("TRENDS_SCAN", "false").lower() == "true"

    if trends_scan:
        # अगर इसी retry-window में पहले ही नई reading मिल चुकी है, तो अनावश्यक
        # Google अनुरोध न करें। असफल/पुरानी reading पर अगला scheduled retry फिर चलेगा।
        recent_success = (
            previous_trends.get("ok")
            and previous_trends_has_scores
            and not previous_trends_all_zero
            and trends_within_freshness(previous_trends, now_utc)
        )
        recent_age_minutes = None
        if recent_success:
            try:
                _stamp = dt.datetime.fromisoformat(str(previous_trends.get("as_of")).replace("Z", "+00:00"))
                if _stamp.tzinfo is None:
                    _stamp = _stamp.replace(tzinfo=dt.timezone.utc)
                recent_age_minutes = (now_utc - _stamp.astimezone(dt.timezone.utc)).total_seconds() / 60
            except (TypeError, ValueError):
                recent_age_minutes = None

        if recent_age_minutes is not None and -5 <= recent_age_minutes <= 90:
            trends = dict(previous_trends)
            trends["stale"] = False
            trends["cached"] = True
            trends["retry_skipped"] = True
            trends["refresh_policy_hours"] = None
            print(f"Google Trends retry skipped: successful reading is only {recent_age_minutes:.0f} minutes old")
        else:
            # नया डेटा ही स्वीकारें; असफलता पर पिछली reading को ताज़ा बताकर न दिखाएँ।
            fresh_trends = fetch_trends()
            if fresh_trends.get("ok"):
                trends = fresh_trends
                trends["stale"] = False
                trends["as_of"] = updated
                trends["cached"] = False
                trends["refresh_policy_hours"] = None
            else:
                trends = {
                    "ok": False, "stale": False, "cached": False,
                    "error": fresh_trends.get("error", "Google Trends की नई reading उपलब्ध नहीं")
                }
    elif previous_trends.get("ok") and previous_trends_has_scores and not previous_trends_all_zero:
        if trends_within_freshness(previous_trends, now_utc):
            trends = dict(previous_trends)
            trends["cached"] = True
            trends["stale"] = False
            trends["refresh_policy_hours"] = None
        else:
            trends = {
                "ok": False, "stale": True, "cached": False,
                "error": f"आख़िरी सफल Google Trends reading {TRENDS_MAX_AGE_MINUTES} मिनट से पुरानी है; पुराना मूड छिपाया गया"
            }
    else:
        trends = {
            "ok": False, "stale": False, "cached": False,
            "error": "नई Google Trends reading उपलब्ध नहीं; अगला तय स्कैन आने पर जाँच होगी"
        }
    result["trends"] = trends

    fresh_trends = trends.get("ok") and not trends.get("stale")
    crowd_pct = trends.get("crowd_bull_pct") if fresh_trends else None
    nifty_ret = all_returns.get("NIFTY") or {}
    update_crowd(crowd_events, crowd_pct, today_str, nifty_ret)
    done = [e for e in crowd_events if e.get("outcome")]
    result["crowd_stats"] = {
        "tracked": len(done),
        "trap": len([e for e in done if e["outcome"] == "trap"]),
        "followed": len([e for e in done if e["outcome"] == "followed"]),
        "events": crowd_events[-10:],
    }

    result = clean(result)
    events = clean(events)
    crowd_events = clean(crowd_events)
    div_events = clean(div_events)
    sig_state = clean(sig_state)
    sig_log = clean(sig_log)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(CROWD_FILE, "w", encoding="utf-8") as f:
        json.dump(crowd_events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(DIV_FILE, "w", encoding="utf-8") as f:
        json.dump(div_events, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(SIG_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sig_state, f, ensure_ascii=False, indent=2, allow_nan=False)
    with open(SIG_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(sig_log, f, ensure_ascii=False, indent=2, allow_nan=False)

    write_header = not os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["time_utc", "instrument", "change_pct", "score"])
        for name, d in result["instruments"].items():
            w.writerow([result["updated"], name, d["change_pct"], d["score"]])


if __name__ == "__main__":
    main()
