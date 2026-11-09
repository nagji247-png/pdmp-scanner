"""Fetch and validate official index constituent rosters once per week.

NSE lists provide Symbol + ISIN directly. BSE SENSEX publishes BSE scrip codes;
those codes are joined to the same-date official BSE CM UDiFF cash archive to
obtain ISIN. No guessed symbol mapping and no third-party roster fallback.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from html.parser import HTMLParser
import io
import json
import re
from pathlib import Path

import requests

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
ROSTER_PATH = Path("index_constituent_rosters.json")
BSE_ARCHIVE_PATH = Path("bse_cm_bhavcopy_archive.json")
EXPECTED = {"NIFTY": 50, "BANKNIFTY": 14, "SENSEX": 30}
SOURCES = {
    "NIFTY": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "BANKNIFTY": "https://nsearchives.nseindia.com/content/indices/ind_niftybanklist.csv",
    "SENSEX": "https://www.bseindia.com/AsiaIndexAPI/api/Codewise_Indices/w?code=16",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Trinetra-Index-Roster/1.0)",
    "Accept": "text/csv,text/html,application/octet-stream,*/*",
    "Referer": "https://www.nseindia.com/",
}


def _normalize_headers(row):
    return {str(key or "").strip().lower(): value for key, value in row.items()}


def parse_nse_constituent_csv(payload, index_key, as_of, source_url):
    if index_key not in ("NIFTY", "BANKNIFTY"):
        raise ValueError("NSE CSV parser only accepts NIFTY or BANKNIFTY")
    try:
        decoded = bytes(payload).decode("utf-8-sig")
    except (TypeError, UnicodeDecodeError) as exc:
        raise ValueError("NSE constituent CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise ValueError("NSE constituent CSV header missing")
    members = []
    seen_symbols, seen_isins = set(), set()
    for raw in reader:
        row = _normalize_headers(raw)
        symbol = str(row.get("symbol") or "").strip().upper()
        isin = str(row.get("isin code") or row.get("isin") or "").strip().upper()
        if not symbol and not isin:
            continue
        if not symbol or not isin:
            raise ValueError(f"{index_key} row missing Symbol or ISIN Code")
        if symbol in seen_symbols or isin in seen_isins:
            raise ValueError(f"{index_key} duplicate symbol or ISIN")
        seen_symbols.add(symbol)
        seen_isins.add(isin)
        members.append({"symbol": symbol, "isin": isin})
    expected = EXPECTED[index_key]
    if len(members) != expected:
        raise ValueError(f"{index_key} expected {expected} members, received {len(members)}")
    return {
        "as_of": as_of, "source_url": source_url,
        "expected_count": expected, "members": members,
        "source": "NSE Indices official index constituent CSV",
    }


class _BseConstituentTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_row = False
        self.in_cell = False
        self.cell = []
        self.cells = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "tr":
            self.in_row = True
            self.cells = []
        elif tag.lower() in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell = []

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data.strip())

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self.in_cell:
            self.cells.append(" ".join(part for part in self.cell if part))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.cells:
                self.rows.append(self.cells)
            self.in_row = False


def parse_bse_sensex_constituents(payload, bse_archive, as_of, source_url):
    data = payload
    if isinstance(payload, (bytes, bytearray, str)):
        raw = bytes(payload).decode("utf-8-sig") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = raw
    scrip_codes = []
    if isinstance(data, dict):
        rows = data.get("Table") or data.get("table") or data.get("Table1") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("SCRIP_CODE") or row.get("Scrip_Code") or row.get("scrip_code") or "").strip()
            if code:
                scrip_codes.append(code)
    else:
        parser = _BseConstituentTableParser()
        parser.feed(str(data or ""))
        for cells in parser.rows:
            if len(cells) < 2:
                continue
            code = next((cell.strip() for cell in cells if re.fullmatch(r"\d{5,6}", cell.strip())), None)
            if code:
                scrip_codes.append(code)
    if len(scrip_codes) != EXPECTED["SENSEX"] or len(set(scrip_codes)) != EXPECTED["SENSEX"]:
        preview = re.sub(r"\\s+", " ", str(html or ""))[:1200]
        raise ValueError(
            f"SENSEX official page must yield 30 unique BSE scrip codes; received {len(scrip_codes)}; "
            f"response_preview={preview!r}"
        )
    records = bse_archive.get("records", []) if isinstance(bse_archive, dict) else []
    session = next((r for r in records if isinstance(r, dict) and r.get("date") == as_of), None)
    if not session:
        raise ValueError(f"same-date BSE cash archive missing for SENSEX roster: {as_of}")
    by_id = {}
    for row in session.get("equity_rows", []):
        instrument_id = str(row.get("instrument_id") or "").strip()
        if instrument_id:
            if instrument_id in by_id:
                raise ValueError(f"duplicate BSE cash scrip code: {instrument_id}")
            by_id[instrument_id] = row
    members = []
    seen_isins = set()
    for code in scrip_codes:
        cash_row = by_id.get(code)
        isin = str(cash_row.get("isin") or "").strip().upper() if cash_row else ""
        if not isin or isin in seen_isins:
            raise ValueError(f"SENSEX scrip code {code} has missing or duplicate cash ISIN")
        seen_isins.add(isin)
        members.append({"instrument_id": code, "isin": isin})
    return {
        "as_of": as_of, "source_url": source_url,
        "expected_count": EXPECTED["SENSEX"], "members": members,
        "source": "BSE Indices official SENSEX constituents page; ISIN resolved from same-date BSE CM UDiFF",
    }


def fetch_once(session, url):
    response = session.get(url, headers=HEADERS, timeout=(10, 45))
    if response.status_code != 200 or not response.content:
        raise RuntimeError(f"official roster source unavailable: HTTP {response.status_code}: {url}")
    return response.content


def build_roster_bundle(session, as_of, bse_archive):
    nifty_payload = fetch_once(session, SOURCES["NIFTY"])
    bank_payload = fetch_once(session, SOURCES["BANKNIFTY"])
    nifty_roster = parse_nse_constituent_csv(nifty_payload, "NIFTY", as_of, SOURCES["NIFTY"])
    bank_roster = parse_nse_constituent_csv(bank_payload, "BANKNIFTY", as_of, SOURCES["BANKNIFTY"])
    partial = {
        "schema_version": 1, "as_of": as_of,
        "rosters": {"NIFTY": nifty_roster, "BANKNIFTY": bank_roster},
        "expected_counts": {"NIFTY": 50, "BANKNIFTY": 14},
        "research_only": True, "score_eligible": False,
    }
    Path("nse_index_constituent_rosters.json").write_text(
        json.dumps(partial, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    bse_payload = fetch_once(session, SOURCES["SENSEX"])
    return {
        "schema_version": 1,
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "rosters": {
            "NIFTY": nifty_roster,
            "BANKNIFTY": bank_roster,
            "SENSEX": parse_bse_sensex_constituents(bse_payload, bse_archive, as_of, SOURCES["SENSEX"]),
        },
        "expected_counts": EXPECTED,
        "research_only": True,
        "score_eligible": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Roster as-of date YYYY-MM-DD; defaults to current IST date")
    parser.add_argument("--bse-archive", default=str(BSE_ARCHIVE_PATH))
    parser.add_argument("--output", default=str(ROSTER_PATH))
    args = parser.parse_args()
    as_of = dt.date.fromisoformat(args.date).isoformat() if args.date else dt.datetime.now(IST).date().isoformat()
    bse_archive = json.loads(Path(args.bse_archive).read_text(encoding="utf-8"))
    with requests.Session() as session:
        bundle = build_roster_bundle(session, as_of, bse_archive)
    output = Path(args.output)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "status": "captured", "as_of": as_of,
        "counts": {key: len(value["members"]) for key, value in bundle["rosters"].items()},
        "requests": 3, "research_only": True, "score_eligible": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
