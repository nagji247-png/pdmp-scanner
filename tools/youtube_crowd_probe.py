#!/usr/bin/env python3
"""Isolated YouTube crowd-attention probe. Never writes production dashboard data."""
from __future__ import annotations
import json, os, re, sys, time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API = "https://www.googleapis.com/youtube/v3"
ASSETS = {
    "NIFTY": "Nifty 50 OR Nifty market",
    "SENSEX": "Sensex market",
    "BANKNIFTY": "Bank Nifty",
    "GOLD": "India gold price OR MCX gold",
    "SILVER": "India silver price OR MCX silver",
    "CRUDEOIL": "MCX crude oil OR crude oil India",
}
BULL = ["bullish", "rise", "rising", "rally", "recovery", "breakout", "upside", "higher", "तेजी", "बढ़ेगा", "बढ़त", "उछाल", "ऊपर जाएगा", "खरीदारी"]
BEAR = ["bearish", "fall", "falling", "crash", "correction", "downside", "selloff", "lower", "गिरावट", "गिरेगा", "नीचे जाएगा", "मंदी", "बिकवाली"]
NEUTRAL = ["sideways", "range bound", "range-bound", "consolidation", "wait and watch", "स्थिर", "सीमित दायरा"]

def api_get(resource: str, params: dict, key: str) -> dict:
    query = urlencode({**params, "key": key})
    req = Request(f"{API}/{resource}?{query}", headers={"Accept": "application/json", "User-Agent": "TrinetraResearchProbe/1.0"})
    try:
        with urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError("YOUTUBE_API_RATE_LIMIT_429") from exc
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"YouTube API HTTP {exc.code}: {body}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"YouTube API network error: {exc}") from exc

def classify(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").lower())
    b = sum(1 for term in BULL if term in s)
    r = sum(1 for term in BEAR if term in s)
    n = sum(1 for term in NEUTRAL if term in s)
    if b == r == n == 0 or (b == r):
        return "NEUTRAL"
    if b > r and b > n:
        return "BULLISH"
    if r > b and r > n:
        return "BEARISH"
    return "NEUTRAL"

def main() -> int:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        print(json.dumps({"status":"blocked","reason":"YOUTUBE_API_KEY secret is not configured","production_write":False}, indent=2))
        return 2
    collected = {}
    all_ids = []
    try:
        # Six search.list calls per run: deliberately manual/low-frequency.
        for asset, query in ASSETS.items():
            data = api_get("search", {"part":"snippet", "type":"video", "q":query, "regionCode":"IN", "relevanceLanguage":"hi", "order":"date", "maxResults":10}, key)
            videos = []
            for item in data.get("items", []):
                vid = item.get("id", {}).get("videoId")
                sn = item.get("snippet", {})
                if not vid: continue
                all_ids.append(vid)
                videos.append({"video_id":vid, "title":sn.get("title",""), "description":sn.get("description","")[:3000],
                    "channel":sn.get("channelTitle",""), "published_at":sn.get("publishedAt"),
                    "metadata_direction":classify((sn.get("title","") + " " + sn.get("description",""))),
                    "transcript_status":"NOT_AVAILABLE_VIA_PUBLIC_DATA_API"})
            collected[asset] = videos
        stats = {}
        if all_ids:
            for i in range(0, len(all_ids), 50):
                batch = api_get("videos", {"part":"statistics,contentDetails", "id":",".join(all_ids[i:i+50])}, key)
                for item in batch.get("items", []):
                    stats[item["id"]] = item.get("statistics", {})
        # At most one comments request per asset (top recent video only).
        for asset, videos in collected.items():
            if not videos: continue
            try:
                cm = api_get("commentThreads", {"part":"snippet", "videoId":videos[0]["video_id"], "maxResults":20, "order":"time", "textFormat":"plainText"}, key)
                comments = []
                for item in cm.get("items", []):
                    c = item.get("snippet",{}).get("topLevelComment",{}).get("snippet",{})
                    comments.append({"text":c.get("textDisplay","")[:1500], "like_count":c.get("likeCount",0), "published_at":c.get("publishedAt")})
                videos[0]["recent_comments"] = comments
                videos[0]["comment_direction_counts"] = {d:sum(classify(c["text"])==d for c in comments) for d in ("BULLISH","BEARISH","NEUTRAL")}
            except RuntimeError as exc:
                videos[0]["comments_status"] = str(exc)
        for videos in collected.values():
            for v in videos:
                st = stats.get(v["video_id"], {})
                v["view_count"] = int(st.get("viewCount",0) or 0)
                v["like_count"] = int(st.get("likeCount",0) or 0)
                v["comment_count"] = int(st.get("commentCount",0) or 0)
        result = {"status":"ok", "provider":"YouTube Data API v3", "geo":"IN", "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
            "assets":{}, "limits":{"search_list_calls":6,"video_statistics_calls":(len(all_ids)+49)//50,"comments_calls_max":6},
            "transcript_note":"Public video transcripts are not exposed by the YouTube Data API. No transcript is fabricated or scraped.",
            "sentiment_note":"Keyword-based preliminary classification only; not a reliable speaker-intent model. Views/likes are not treated as sentiment.",
            "production_write":False}
        for asset, videos in collected.items():
            counts = {d:sum(v["metadata_direction"]==d for v in videos) for d in ("BULLISH","BEARISH","NEUTRAL")}
            result["assets"][asset] = {"video_count":len(videos),"metadata_direction_counts":counts,"videos":videos}
        os.makedirs("youtube_probe_output", exist_ok=True)
        with open("youtube_probe_output/youtube_crowd_probe.json","w",encoding="utf-8") as f:
            json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps({"status":"ok","asset_video_counts":{a:x["video_count"] for a,x in result["assets"].items()},
            "search_list_calls":6,"production_write":False,"output":"youtube_probe_output/youtube_crowd_probe.json"},ensure_ascii=False,indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"status":"unavailable","reason":str(exc),"production_write":False},indent=2))
        return 1

if __name__ == "__main__":
    sys.exit(main())
