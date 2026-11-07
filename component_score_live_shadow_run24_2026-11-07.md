# Component Score Live Shadow — Run #24

**Repository:** `nagji247-png/pdmp-scanner`  
**Branch:** `feature/component-score-mainline-20261106`  
**Code HEAD:** `8905a382de174064374ea7599206036a0dc281e4`  
**Workflow run:** [Component Score Live Shadow Scan #24](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42323702923)  
**Artifact:** `component-score-live-shadow` (artifact ID `13553848901`)  
**Job result:** completed successfully. This is a shadow/research run, not a production deployment.

## 1. Per-asset shadow Final

| Asset | News component | Shadow Final | Included components |
|---|---:|---:|---|
| NIFTY | +0.18 | **+0.18** | News only |
| SENSEX | +0.86 | **+0.86** | News only |
| BANKNIFTY | +0.76 | **+0.76** | News only |
| GOLD | +0.01 | **+0.01** | News only |
| SILVER | -0.33 | **-0.33** | News only |

All five results are separate asset-level shadow outputs. They are not validated trading signals and do not replace or modify the published PDMP scores. Search, OI, futures and basket components were excluded, so News carries 100% of the normalized weight in each result.

## 2. Google Trends diagnostic

The manual shadow run collected separate related-query results for all five assets. However, each asset had **zero queries classified as directional/explicit-neutral sentiment** (coverage 0%). The queries were predominantly informational or navigation/price lookups, such as index live/chart/today and gold/silver price/coin searches.

The additional per-asset directional phrase diagnostic also had no usable recent interest for its three directional phrases per asset. Therefore:
- Search was marked unavailable/excluded, not assigned a zero score.
- Generic price/navigation searches were not relabelled as neutral.
- No search component entered any asset Final.
- The workflow log did not show a Google Trends HTTP 429 in this run. This is only an observation about this run, not a guarantee against future throttling.

These five extra directional phrase batches run only in the manually dispatched shadow workflow. The ordinary scheduled scan cadence was not changed.

## 3. Exchange/source observations

- NSE NIFTY: 25,030.35, +2.01%, dated 6-Nov-2026 15:30 IST.
- NSE BANKNIFTY: 59,086, +2.27%, dated 6-Nov-2026 15:30 IST.
- SENSEX BSE endpoint returned HTTP 403; Google Finance fallback reported 81,028.02, +2.17%, dated 6-Nov-2026 15:32:33.
- MCX official contract observations: GOLD ₹142,364, -1.20%, OI 15,771; SILVER ₹184,977, -1.16%, OI 16,826; both dated 6-Nov-2026 23:54 IST, expiry 4-Dec-2026.
- Yahoo Finance returned HTTP 429 for USDINR (`INR=X`) on both query1 and query2 endpoints. USDINR was unavailable in this run.
- Nine individual NSE stock quotes and the news feeds were fetched successfully.

These prices are source observations for the run; they do not by themselves validate a directional OI/futures score.

## 4. Why the other components remain excluded

### NSE index OI
Exact UDiFF/Contract Master reconciliation had previously verified 2,050/2,050 NIFTY and 975/975 BANKNIFTY option contracts for the 5-Nov-2026 archive. But that dated snapshot is not wired into the live shadow scan, and a sufficiently robust 60-session per-index directional edge has not been established. Participant-wise CLIENT OI is market-wide aggregate data, not symbol-specific index positioning.

### CLIENT futures and options
The exploratory 75-observation chronological holdout on market-wide participant CLIENT data did not show a consistent directional edge. Examples for CLIENT Index Futures Long change:

| Underlying price target | NIFTY hit rate | SENSEX hit rate | BANKNIFTY hit rate |
|---|---:|---:|---:|
| 1 session | 48.00% | 52.00% | 45.33% |
| 3 sessions | 42.67% | 45.33% | 56.00% |
| 5 sessions | 43.24% | 44.59% | 48.65% |

These results are mixed and mostly near/below chance. They do not justify copying a market-wide CLIENT futures signal into three separate index scores. CE/PE Long/Short changes remain separately visible as context, not a directional score.

### Constituent baskets
NIFTY 50 and NIFTY Bank official weights/cash-price research exists, but the complete dated basket is not wired into this live scan and the prior chronological holdouts were weak. Full official SENSEX 30-stock weights have not yet been verified in this workflow. No partial nine-stock proxy or estimated weights are substituted.

### GOLD/SILVER OI
The run fetched official MCX contract prices and OI, but a same-expiry, prior-session comparison plus sufficient directional validation is still required. Current contract OI alone is not a validated score.

## 5. Validation and safeguards

At code HEAD `8905a382de174064374ea7599206036a0dc281e4`:
- [Component Score Validation #200](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42321906047): success.
- [NSE/MCX Validation #265](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42321906042): success.
- [OI Research Validation #94](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42321906039): success.

The above are workflow results. Long 60-session OI, 60-session basket and 30-session MCX holdouts were explicitly skipped in #265; skipped checks are not passes. The separate exploratory participant OI holdout described above is not an eligible live component.

**No production score, dashboard layout, ordinary scan schedule, or live signal was changed. PR #90 remains Draft and unmerged.**
