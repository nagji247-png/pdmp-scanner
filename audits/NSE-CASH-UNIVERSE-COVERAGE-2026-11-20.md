# NSE Cash-Market Universe Coverage Audit — 20 Nov 2026

## Purpose

Record what the verified NSE MCP snapshots establish about the TRINETRA stock universe before changing production scanning. This is an audit note only; it does not change the dashboard or scanner.

## Verified snapshot findings

The NSE MCP equity prefix snapshot from the successful 36-prefix run (A-Z and 0-9) contained:

- 3,146 raw rows.
- 3,140 unique symbol names after de-duplication.
- 3,138 unique records with `type=CM`.
- 2 records with `type=ILQ` (AGASTYAEN and UNIVPHOTO).
- Within `type=CM`: 2,967 distinct `series=EQ` symbols and 171 distinct `series=BE` symbols.
- No symbol-prefix mismatches in the captured responses.
- The 3,146 raw rows include duplicate rows; the unique counts above are de-duplicated.

The NSE MCP SME typed A-Z audit separately found 581 distinct symbols typed SME and five ILQ typed records in the SME endpoint responses. These SME endpoint counts must not be added to the CM counts: endpoint definitions, overlapping symbols, and status-count semantics have not been reconciled.

The bounded unfiltered SME call returned 500 rows (498 distinct symbol names), consistent with the documented maximum limit of 500. It cannot establish the full SME universe.

## Current production coverage

In `fetch_and_score.py`, `main()` loads `nse-fo-stock-sector-master.json` and passes only its 218 verified F&O symbols to `fetch_nse_market_activity_bulk_quotes()`. If that returns no instruments, the EOD fallback is also requested only for those same F&O symbols.

Therefore the current Market Activity bulk-quote path is **218-stock F&O coverage**, not full NSE cash-market coverage. The nine-stock PDMP watchlist is a separate path and remains unchanged.

The helper `nse_stock_universe()` currently calls `cm_get_equity_stocks` once with an empty filter and `limit=500`. That cannot represent the full 3,140-symbol prefix snapshot. A source search in the current `fetch_and_score.py` found no call site for this helper, so it should not be treated as the active Market Activity universe.

## What is not established

- The 590 SME status count versus 581 distinct SME-typed A-Z symbols remains unexplained. It is not proof that nine listings are missing.
- The 218 F&O master has not yet been directly set-compared with the exact 20-Nov typed CM snapshot in this audit.
- The 171 `CM/BE` securities are separate from `CM/EQ`; whether and how to include them in each scanner signal needs an explicit policy.
- The two `ILQ/BE` records are not classified as ordinary CM equity and should not silently enter the cash-equity universe.
- A successful post-market snapshot is not proof of live intraday freshness.
- Public NSE access does not itself establish permission to republish raw quotes or a complete exchange-derived list on public GitHub Pages.

## Safe implementation direction

1. Keep the verified 218 F&O universe intact.
2. Build a separately typed cash-market universe from verified `CM/EQ` and `CM/BE` records, preserving the series field; do not mix in `ILQ` without evidence.
3. Reconcile F&O membership against the same dated snapshot before calculating the non-F&O remainder.
4. For stocks outside F&O, include a buying/selling signal only when a verified quote/volume/delivery/bulk-block source exists; never fabricate OI or unavailable fields.
5. Display sector direction from available verified shares with coverage counts and an insufficient-coverage caution; do not hide the direction when coverage is low.
6. Do not fan out one quote request per 3,000+ symbols. First validate endpoint refresh/capacity, request budget, timestamp behavior, and NSE data-use terms.
7. Do not commit raw quote snapshots or make production changes in this audit PR.

## Source artifacts

- NSE MCP equity prefix snapshot, 36 prefixes: run 44765070308, artifact 14642314267.
- NSE SME A-Z typed record audit: run 44782531641, artifact 14652234038.
- NSE SME status vs unfiltered endpoint check: run 44783749983, artifact 14653326324.
- Current F&O master: `nse-fo-stock-sector-master.json`, 218 symbols, `as_of=2026-11-14`.

All referenced workflow artifacts are short-lived or time-limited. This note records aggregate results only and intentionally does not include raw quote data or the full symbol dump.
