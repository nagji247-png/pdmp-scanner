#!/usr/bin/env python3
"""One-asset proof of concept: export Google Trends CSV through the public UI.

This deliberately uses the Google Trends website, not pytrends/private endpoints.
It is diagnostic-only and never writes dashboard data.json or changes scores.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ASSET = "NIFTY"
TERMS = ["nifty", "nifty breakout", "nifty crash", "nifty sideways"]
OUT = Path("google-trends-browser-probe")
OUT.mkdir(exist_ok=True)
CSV_PATH = OUT / "nifty-google-trends.csv"
JSON_PATH = OUT / "google-trends-browser-probe.json"


def result(status: str, reason: str, **extra):
    payload = {
        "asset": ASSET,
        "provider": "Google Trends website CSV export",
        "geo": "IN",
        "timeframe": "now 1-d",
        "terms": TERMS,
        "status": status,
        "reason": reason,
        "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        **extra,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if status == "available" else 2


def parse_export(path: Path):
    rows = list(csv.reader(path.open(encoding="utf-8-sig", newline="")))
    header_index = None
    expected = {term.lower() for term in TERMS}
    for index, row in enumerate(rows):
        cells = [cell.strip().lower() for cell in row]
        if cells and cells[0] in ("time", "week", "day") and expected.issubset(set(cells[1:])):
            header_index = index
            break
    if header_index is None:
        raise ValueError("CSV export मिला, लेकिन अपेक्षित Time + चारों query columns नहीं मिले")
    header = [cell.strip() for cell in rows[header_index]]
    observations = []
    for row in rows[header_index + 1:]:
        if len(row) < len(header):
            continue
        date_value = row[0].strip()
        if not date_value or date_value.lower().startswith(("note:", "category:")):
            continue
        values = {}
        for term in TERMS:
            try:
                values[term] = float(row[header.index(term)])
            except (ValueError, KeyError):
                values[term] = None
        observations.append({"time": date_value, "interest": values})
    if not observations:
        raise ValueError("CSV में कोई वास्तविक Interest observation नहीं मिला")
    return observations


def main():
    query = ",".join(TERMS)
    url = "https://trends.google.com/trends/explore?" + urlencode({
        "date": "now 1-d", "geo": "IN", "q": query
    })
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(accept_downloads=True, locale="en-IN")
        page = context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(12000)
            body = (page.locator("body").inner_text(timeout=10000) or "").lower()
            if response and response.status in (429, 403):
                return result("unavailable", f"Google Trends website HTTP {response.status}")
            if any(token in body for token in ("unusual traffic", "automated queries", "captcha", "sorry")):
                return result("unavailable", "Google ने browser session पर anti-automation/challenge दिखाया")
            if "interest over time" not in body:
                return result("unavailable", "Google Trends chart load नहीं हुआ; page पर Interest over time नहीं मिला",
                              page_title=page.title(), http_status=response.status if response else None)
            try:
                button = page.get_by_role("button", name=re.compile("download", re.I)).first
                with page.expect_download(timeout=20000) as download_info:
                    button.click(timeout=10000)
                download = download_info.value
                download.save_as(str(CSV_PATH))
            except PlaywrightTimeoutError:
                return result("unavailable", "Google Trends UI पर CSV download button/response उपलब्ध नहीं हुआ",
                              page_title=page.title(), http_status=response.status if response else None)
            observations = parse_export(CSV_PATH)
            return result("available", "Google Trends website से CSV export और चारों query columns सत्यापित",
                          source_url=url, http_status=response.status if response else None,
                          observation_count=len(observations), observations=observations)
        except Exception as exc:
            return result("unavailable", f"{type(exc).__name__}: {str(exc)[:240]}")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
