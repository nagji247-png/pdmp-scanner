# PDMP Component Score Shadow Report — 2026-11-06

- Shadow scan completed: `2026-11-06T08:58Z` (14:28 IST).
- GitHub Actions run: [Component Score Live Shadow Scan #17](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42191484666)
- Artifact: `component-score-live-shadow` (data.json; 97,118-byte ZIP; expires 2026-11-09).
- Scope: isolated shadow calculation only. Published `instruments[*].score`, production signals and dashboard live scoring were not changed.
- Formula: weighted mean of verified components only; missing/stale/unvalidated inputs are excluded, never set to zero.

## Per-asset result

| Asset | News component | News evidence | Trends mix (Bull/Bear/Neutral) | Coverage | Final shadow score | Included weights |
|---|---:|---:|---:|---:|---:|---|
| NIFTY | +0.71 | 7 headlines | 0 / 0 / 100% | 84.6% | **+0.71** | News 100% |
| SENSEX | +1.20 | 3 headlines | 0 / 0 / 100% | 77.5% | **+1.20** | News 100% |
| BANKNIFTY | +0.89 | 5 headlines | 0 / 0 / 100% | 78.5% | **+0.89** | News 100% |
| GOLD | -0.26 | 8 headlines | 0 / 0 / 100% | 78.0% | **-0.26** | News 100% |
| SILVER | -0.08 | 8 headlines | 0 / 0 / 100% | 53.7% | **-0.08** | News 100% |

These are component research scores, not trading recommendations or published PDMP scores. The five assets have distinct asset-specific News queries and separate Google Trends seeds.

## Why Search did not enter the final

The one-day Google Trends related-query batches returned only neutral/information-intent classified queries for all five seeds. Since there was no bullish-vs-bearish directional split, Search was kept visible as diagnostic data but excluded from the weighted final. The percentages are relative weights within each seed's classified related-query set, not percentages of all people/searches. Coverage is separately shown above.

Seeds: `nifty`, `sensex`, `bank nifty`, `gold price`, `silver price`.

## Components withheld

- **Index EOD option OI:** no verified, symbol-specific EOD option-chain snapshot for NIFTY/SENSEX/BANKNIFTY was present in this run.
- **CLIENT CE/PE and Futures:** official NSE participant report supplied market-wide aggregate changes only, not index-specific positions. The data is displayed as context, not added to any index Final.
- **Index Futures:** directional scoring remains withheld because the CLIENT futures holdout results were not robust enough for live use.
- **Gold/Silver MCX EOD OI:** dated category-wise OI snapshot was not verified in this run.
- **Gold/Silver Futures:** same-expiry current-vs-previous session OI comparison was not verified.
- **Index stock basket:** complete official constituents and same-date official weights were not available; the 9-stock watchlist was not substituted.

## NSE CLIENT aggregate context (2026-11-05 vs 2026-11-04)

This exact same market-wide report is repeated as context on the three index cards; it is **not three separate index datasets**.

| CLIENT field | Change |
|---|---:|
| CE Call Long | +54,558 |
| CE Call Short | +55,558 |
| PE Put Long | +636,814 |
| PE Put Short | +565,632 |
| Index Futures Long | -28,501 |
| Index Futures Short | +16,651 |

CE/PE long/short changes are not treated as standalone bullish/bearish predictors. CLIENT Futures are also withheld from scoring pending stronger validation.

## Validation

- Component scoring CI: PASS — Python syntax, unit/integration tests and dashboard JavaScript syntax.
- OI research validation: PASS.
- NSE/MCX quote integration validation: PASS.
- Live shadow scan: PASS; artifact uploaded.
- No merge or deployment performed.


## Repeat shadow observation — 2026-11-06 09:09 UTC

A second isolated run completed successfully: [Run #18](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42192860647). It produced the same News and final component scores:

| Asset | First final | Second final | Search mix on second run |
|---|---:|---:|---|
| NIFTY | +0.71 | +0.71 | 0 / 0 / 100% |
| SENSEX | +1.20 | +1.20 | 0 / 0 / 100% |
| BANKNIFTY | +0.89 | +0.89 | 0 / 0 / 100% |
| GOLD | -0.26 | -0.26 | 0 / 0 / 100% |
| SILVER | -0.08 | -0.08 | 0 / 0 / 100% |

Search classification coverage on the second observation: NIFTY 85.5%, SENSEX 77.3%, BANKNIFTY 69.7%, GOLD 77.8%, SILVER 50.7%. The mix remained neutral-only; Search correctly stayed out of Final.

The repeat run supports that the News result is stable across these two close observations, but it does **not** validate the News score as a predictive trading signal. The live shadow workflow is now manual-dispatch only to avoid repeated Google Trends requests on every PR update.


## Exchange-specific EOD OI source audit — 6 Nov 2026

This audit separates the three exchanges/sources so that a market-wide report is not mistaken for an index-specific or commodity-specific dataset.

### NSE: NIFTY and BANKNIFTY candidate

- NSE All Reports explicitly lists F&O - UDiFF Common Bhavcopy Final (zip) and identifies the older F&O Bhavcopy formats as discontinued from 8-Jul-2024.
- This is the correct official daily contract-level candidate for NSE-listed index derivatives such as NIFTY and BANKNIFTY. It is distinct from the participant-wise CLIENT OI report.
- Before enabling scoring, a dated ZIP must be downloaded and checked for exact OPTIDX/index symbol, expiry, strike, CE/PE, OpnIntrst, ChngInOpnIntrst, trade date and completeness. A single contract or a partial expiry is not the whole index option book.
- NSE's live Option Chain page also exposes a CSV download, but it is a live UI surface and does not itself prove a durable historical EOD archive.

### BSE: SENSEX candidate

- SENSEX index options are a BSE product; the NSE F&O bhavcopy must not be used as a substitute for SENSEX.
- BSE's published Equity Derivatives file-format document defines a Market Summary file MS_<yyyymmdd>-01.csv with Product Type IO for index options, Asset Code, Expiry Date, Strike Price, Option Type (CE/PE) and an Open Interest field.
- BSE's current market-data portal describes Equity Derivatives data as an API product with plans/KYC/payment. The public format document proves the schema, not free public access to the daily file. A freely accessible dated daily SENSEX option OI file has not yet been verified.
- Therefore SENSEX EOD OI remains excluded until a dated, complete, accessible source is verified.

### MCX: GOLD and SILVER candidate

- MCX's official Bhav Copy page and the existing code's fetch_mcx_bhavcopy_rows(trade_date) establish a dated contract-level Bhavcopy route. The current parser mcx_bhavcopy_contract_close() extracts only the exact FUTCOM contract's close; it does not currently validate or return OI fields.
- MCX's official Historical Data page currently documents traded-contract quantity, total value, average daily turnover and premium value; those displayed summary/detail fields are not an OI history.
- MCX's PRO/CLI Details page currently describes percentage of proprietary/client trades and ALGO/HFT trades by commodity. That is trade-value share, not participant-wise open interest. It cannot be relabelled as CLIENT OI.
- Next technical gate: inspect one official dated MCX Bhav Copy response and verify the exact OI and change-in-OI field names, instrument type, commodity symbol, expiry, trade date and prior-session same-expiry match. Until then, no MCX OI/futures component is included.

### Current decision

- NIFTY/BANKNIFTY: official NSE daily contract-level OI is a viable candidate; schema and full-date coverage must be fixture-validated before use.
- SENSEX: requires BSE daily contract-level data; schema is known, public/free daily access is not yet established.
- GOLD/SILVER: MCX contract-level Bhav Copy is a candidate, but OI field mapping and same-expiry daily comparison remain unverified.
- None of these sources changes the current shadow scores until the exact date, exchange, symbol, expiry and coverage checks pass. No score is inferred from a quote-only or participant-aggregate report.

Official source references:
- NSE F&O reports: https://www.nseindia.com/all-reports-derivatives
- NSE EOD/historical data description: https://www.nseindia.com/static/market-data/eod-historical-data-subscription
- BSE Equity Derivatives file format: https://www.bseindia.com/downloads1/File_Format_Equity_Derivatives.pdf
- BSE market-data portal: https://marketdata.bseindia.com/
- MCX Bhav Copy: https://www.mcxindia.com/market-data/bhavcopy
- MCX Historical Data: https://www.mcxindia.com/market-data/historical-data
- MCX PRO/CLI Details: https://www.mcxindia.com/market-data/pro-cli-details
