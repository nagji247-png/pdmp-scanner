# PDMP Component Score Live Shadow — Run #19

- Workflow: [Component Score Live Shadow Scan #19](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42256925227)
- Run ID: `42256925227`
- Event: `workflow_dispatch`
- Branch: `feature/component-score-mainline-20261106`
- Commit: `15b80a248cfd13332f1a4b023bc4a033ff2ae743`
- Captured data timestamp: `2026-11-06T16:56Z` (22:26 IST)
- Job: completed successfully; all six workflow steps passed.
- Artifact: `component-score-live-shadow` (data.json; 98,112 bytes; expires 2026-11-09T16:59:42Z).
- Scope: isolated shadow run only. No production score, published signal, dashboard data, or repository data file was changed by this workflow.

## Per-asset verified component result

Formula: sum(score × configured component weight) / sum(weights of included verified components). Missing, stale, or unvalidated components are excluded, not set to zero.

| Asset | News score | Search mix (Bull/Bear/Neutral) | Search coverage | Final shadow | Included weight |
|---|---:|---:|---:|---:|---|
| NIFTY | -0.49 | 0.0 / 0.0 / 100.0% | 84.4% | **-0.49** | News 100% |
| SENSEX | +0.70 | 0.0 / 0.0 / 100.0% | 83.3% | **+0.70** | News 100% |
| BANKNIFTY | +0.41 | 0.0 / 0.0 / 100.0% | 77.4% | **+0.41** | News 100% |
| GOLD | -0.11 | 0.0 / 0.0 / 100.0% | 75.7% | **-0.11** | News 100% |
| SILVER | +0.03 | 0.0 / 0.0 / 100.0% | 56.6% | **+0.03** | News 100% |

News source for all assets: Google News RSS, asset-specific card query; only timestamped headlines within 24 hours. Index news also excludes cross-index duplicate headlines. Scores are shadow research values, not validated trading signals.

## Asset-specific Google Trends diagnostics

All five seeds returned a fresh `now 1-d` related-query snapshot at `2026-11-06T16:56:00Z`:

| Asset | Seed | Raw queries | Classified | Unclassified |
|---|---|---:|---:|---:|
| NIFTY | `nifty` | 25 | 16 | 9 |
| SENSEX | `sensex` | 24 | 11 | 13 |
| BANKNIFTY | `bank nifty` | 6 | 5 | 1 |
| GOLD | `gold price` | 25 | 17 | 8 |
| SILVER | `silver price` | 25 | 14 | 11 |

The classified results were neutral/information-intent only. Examples include `nifty today`, `sensex share price`, `bank nifty live`, `gold price today`, and `silver coin price`. No asset had a bullish or bearish classified query weight in this snapshot.

Important interpretation:
- 100% Neutral is the share within that seed's classified related-query weights. It is **not** 100% of all Google searches, retail traders, or people.
- Coverage is the share of total returned related-query weight that was classifiable.
- Search was correctly excluded from each Final because there was no bullish-vs-bearish directional split. The scan did not invent a zero directional score.
- Rising related queries were kept as separate diagnostics and were not mixed into the top-query weight denominator.

## Other components withheld

### NIFTY / SENSEX / BANKNIFTY
- EOD OI: excluded; no dated, complete, per-index EOD snapshot was wired into this live scan. Existing NSE OI contract reconciliation is not itself a validated directional predictor.
- CLIENT CE/PE and CLIENT Futures: available only as NSE participant-wise market-wide aggregate, not separately attributable to each index. They remain context-only and are not copied into each index score.
- Stock basket: excluded from Final pending longer-horizon directional validation. NIFTY 50 and NIFTY Bank research basket coverage exists, but the 60-session holdout did not establish a reliable edge. SENSEX full official weights are still not verified.

### GOLD / SILVER
- MCX EOD OI / Futures: excluded from Final. Exact-contract Bhav Copy observations and same-expiry diagnostics exist in research, but the short holdout did not establish a robust predictive edge.

## NSE CLIENT aggregate context (6-Nov vs 5-Nov 2026)

This is one market-wide participant report, repeated as context only; it is not three index-specific datasets.

| CLIENT field | Change |
|---|---:|
| CE Call Long | +145,968 |
| CE Call Short | +225,479 |
| PE Put Long | +751,994 |
| PE Put Short | +729,117 |
| Index Futures Long | -6,612 |
| Index Futures Short | +14,248 |

The four CE/PE Long/Short changes are retained separately. Gross OI additions alone are not converted into a guessed bullish/bearish score.

## Global crowd card status

The global `trends` object in this artifact is unavailable because the last successful global Google Trends reading was older than the configured 360-minute age limit. Its daily slots were pending. This is separate from the five fresh asset-specific shadow snapshots above. The global crowd card must therefore remain unavailable / NO TRADE for this artifact; no stale mood is reused.

## Validation decision

- Live shadow workflow: PASS.
- Artifact uploaded: PASS.
- All five asset-specific snapshots present and timestamped: PASS.
- Per-asset Final formula: News only, normalized to 100% of included weight.
- Search contribution: withheld correctly for all five assets.
- Production score changed: `false`.
- Merge / deploy: not performed by this workflow.

Next research gate: improve the quality of asset-specific directional search evidence without relabelling neutral price/navigation queries as bullish or bearish, then repeat a manual shadow scan. Do not enable any excluded OI, Futures, or basket component until its dated source and out-of-sample directional validation pass.
