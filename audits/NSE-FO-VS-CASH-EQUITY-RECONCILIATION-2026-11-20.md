# NSE F&O vs Cash Equity Reconciliation — 20 Nov 2026

## Result

A direct symbol-set comparison was performed using:
- the 218-symbol `nse-fo-stock-sector-master.json` in main (`as_of=2026-11-14`);
- the successful NSE MCP 36-prefix snapshot from 20-Nov-2026, de-duplicated by symbol and filtered by exact `type` and `series`.

| Universe | Unique symbols |
|---|---:|
| NSE MCP `type=CM, series=EQ` | 2,967 |
| NSE MCP `type=CM, series=BE` | 171 |
| NSE MCP all `type=CM` (EQ + BE) | 3,138 |
| Verified F&O master | 218 |
| F&O symbols found in CM/EQ | 218 |
| F&O symbols missing from CM/EQ | 0 |
| CM/EQ symbols outside F&O | 2,749 |
| CM/BE symbols outside F&O | 171 |

## Interpretation

- All 218 verified F&O symbols are present in the 20-Nov NSE MCP `CM/EQ` snapshot.
- The current dated snapshot therefore supports a **2,749-symbol CM/EQ non-F&O remainder** for further validation.
- The 171 CM/BE symbols are a separate series and should remain separately typed; do not silently treat them as EQ.
- The 2 ILQ/BE symbols (AGASTYAEN and UNIVPHOTO) are excluded from CM totals.
- This is a post-market symbol-universe comparison, not an intraday quote freshness test.
- It does not establish data-use or public republication rights for NSE-derived market data.

## Production status

No production changes are made by this audit. The current Market Activity quote path still uses the 218-symbol F&O master only. The 2,749 CM/EQ non-F&O symbols are identified as a candidate extension universe, not yet enabled for quote polling or signal generation.

## Recommended next validation

Before enabling the additional universe:
1. verify the exact NSE MCP response schema and freshness timestamps for a small, bounded sample from the non-F&O remainder;
2. test available quote, volume, delivery and bulk/block-deal fields without per-symbol request fan-out;
3. preserve unknown/missing fields as unavailable, never fabricate OI or futures data;
4. establish NSE data-use terms before public display of exchange-derived quote data;
5. retain the existing 218 F&O path and all stale-data safeguards.

## Reproducible source references

- NSE MCP 36-prefix snapshot: Actions run 44765070308, artifact 14642314267.
- Verified F&O master: `nse-fo-stock-sector-master.json`, 218 symbols, `as_of=2026-11-14`.
- Prior aggregate coverage note: PR #429.

This file records counts and reconciliation only. It does not publish the full symbol list or raw quote data.