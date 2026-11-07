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

The official BSE SENSEX October-2026 factsheet was retrieved in CI, but its PDF text extraction did not expose a complete 30-stock weight table. The same probe separately retrieved the official BSE SENSEX roster with 30 rows as of 2026-10-30. Membership is therefore verified for that date; complete official weights remain unresolved. An older January 2026 factsheet had a reported constituent-count discrepancy and should not be used as the current membership snapshot.

Official BSE factsheet URL:
- https://www.bseindices.com/Downloads/Factsheet/Factsheet_BSESENSEX_Jan2026.pdf

The partial top-10 weight table is not a complete basket. Do not use these ten weights as if they represented the full index.

## Verified official monthly weights and dated cash coverage (CI evidence, 2026-11-06)

The NSE/MCX Integration workflow #260 downloaded and parsed the official NSE Indices monthly archive:

- Archive: https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/indices_dataOct2026.zip
- Report date: **October 30, 2026**
- NIFTY 50 PDF: `NIFTY_50_Oct2026.pdf` — 50 constituents, weight sum 99.98%, zero duplicate symbols, zero rejected rows.
- NIFTY Bank PDF: `NIFTY_Bank_Oct2026.pdf` — 14 constituents, weight sum 100.00%, zero duplicate symbols, zero rejected rows.
- Dated NSE cash EQ bhavcopy coverage was complete for the 50/50 and 14/14 member sets in the four observed sessions from Oct 30 through Nov 5, 2026.

The same workflow reconstructed daily prior-session weights from the Oct 30 official monthly snapshot and cash prices. Reconstructed basket returns matched the official index returns closely: NIFTY 50 deviations were 0.0, -8.6, -2.2 and 0.0 bps across the four checked sessions; NIFTY Bank deviations were 0.0 bps at displayed precision for all four. This confirms source parsing and short-window index replication, not a 60-session directional edge.

The workflow's 60-session chronological directional holdout is separately reported in the PR: NIFTY direct 11/20 vs contrarian 9/20 (correlation -0.091); BANKNIFTY direct 8/20 vs contrarian 12/20 (correlation -0.059). This evidence remains weak and descriptive; the basket component is still excluded from Final pending broader validation and live snapshot wiring.

The NSE All Reports catalogue also lists “Market Capitalisation, Weightage, Beta for NIFTY 50 & NIFTY Next 50”, a potential additional official route, but the already-verified October archive above is the evidence used here. The official monthly archive itself contains NIFTY 50 and NIFTY Bank PDFs.

Official catalogue lead: https://betanseapi.nseindia.com/all-reports

## SENSEX remains a separate unresolved source

The same CI probe retrieved the BSE SENSEX roster (30 rows, as-of 2026-10-30), but the October 2026 BSE factsheet PDF text extraction yielded no complete 30-stock weight table. Therefore SENSEX membership is known for that date, but complete official constituent weights are not yet verified. Do not infer weights from the top-10 factsheet, use a third-party table, or substitute NIFTY data.

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
