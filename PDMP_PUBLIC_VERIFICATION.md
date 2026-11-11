# PDMP Scanner — Public Verification Record

**Repository:** [nagji247-png/pdmp-scanner](https://github.com/nagji247-png/pdmp-scanner)  
**Verification date:** 8 November 2026  
**Scope:** Research and shadow diagnostics. This document is not a trading recommendation.

## What is working

- Five separate asset records are produced: NIFTY, SENSEX, BANKNIFTY, GOLD and SILVER.
- The shadow score formula renormalizes weights over components that pass the eligibility checks.
- News is evaluated per asset, not copied from one index to another.
- Search evidence must be fresh, asset-specific Google Trends `now 1-d` related-query data. Stale, cross-asset, or unclassified evidence is excluded.
- NSE participant-wise CLIENT OI/Futures is treated as market-wide context, not falsely labelled as index-specific positioning.
- NSE and MCX archive diagnostics run offline against saved records. They do not call Google Trends, NSE, MCX or Yahoo Finance.
- The existing published dashboard score is not changed by these shadow diagnostics.

## Latest five-asset shadow snapshot

These are the currently recorded shadow results. **Only the per-asset News component is eligible in this snapshot.** The numbers below are therefore not fully covered multi-source scores.

| Asset | Shadow score | Eligible components | Coverage |
|---|---:|---|---:|
| NIFTY | +0.19 | News only | 1/5 (20%) |
| SENSEX | +1.00 | News only | 1/5 (20%) |
| BANKNIFTY | 0.00 | News only | 1/5 (20%) |
| GOLD | -0.28 | News only | 1/4 (25%) |
| SILVER | +0.45 | News only | 1/4 (25%) |

Coverage is data availability, **not** prediction confidence or accuracy. The shadow numbers must not be represented as fully validated market forecasts.

## Historical archive evidence

The saved research archives cover 2–6 November 2026 (five sessions):

| Dataset | Observations reported | Current eligibility |
|---|---:|---|
| NSE NIFTY index-option OI | 71 | Diagnostic only; insufficient history |
| NSE BANKNIFTY index-option OI | 24 | Diagnostic only; insufficient history |
| MCX GOLD same-expiry futures OI/price | 24 | Diagnostic only; insufficient history |
| MCX SILVER same-expiry futures OI/price | 20 | Diagnostic only; insufficient history |

NSE exact-contract reconciliation was checked against the official NSE UDiFF file and same-date MII contract master for 5 November 2026: NIFTY 2,050/2,050 and BANKNIFTY 975/975 contracts reconciled. This verifies contract identity for that date; it does **not** establish a profitable directional signal.

MCX data is total contract OI, not MCX CLIENT-category OI. It must not be described as CLIENT positioning. The short archive is not sufficient to validate a futures direction rule.

## Automated verification

Consolidated Component Verification workflow run: [#42475198913](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42475198913)

Recorded result:
- Workflow completed successfully.
- Five-asset offline verifier: integrity **PASS**.
- Component integrity failures: **0**.
- Completion status: **PARTIAL**.
- NSE/MCX archive diagnostics completed without provider fetches.
- Final-score eligibility remains restricted to components that pass validation.

## What is deliberately not claimed yet

- No 60-session chronological holdout has established predictive edge for OI or futures.
- SENSEX BSE index-option EOD archive and exact contract validation are still outstanding.
- Full official constituent-weighted baskets are not yet wired into the live shadow scan.
- Asset-specific Trends readings are not currently eligible in the snapshot above.
- No claim is made that this system guarantees profitable trades or reversals.

## Next acceptance gates

1. Build a sufficiently long dated archive for each relevant source.
2. Validate exact symbol, contract, expiry and date before calculating any component.
3. Run chronological 60-session validation and a separate holdout; report sample size, hit rate and uncertainty.
4. Add each component to the final shadow score only after it passes those gates.
5. Keep the production dashboard and existing scan cadence unchanged until the evidence supports promotion.

**Principle:** no fabricated live data, no cross-asset substitution, no unvalidated score contribution, and no extra provider calls just to make a dashboard look complete.
