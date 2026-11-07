# Official constituent-source audit — 2026-11-07

Scope: identify free, official constituent sources for the Trinetra/PDMP stock-basket research component. This is source discovery only; no basket component is enabled in Final.

## Verified official NSE Indices download endpoints

The official NIFTY 50 index page exposes an "Index Constituent" download. Its resolved CSV endpoint is:

- NIFTY 50: https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv

The official Nifty Bank index page exposes the same download control. Its resolved CSV endpoint is:

- NIFTY BANK: https://www.niftyindices.com//IndexConstituent/ind_niftybanklist.csv

Both download links were resolved from the official NSE Indices site. The web preview cannot render the CSV because the server returns an application/octet-stream download; this is not evidence that the file is invalid. The pages identify the official index pages and constituent-download controls.

Official index pages:
- NIFTY 50: https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50
- NIFTY BANK: https://www.niftyindices.com/indices/equity/sectoral-indices/nifty-bank

Important distinction: constituent membership CSV is not automatically a daily constituent-weight file. Before calculating weighted breadth, the pipeline must verify that the source contains the exact effective date, symbols and investible weights; otherwise it must fail closed. Do not estimate missing weights from market cap or from the top-10 list.

## SENSEX source finding

The official BSE SENSEX factsheet currently discovered in this audit is dated 30-Jan-2026 and shows only the top 10 constituent weights in its extracted content, not all constituent weights. It reports the number of constituents as 31 on that dated factsheet, which conflicts with the commonly referenced 30-stock SENSEX description and may reflect an index event/transition or source-version difference. This must be resolved against a current official BSE constituent/weight download before using a basket.

Official BSE factsheet URL:
- https://www.bseindices.com/Downloads/Factsheet/Factsheet_BSESENSEX_Jan2026.pdf

Its top 10 weights sum to 65.68%; the remaining constituent weights cannot be inferred safely from this partial list. Do not use these ten weights as if they represented the full index.

## Additional official weight-report lead (2026-11-07)

The NSE India All Reports catalogue exposes a report named **“Market Capitalisation, Weightage, Beta for NIFTY 50 & NIFTY Next 50”**. This is a useful official lead for obtaining dated NIFTY 50 constituent weights, but the report output itself has not yet been downloaded, parsed, date-checked, or reconciled against all 50 members. It does not establish NIFTY BANK weights.

Official catalogue: https://betanseapi.nseindia.com/all-reports

The public NIFTY 50 index page confirms the index uses free-float market-cap weighting and offers an Index Constituent download, while the NIFTY BANK page likewise offers a member CSV. A member list is still not a complete weight snapshot. The NSE Indices Daily Reports page currently exposes Daily Snapshot CSV links; this audit did not establish that those snapshots contain complete constituent weights.

For SENSEX, the BSE official site identifies the benchmark and its float-adjusted methodology, but this search did not retrieve a current, complete, dated official 30-member weight file. Third-party tables are not accepted as an official substitute.

**Status correction:** Earlier shadow diagnostic wording that said NIFTY 50 and NIFTY Bank monthly weights had been verified was too strong. Only official constituent-download endpoints were identified. No complete dated weights for these indices have been parsed and validated yet. The component remains excluded from Final.

## Secondary source caution

Non-official index summaries may list all Nifty Bank members or top-10 weights, but they are not accepted as authoritative weight snapshots for live scoring. Use official NSE Indices/BSE sources only for the basket's membership and effective weights.

## Implementation gate

A future loader may fetch these free public files, but the stock-basket component must remain excluded from Final until all of the following pass:
1. Official source identity and successful HTTP/file parse.
2. Effective date present and within the allowed session-age window.
3. Exact expected member count and unique, non-empty exchange symbols.
4. Positive weights and total weight within a strict tolerance of 100%.
5. Every constituent has a valid previous/current close for the same trading dates.
6. No duplicate/missing symbols, stale quote rows, or partial fallback basket.
7. Chronological out-of-sample validation demonstrates useful directional value beyond the index/news baseline.

The existing helper `weighted_constituent_breadth_candidate` correctly keeps its output diagnostic-only (`included_in_asset_final=false`). This audit does not change that gate.

## User-facing safety invariants

- Never substitute the 9-stock watchlist for any index's full constituent basket.
- Never substitute NIFTY data for SENSEX or BANKNIFTY.
- Never infer all weights from top-10 factsheet data.
- Never enable the component merely because a CSV download succeeds.
- No production score, dashboard layout, ordinary 30-minute scan cadence, or live signal is changed by this audit.
