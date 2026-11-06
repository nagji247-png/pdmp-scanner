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


## Follow-up implementation checkpoint — 6 Nov 2026

### NSE UDiFF parser prototype

- Added `aggregate_nse_udiff_index_option_oi()` in `component_scoring.py` for the official NSE F&O UDiFF field names: `FinInstrmTp=OPTIDX`, `TckrSymb`, `BizDt`, `XpryDt`, `OptnTp`, `OpnIntrst`, and `ChngInOpnIntrst`.
- The helper aggregates CE and PE open interest and change-in-OI separately for one exact symbol and trade date. It rejects mismatched dates, missing expiry/OI/change fields, malformed option sides, and snapshots missing either CE or PE.
- It explicitly sets `included_in_asset_final=false` and `coverage_validated=false`. This is a parser/diagnostic prototype, not a production data feed and not a directional score. Full contract-master reconciliation and a real dated exchange-file fixture are still required.
- Unit tests added for symbol isolation, CE/PE aggregation, and fail-closed date/side handling.

### MCX category OI source clarification

- MCX's official disclosure page states that its category-wise Open Interest and Turnover report is at commodity level, including all variants of the same commodity; options positions use the directional method. It may be useful as commodity-participant context for GOLD/SILVER, but it is not contract/expiry-specific and cannot replace daily Bhavcopy OI by exact contract.
- MCX's official Datafeed page confirms that end-of-day Bhav Copy includes contract-wise open interest. The remaining engineering gate is to inspect a real dated MCX file/API response and map the exact OI keys, then compare the same symbol and expiry across consecutive trading dates.
- No MCX participant report or Bhavcopy OI has been added to the asset score.

### Main branch movement

- `main` advanced by one unrelated GitHub Actions commit refreshing `trinetra-data.json` after this feature branch's base point. The feature branch is now 21 commits ahead and 1 behind `main`; this data-only commit does not overlap the component files. No automatic merge/rebase was attempted.

Official source references:
- NSE reports page (lists F&O UDiFF Bhavcopy and COM category-wise OI reports): https://www.nseindia.com/all-reports-derivatives
- NSE UDiFF formats: https://www.nseindia.com/static/resources/forms-formats-members
- MCX category-wise participant OI disclosure: https://beta.mcxindia.com/market-operations/trading-surveillance/reports/disclosure-of-open-interest-and-turnover-for-various-categories-of-market-participants
- MCX Datafeed (EOD Bhavcopy includes contract-wise OI): https://classic.mcxindia.com/technology/datafeed


### NSE archive availability re-check — 6 Nov 2026

- A fresh index of NSE's official All Reports page exposes a dated F&O UDiFF Common Bhavcopy Final ZIP named `BhavCopy_NSE_FO_0_0_0_20261030_F_0000.csv.zip` and the corresponding dated NSE F&O Contract File `NSE_FO_contract_30102026.csv.gz`. This confirms that the official report listing publishes both the daily bhavcopy and a same-date contract-master candidate.
- The corresponding official archive URL pattern is `https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_20261030_F_0000.csv.zip`. The browser retrieval path rejected the ZIP binary content type and the direct download attempt failed in this environment. Therefore, the actual CSV rows and the contract-master cross-check have **not** been inspected; this is source availability confirmation, not parser fixture validation.
- Next gate remains unchanged: obtain both official dated files, inspect the actual headers/rows, reconcile every OPTIDX contract for NIFTY and BANKNIFTY (including expiry/strike/CE-PE identity), compare file counts and reject incomplete coverage before considering any OI component. SENSEX remains BSE-only.
- Official listing evidence: https://www.nseindia.in/all-reports-derivatives

### MCX UDiFF schema and public Bhav Copy re-check — 6 Nov 2026

- MCX Clearing Corporation's official UDiFF page publishes a Bhavcopy format PDF and a separate sample-file link for the Commodity Derivatives segment. The PDF confirms the file name pattern `Bhavcopy_MCX_CO_0_0_0_yyyymmdd_F_0000.csv`, CSV with ISO headers, and exact fields: `TradDt`, `BizDt`, `Sgmt`, `Src`, `FinInstrmTp`, `TckrSymb`, `XpryDt`, `ClsPric`, `OpnIntrst`, and `ChngInOpnIntrst`.
- MCX's official public Bhav Copy page search-indexed a dated 05-Nov-2026 table with instrument, commodity, expiry, close, volume and OI (Lots), confirming current daily public table visibility for commodity futures. This is useful as a cross-check surface, but it does not expose the UDiFF raw CSV headers/rows through the browser extraction.
- The official sample CSV link currently returns an unsupported CSV content type in this environment. Thus the actual sample rows and current dated raw UDiFF CSV have not been inspected; the schema mapping is based on the official MCXCCL PDF, not a live-file fixture.
- Added `aggregate_mcx_udiff_commodity_futures_oi()` as a diagnostic-only parser prototype. It isolates exact MCX/CO/FUTCOM/symbol/trade-date/expiry and requires one exact row with valid OI, change-in-OI and close. Duplicate rows, missing fields and ambiguous matches fail closed. It always reports `included_in_asset_final=false` and `coverage_validated=false`.
- Added unit tests for exact symbol/expiry/date isolation, duplicate rejection and missing OI-change rejection. No GOLD/SILVER component score is enabled: actual raw-file fixture, complete daily-file checks, and same-expiry previous-session comparison are still required.
- Official sources: https://www.mcxccl.com/all-circulars/unified-distilled-file-formats-%28udiff%29 and https://www.mcxindia.com/market-data/bhavcopy.

### MCX public Bhav Copy: actual same-expiry GOLD/SILVER comparison — 6 Nov 2026

- The GitHub Actions runner successfully fetched the official MCX public Bhav Copy endpoint for 5-Nov-2026 (16,402 rows) and 4-Nov-2026 (16,350 rows). Exact FUTCOM rows were isolated for the same 04-Dec-2026 expiry for both commodities.
- GOLD: 4-Nov close ₹143,234, OI 16,095 lots; 5-Nov close ₹144,095, OI 15,716 lots. One-session change: close +₹861, OI -379 lots (price-up/OI-down regime).
- SILVER: 4-Nov close ₹187,735, OI 17,143 lots; 5-Nov close ₹187,140, OI 16,701 lots. One-session change: close -₹595, OI -442 lots (price-down/OI-down regime).
- These are genuine dated exchange records, not synthetic fixtures. They establish that the public Bhav Copy endpoint exposes contract-wise OI and close and that same-expiry two-session comparison is feasible.
- Added `compare_mcx_bhavcopy_contract_oi()` with strict exact symbol/FUTCOM/expiry/date matching, one-row-per-session requirement, numeric OI/close checks, and duplicate rejection. It reports price/OI regime as diagnostic context only and hard-codes `included_in_asset_final=false` and `coverage_validated=false`.
- Added unit tests for the GOLD observed delta and duplicate-row rejection; compact MCX expiry dates (e.g. `04DEC2026`) are now parsed.
- Important limit: this is one expiry and one adjacent-session pair only. It is not a validated predictive signal. Need broader multi-session history, contract roll/expiry controls, data completeness and out-of-sample price/OI regime study before assigning any GOLD/SILVER score. No component score has been added to asset finals.
- Runner evidence: [MCX Bhav Copy diagnostic run 42204349281](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42204349281).

### Latest validation after MCX UDiFF parser tests — 6 Nov 2026

All three workflows passed on commit `6e5137aeb6e96ab21c34b93ddf46990a5d3c60ca`:
- Component Score Validation: [run 42197522607](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42197522607) — Python syntax, 23 unit/integration tests (including both new MCX UDiFF tests), and dashboard JavaScript syntax all passed.
- NSE/MCX Quote Integration: [run 42197522507](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42197522507) — existing quote, timestamp, MCX Market Watch and NSE diagnostics passed. This workflow does not claim raw UDiFF fixture validation.
- OI Research Validation: [run 42197522504](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42197522504) — OI research syntax and tests passed.

These CI results validate parser logic against synthetic fixtures and existing integration checks only. They do not replace a real official dated UDiFF CSV fixture, daily-file completeness audit, or consecutive-session OI/price study. Therefore NSE and MCX OI components remain excluded from all asset final scores.



### MCX five-session same-expiry raw data check and diagnostic fix — 6 Nov 2026

- Expanded the official MCX Bhav Copy probe to five available sessions (30-Oct, 2-Nov, 3-Nov, 4-Nov, 5-Nov 2026) for the exact FUTCOM 04DEC2026 contracts.
- The runner successfully retrieved all five dated exchange responses: 15,913; 16,296; 16,318; 16,350; and 16,402 rows respectively. Exactly one GOLD and one SILVER 04DEC2026 row were found per date.
- Observed GOLD close/OI (₹ / lots): 30-Oct 138,485 / 16,368; 2-Nov 140,186 / 16,142; 3-Nov 139,452 / 16,282; 4-Nov 143,234 / 16,095; 5-Nov 144,095 / 15,716.
- Observed SILVER close/OI (₹ / lots): 30-Oct 179,132 / 18,105; 2-Nov 183,779 / 16,933; 3-Nov 179,698 / 16,830; 4-Nov 187,735 / 17,143; 5-Nov 187,140 / 16,701.
- The five raw dated fetches succeeded, but the comparison step in that workflow attempt failed because `fetch_and_score.py` had not imported `compare_mcx_bhavcopy_contract_oi` from `component_scoring.py`. This is an integration/import defect, not an exchange-data failure.
- Fixed the missing import and added an integration regression test that verifies the function is exported by `fetch_and_score` and correctly compares the real GOLD 5-Nov vs 4-Nov sample (close +₹861; OI -379 lots; diagnostic-only).
- The four observed one-session regime readings per commodity are too small to validate a predictive edge. A quick next-session direction check on the first three available signals was mixed/poor (GOLD 1/3; SILVER 0/3). This tiny sample is explicitly descriptive, not a statistical backtest. No MCX OI score is enabled.
- The workflow attempt that exposed the import bug: [NSE/MCX integration run 42207762537](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42207762537). The subsequent fix is on branch commit `8c00a1e8b790ee21fc7d0402cc9a036d36e361f6`; this GitHub App commit has not yet produced a new Actions run visible through the connected run listing, so the fix is not marked CI-verified here.
- Production score, dashboard behavior and live signals remain unchanged.


### Follow-up correction to the MCX comparator import fix — 6 Nov 2026

- The first regression run after adding the import test exposed an unrelated test-environment failure: an earlier partial-file update had temporarily replaced `fetch_and_score.py` with only the import preamble. The failing run was `42210205914` (Component Score Validation), `42210205861` (OI Research Validation), and `42210205811` (NSE/MCX Integration); the affected tests could not find the existing scanner functions because the module had been truncated.
- Restored the complete `fetch_and_score.py` from the last intact checkpoint commit `d1e1ffca90b01d0a6d8d04954bdf173bdea1304b`, then applied the comparator import to the full 236 KB file. Verified from the current branch file that `build_asset_component_breakdowns`, `_asset_search_direction`, and `compare_mcx_bhavcopy_contract_oi` are all present.
- Latest restoration commit: `79e3915f7227ce2d8f88ee22e9d13c99aeab9c38`; report follow-up commit at that checkpoint: `a22206943068bc5c96d17f5fd12951dcad02af1f`. The failed workflow runs above are against the temporary truncated-file commit and must not be treated as current-branch validation. **Superseding validation update:** on head `a22206943068bc5c96d17f5fd12951dcad02af1f`, fresh GitHub Actions runs all completed successfully: Component Score Validation #117 (`42210323542`) and #116 (`42210317445`), NSE/MCX Integration #206 (`42210317214`), and OI Research Validation #35 (`42210317358`). Job-level inspection confirmed tests and syntax steps passed. The restored `fetch_and_score.py` was re-fetched at 236,554 characters and confirmed to contain `build_asset_component_breakdowns`, `_asset_search_direction`, and the MCX comparator import. This validates the restoration/integration tests, not full official NSE UDiFF file coverage.
- The feature branch only was affected; `main`/production was not changed. No merge, deployment, published score or signal change occurred.


### NSE historical options archive route discovered — 6 Nov 2026

- The official NSE Historical Reports page links to the official Historical Contract-wise Price Volume Data page (`/report-detail/fo_eq_security`). The page exposes Instrument, Symbol, Year, Expiry, Option Type, Strike Price and date-range controls, plus CSV download.
- This is a stronger research route for historical index option contract records than relying only on the daily UDiFF download. Next validation must select `OPTIDX`, NIFTY and/or BANKNIFTY, and the relevant CE/PE expiries/date window; then compare returned contract rows and OI against dated UDiFF and the same-date NSE F&O Contract Master.
- The archive page's UI presence is verified, but no downloaded options CSV, complete contract inventory, or actual historical OI sample has yet been validated in this checkpoint. It is a source-discovery result, not proof that the OI parser is complete. SENSEX remains BSE-only.
- Official source: https://www.nseindia.com/report-detail/fo_eq_security (linked from https://www.nseindia.com/static/resources/historical-reports-capital-market-daily-monthly-archives).


### SENSEX/BSE official derivative OI access check — 6 Nov 2026

- BSE's official Equity Derivatives file-format document defines the daily Market Summary file as `MS_<yyyymmdd>-01.csv`. Its fields include Product Type `IO` (Index Options), Asset Code, Expiry Date, Strike Price, Option Type `CE`/`PE`, Close Price and Open Interest. This is structurally suitable for SENSEX option contract OI if the dated file is accessible and its SENSEX asset code/master mapping is validated.
- The same official BSE document states the end-of-day member files are available in `member.bseindia.com`; this does not establish a freely downloadable public archive for the complete daily Market Summary. BSE's public Market Data portal describes Equity Derivatives API access through registration/KYC/data plans. No free, complete dated SENSEX market-summary file has been retrieved in this checkpoint.
- Therefore SENSEX CE/PE OI remains excluded. Do not substitute NSE participant data or infer a SENSEX-specific signal from NIFTY options.
- Official sources: https://www.bseindia.com/downloads1/File_Format_Equity_Derivatives.pdf and https://marketdata.bseindia.com/.


### Fresh full-branch CI verification on latest checkpoint — 6 Nov 2026

The latest feature-branch head `f7cc8a717492da47ed2d3a99d42a915809e3a47a` was associated with three completed GitHub Actions runs, all successful:

- Component Score Validation #119: [run 42211993671](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42211993671). Job steps confirm Python syntax validation, unit/integration tests, dashboard JavaScript extraction and syntax validation all passed.
- NSE/MCX Quote Integration #208: [run 42211993676](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42211993676). Job steps confirm Python syntax, Google Trends/NSE handshake and fallback checks, NSE timestamp and symbol validation, MCX source/freshness parsing, MCX Market Watch parsing, and diagnostic NSE/MCX probes all passed.
- OI Research Validation #37: [run 42211993672](https://github.com/nagji247-png/pdmp-scanner/actions/runs/42211993672). Job steps confirm OI research Python syntax and OI research unit tests passed.

This supersedes the earlier note that fresh validation after the recovery checkpoint was not yet visible. These runs validate the current branch code and tests. They do **not** establish complete official NSE OPTIDX historical CSV coverage, real-file Contract Master reconciliation, predictive validity of any OI signal, or permission to include OI in an asset Final. NSE/MCX OI gates remain closed pending those separate data validations. No production scores or signals were changed.



### Fresh NSE historical OPTIDX + MCX five-session diagnostic — 6 Nov 2026

- On feature head `235fa1ae85e7060eb642c0b8536dcfb0803c99e9`, the NSE/MCX Integration workflow completed successfully (run #213). Its NSE session bootstrap now visits both `/option-chain` and the official historical F&O report page `/report-detail/fo_eq_security`, then applies the report-page Referer and browser request headers.
- NSE `option-chain-contract-info`, `option-chain-v3`, and `historicalOR/foCPV` returned JSON/HTTP 200 for both NIFTY and BANKNIFTY. The historical endpoint returned one dated 5-Nov-2026 row for each tested CE and PE contract, including `FH_OPEN_INT`, `FH_CHANGE_IN_OI`, `FH_TIMESTAMP`, expiry, strike, symbol and option side.
- Important correction: the first diagnostic selected the nearest strike to the **current** option-chain underlying while querying a past date. That is not necessarily the historical ATM strike. These four responses prove the historical API and schema are reachable, but they are not treated as verified historical-ATM samples or complete index OI coverage. A follow-up diagnostic now obtains `FH_UNDERLYING_VALUE` from the dated historical response first and then chooses the nearest strike from the official chain strike list. This corrected selection is pending fresh CI and log verification.
- MCX official Bhav Copy fetch succeeded for all five sessions in the same run: 30-Oct (15,913 rows), 2-Nov (16,296), 3-Nov (16,318), 4-Nov (16,350), 5-Nov (16,402). Exact GOLD and SILVER FUTCOM contracts, expiry 04DEC2026, were uniquely found on all five dates.
- GOLD same-expiry close/OI (₹ / lots): 30-Oct 138,485 / 16,368; 2-Nov 140,186 / 16,142; 3-Nov 139,452 / 16,282; 4-Nov 143,234 / 16,095; 5-Nov 144,095 / 15,716.
- SILVER same-expiry close/OI (₹ / lots): 30-Oct 179,132 / 18,105; 2-Nov 183,779 / 16,933; 3-Nov 179,698 / 16,830; 4-Nov 187,735 / 17,143; 5-Nov 187,140 / 16,701.
- Four adjacent-session diagnostic regimes for GOLD: 5-Nov price-up/OI-down (+₹861, -379 lots); 4-Nov price-up/OI-down (+₹3,782, -187); 3-Nov price-down/OI-up (-₹734, +140); 2-Nov price-up/OI-down (+₹1,701, -226).
- Four adjacent-session diagnostic regimes for SILVER: 5-Nov price-down/OI-down (-₹595, -442 lots); 4-Nov price-up/OI-up (+₹8,037, +313); 3-Nov price-down/OI-down (-₹4,081, -103); 2-Nov price-up/OI-down (+₹4,647, -1,172).
- This confirms the official public MCX Bhav Copy contains usable exact-contract daily OI fields and that same-expiry multi-session comparisons are technically feasible. Four observations are still far too few for predictive validation; both MCX OI components remain excluded from asset Final.
- On head `235fa1ae85e7060eb642c0b8536dcfb0803c99e9`, Component Score Validation #127, OI Research Validation #42 and NSE/MCX Integration #213 all completed PASS. Follow-up commit `a66b8efc77581b27dc3293d9ac7fcf1fd7b71c54` changes the historical strike selection to use the dated underlying; its three CI runs are pending at this report checkpoint.
- No production score, signal, dashboard layout, merge or deployment was changed.


### Corrected historical ATM strike validation — 6 Nov 2026

The follow-up diagnostic on feature commit `a66b8efc77581b27dc3293d9ac7fcf1fd7b71c54` now uses the dated historical row's `FH_UNDERLYING_VALUE` to select the nearest strike from the full official chain strike list. This corrects the earlier current-spot selection; the two spot values were materially different on 5-Nov.

| Asset | 6-Nov chain spot | 5-Nov historical spot | 5-Nov nearest strike | CE OI / change-in-OI | PE OI / change-in-OI |
|---|---:|---:|---:|---:|---:|
| NIFTY | 25,030.35 | 24,536.60 | 24,550 | 4,294,095 / +2,677,935 | 2,999,295 / +2,997,800 |
| BANKNIFTY | 59,086.00 | 57,773.65 | 57,800 | 178,320 / +104,640 | 119,220 / +118,440 |

For each symbol/side the official historical `foCPV` endpoint returned exactly one row dated 05-Nov-2026, matching the requested symbol, expiry, strike and CE/PE. The response also contained close, settlement, volume, OI, change-in-OI and the historical underlying value. NSE integration run #214 completed successfully, as did Component Score Validation #128 and OI Research Validation #43 on the diagnostic code commit.

**Scope limit:** this is one historical ATM strike per index and both option sides, not the full expiry chain or full index OI. The four CE/PE values must not be aggregated into an index component score or mistaken for CLIENT-wide positions. The official daily UDiFF Bhavcopy plus same-date contract master are still required for complete contract inventory, row coverage and exact master reconciliation. No index OI component is enabled.


### Official NSE UDiFF + same-date MII Contract Master audit — 6 Nov 2026

- The GitHub Actions runner downloaded the official 5-Nov-2026 F&O UDiFF Bhavcopy ZIP (1,247,678 bytes) and decompressed its CSV: 39,018 rows, with the expected UDiFF columns including `FinInstrmId`, `FinInstrmTp`, `TckrSymb`, `XpryDt`, `StrkPric`, `OptnTp`, `OpnIntrst` and `ChngInOpnIntrst`.
- The real NSE UDiFF instrument code for index options is `IDO` (legacy normalized name: `OPTIDX`). The parser and tests were corrected to recognize the official `IDO` value; the earlier zero-row result was caused by filtering on the legacy label against the raw UDiFF file.
- Parser output for 5-Nov-2026:
  - NIFTY: 2,050 OPTIDX/IDO rows (1,017 CE; 1,033 PE), 18 expiries; CE OI 266,006,225, CE change +17,581,085; PE OI 343,683,325, PE change +59,165,685.
  - BANKNIFTY: 975 rows (487 CE; 488 PE), 6 expiries; CE OI 15,271,860, CE change +131,940; PE OI 17,720,640, PE change +2,468,400.
- The same-date NSE F&O Contract Master GZ downloaded successfully (1,934,461 bytes; 88,325 rows). Exact `FinInstrmId` join results: NIFTY 2,050/2,050 IDs matched, BANKNIFTY 975/975 matched; zero missing IDs and zero duplicate master IDs. Symbol and CE/PE side also matched for every joined row.
- **Remaining contract-master caveat:** the MII master file's `XpryDt` and `StrkPric` are not in the same representation as the UDiFF Bhavcopy fields. For example, one joined contract has UDiFF expiry `2027-01-25` and strike `23450.00`, while the MII row carries `XpryDt=1485354600` and `StrkPric=2345000`; `DcmlLctr` is blank. The direct date/strike conversion is not yet documented or validated. The exact ID + symbol + side join is strong evidence, but it is not yet a complete expiry/strike identity reconciliation.
- Therefore `coverage_validated=false` remains deliberate. The UDiFF aggregates are real exchange-wide contract OI context, not CLIENT-only positions, and are not yet included in any index Final. Next gate: establish MII expiry/strike field encoding and perform a second dated UDiFF comparison with stable exact-contract keys before any score test.
- On head `839d994ce8d6dd2ebe01f348e6e698af9cc174ac`, Component Score Validation #137, OI Research Validation #51 and NSE/MCX Integration #222 all passed. These validate parser/tests and diagnostic download/joins; they do not close the expiry/strike normalization or predictive-validation gates.
- No production score, signal, dashboard layout, merge or deployment was changed.


### NSE five-session exact-contract OI comparison — 6 Nov 2026

- The official NSE UDiFF F&O Bhavcopy was downloaded successfully for 30-Oct, 2-Nov, 3-Nov, 4-Nov and 5-Nov 2026. Every file parsed with zero duplicate exact-contract keys and zero rejected NIFTY/BANKNIFTY option rows. The comparison key is exact UDiFF `(expiry, strike, CE/PE)`; only contracts present on both adjacent dates are compared.
- All comparisons had zero lot-size mismatches. OI changes below are summed only over the common contract set; newly listed and removed contracts are reported separately. They are exchange-wide index-option positions, not CLIENT-only positions.
- **NIFTY common-contract changes (CE / PE OI lots):**
  - 5-Nov vs 4-Nov: 1,858 common; 192 new; 0 removed. CE +197,733.23 lots; PE +910,241.31 lots.
  - 4-Nov vs 3-Nov: 1,716 common; 142 new; 246 removed. CE +979,748.77; PE +966,418.38.
  - 3-Nov vs 2-Nov: 1,852 common; 110 new; 0 removed. CE +465,548.69; PE +1,165,115.15.
  - 2-Nov vs 30-Oct: 1,694 common; 158 new; 0 removed. CE +436,801.54; PE +526,982.92.
- **BANKNIFTY common-contract changes (CE / PE OI lots):**
  - 5-Nov vs 4-Nov: 935 common; 40 new; 0 removed. CE +4,398 lots; PE +82,280 lots.
  - 4-Nov vs 3-Nov: 925 common; 10 new; 0 removed. CE +15,617; PE +28,196.
  - 3-Nov vs 2-Nov: 925 common; 0 new; 0 removed. CE +4,003; PE +9,664.
  - 2-Nov vs 30-Oct: 925 common; 0 new; 0 removed. CE +21,698; PE +23,471.
- For the latest 5-Nov vs 4-Nov pair, the contract-level close/OI regime counts were also recorded separately by CE and PE. These counts are descriptive only; price/OI regime is not treated as a verified long/short participant position.
- This confirms that five dated NSE files can be retrieved and that adjacent-session OI deltas can be computed on exact common contract keys with lot-size consistency. Four intervals are still too few to validate predictive value, and the changing contract universe (new/removed contracts) must be handled explicitly. No NIFTY/BANKNIFTY OI score is enabled.
- NSE/MCX Integration #224 passed with this five-session diagnostic. Component Score Validation #140 and OI Research Validation #53 also passed on code head `66c869c268aa062639fd43c79db8698b8ed33cf8`.
- No production score, signal, dashboard layout, merge or deployment was changed.


### 60-session NSE option OI candidate test — chronological holdout, 6 Nov 2026

- The exploratory NSE option OI-weighted premium-direction proxy was expanded to 70 weekday candidates. The archive supplied 66 valid sessions from 4-Aug through 5-Nov-2026; 20-Oct and 6-Nov returned no file at the tested URL. This produced 64 next-session observations for each index.
- Candidate formula (research only): exact common `(expiry, strike, CE/PE)` contracts across adjacent dates; require nonzero volume on both dates and unchanged lot size; weight each contract by absolute OI change in lots; CE premium up and PE premium down count as bullish, the reverse as bearish; normalize to -10…+10. This is a heuristic proxy, not participant-identified positions.
- Chronological split: first 44 observations in-sample; final 20 observations held out. No formula parameters were tuned on the holdout.
- NIFTY: in-sample direct 23/44 (52.3%), contrarian 21/44 (47.7%), Pearson -0.199; holdout direct 10/20 (50%), contrarian 10/20 (50%), Pearson +0.138.
- BANKNIFTY: in-sample direct 16/44 (36.4%), contrarian 28/44 (63.6%), Pearson -0.277; holdout direct 8/20 (40%), contrarian 12/20 (60%), Pearson +0.037.
- The holdout correlations are near zero and the hit-rate differences are not persuasive at 20 observations. This does not validate an OI-derived NIFTY or BANKNIFTY component. The 6-Nov UDiFF archive was not available at the checked URL, so the 5-Nov signal's next-session return could not be evaluated. No score is enabled.

### MCX GOLD/SILVER OI breadth candidate test — 43 valid sessions

- The official MCX Bhav Copy helper returned 43 valid sessions from 7-Sep through 5-Nov-2026; 2-Oct and 6-Nov had no contract rows at the tested endpoint.
- The research proxy compared exact common FUTCOM expiries across adjacent sessions, weighted each expiry's price direction by absolute OI change, and benchmarked next-session movement on the nearest exact expiry available on both dates. This is a futures OI-weighted price-direction breadth proxy, not a verified long/short participant measure.
- Chronological split: 28 in-sample observations and 13 holdout observations; no parameter tuning.
- GOLD: in-sample direct 12/28 (42.9%), contrarian 16/28 (57.1%), Pearson -0.262; holdout direct 8/13 (61.5%), contrarian 5/13 (38.5%), Pearson +0.145.
- SILVER: in-sample direct 13/28 (46.4%), contrarian 15/28 (53.6%), Pearson -0.095; holdout direct 5/13 (38.5%), contrarian 8/13 (61.5%), Pearson -0.013.
- The small holdout samples and near-zero correlations do not establish a reliable edge. The gold holdout favoured the direct direction; the silver holdout's 61.5% contrarian hit rate had near-zero correlation and only 13 observations. Both MCX OI components remain excluded from Final.
- On code head `15b39f58a2106cfa1e23a8ec53fc79cefb421ffc`, Component Score Validation #146, OI Research Validation #58 and NSE/MCX Integration #229 all PASS. The longer diagnostics are research-only and did not alter production scoring.


### Full NIFTY 50 and NIFTY Bank basket reconstruction — 6 Nov 2026

- Official NSE Indices monthly archive `indices_dataOct2026.zip` downloaded successfully. Its 30-Oct-2026 PDFs contain all constituents and weights:
  - NIFTY 50: 50 symbols, weight sum 99.98% (rounding), zero duplicate symbols, zero rejected rows.
  - NIFTY Bank: 14 symbols, weight sum 100.00%, zero duplicate symbols, zero rejected rows.
- Official NSE cash-market UDiFF Bhavcopies for 2-Nov, 3-Nov, 4-Nov and 5-Nov were downloaded. Each date supplied all EQ-series symbols required by both baskets: 50/50 NIFTY 50 and 14/14 NIFTY Bank.
- Starting from the official 30-Oct constituent weights and closing prices, daily weights were reconstructed by updating each constituent's weight in proportion to its price return. The weighted basket return was then compared with the official index underlying close from the same-date NSE F&O UDiFF file. This is a reconstructed daily weight series, not a claim that NSE publishes daily constituent weights in this archive.
- Daily basket-vs-index validation:
  - NIFTY 50: 30-Oct→2-Nov +1.681% vs index +1.682% (difference rounds to -0.0 bps); 2-Nov→3-Nov +1.493% vs +1.579% (-8.6 bps); 3-Nov→4-Nov +0.607% vs +0.629% (-2.2 bps); 4-Nov→5-Nov +2.404% vs +2.404% (-0.0 bps).
  - NIFTY Bank: 30-Oct→2-Nov +0.576% vs +0.576%; 2-Nov→3-Nov +0.978% vs +0.978%; 3-Nov→4-Nov +0.673% vs +0.673%; 4-Nov→5-Nov +3.327% vs +3.327%. Differences round to 0.0 bps at displayed precision.
- For 5-Nov, the largest positive NIFTY 50 contributors were ICICIBANK (+0.491 percentage points), HDFCBANK (+0.322), BAJFINANCE (+0.187), M&M (+0.134) and INFY (+0.125). The largest negative contributors were BHARTIARTL (-0.029), NTPC (-0.023), APOLLOHOSP (-0.021), ADANIPORTS (-0.018) and ONGC (-0.018).
- For 5-Nov, the largest positive NIFTY Bank contributors were ICICIBANK (+0.796 pp), HDFCBANK (+0.598), AXISBANK (+0.385), SBIN (+0.277) and INDUSINDBK (+0.250). All 14 constituents were present; the five smallest contributions were positive, so there were no negative contributors in that basket on that date.
- This closes the constituent/price data retrieval and basket-reconstruction gate for NIFTY 50 and NIFTY Bank over these four sessions. The 8.6 bps NIFTY difference on 3-Nov is retained transparently; no attempt was made to force a perfect fit. The raw basket return is a price/breadth component, not yet scaled into a -10…+10 sentiment score. Score scaling and historical validation are still required before it can enter Final.
- **SENSEX remains incomplete:** BSE Index Services returned a 30-stock roster dated 30-Oct-2026 in one successful request, but its roster endpoint does not expose weights and a subsequent request returned an empty response. The official October factsheet PDF was downloaded but yielded no extractable text; a complete 30-stock weight file has not been verified. No equal-weight or NSE-proxy basket is substituted.
- On code head `1c0a6243d6f39ef71ea4844b780a818c43cd2961`, Component Score Validation #154, OI Research Validation #65 and NSE/MCX Integration #236 all PASS. This workflow verifies the official monthly weights, full symbol coverage and four-session basket reconstruction; it does not add the basket to production Final.
- No production score, signal, dashboard layout, merge or deployment was changed.


### Weighted stock-basket breadth score — 5 Nov 2026

A descriptive -10…+10 breadth measure was calculated from the reconstructed prior-day constituent weights:

`breadth_score = 10 × (advancing_weight_fraction − declining_weight_fraction)`

Flat-weight constituents contribute zero. This measures how broadly the constituent basket participated; it is not a crowd/participant position measure and is not yet a predictive signal.

- **NIFTY 50, 5-Nov:** breadth score **+6.53**; 39/50 stocks advanced, representing 82.63% of index weight; 11/50 declined, representing 17.37%.
- **NIFTY Bank, 5-Nov:** breadth score **+10.00**; all 14/14 stocks advanced, representing 100% of index weight; none declined.
- Prior-session breadth scores (30-Oct→2-Nov, 2→3-Nov, 3→4-Nov): NIFTY 50 +4.07, +6.13, +2.77; NIFTY Bank +1.04, +1.73, +2.77.
- These are verified descriptive breadth values based on the full official constituent weights and dated EQ closes. They remain shadow/research-only until a longer historical breadth-score test is completed; they do not contribute to production or Final.


### Weighted stock-basket breadth candidate and helper validation — 6 Nov 2026

The full-basket diagnostic now also calculates a candidate score as:

`10 × (advancing constituent prior-weight − declining constituent prior-weight)`

Flat constituents contribute zero to the difference. This is bounded to [-10,+10]. It is explicitly a *candidate diagnostic*, not an included Final component.

Four-session results from official NSE cash prices and official 30-Oct weights:

| Session | NIFTY 50 candidate | NIFTY advance / decline weight | BANKNIFTY candidate | BANKNIFTY advance / decline weight |
|---|---:|---:|---:|---:|
| 30-Oct → 2-Nov | +4.07 | 70.35% / 29.65% | +1.04 | 53.63% / 43.26% (3.11% flat) |
| 2-Nov → 3-Nov | +6.13 | 80.19% / 18.91% (0.90% flat) | +1.73 | 58.64% / 41.36% |
| 3-Nov → 4-Nov | +2.77 | 63.87% / 36.13% | +2.77 | 63.84% / 36.16% |
| 4-Nov → 5-Nov | +6.53 | 82.63% / 17.37% | +10.00 | 100.00% / 0.00% |

Important interpretation:
- NIFTY and BANKNIFTY are demonstrably different per session; the 3-Nov→4-Nov readings happen to be close, not copied.
- BANKNIFTY's +10.00 on 5-Nov is a genuine ceiling result because all 14 constituents advanced; it is not a forecast or an overbought reading.
- The weighted breadth score is not yet calibrated against next-session returns. Four sessions are source/coverage verification only, not evidence of predictive power.
- A fail-closed reusable helper, `weighted_constituent_breadth_candidate()`, was added to `component_scoring.py`. It rejects missing/duplicate symbols, invalid prices/weights and incomplete weight totals; its output is always marked `included_in_asset_final=false`. Unit tests cover its arithmetic and rejection paths. The helper does not alter production scoring.
- Component Score Validation #162 PASS on helper/test code. OI Research Validation #71 PASS. NSE/MCX Integration #242 was still running its historical-options diagnostic at report time.
- SENSEX full 30-stock weights remain unverified: BSE's official roster endpoint exposes constituents but not weights; its monthly factsheet provides only top-10 weights. Third-party weight lists are not substituted for official dated source data.


### SENSEX weight-source boundary and historical breadth retry — 6 Nov 2026

- BSE's official SENSEX constituents endpoint returned the full 30-stock roster with its 30-Oct-2026 as-of date, but the returned fields are membership, scrip code, name and industry; no constituent weight field was present.
- BSE's official SENSEX October factsheet is available as a PDF. Its published factsheet weight table is titled "Top Constituents by Weightage" and lists only the top ten, not all 30. BSE methodology confirms float-adjusted market-cap weighting; that methodology alone cannot reconstruct exact daily weights without the missing free-float inputs.
- Third-party complete weight tables were found, but are not substituted for a dated official source. SENSEX breadth remains excluded rather than using equal weights, a NIFTY basket or guessed weights.
- First 60-session breadth backtest attempt reached an NSE historical cash-file read timeout. The workflow had `continue-on-error`, so its step was marked success even though the diagnostic itself stopped before producing backtest statistics. No accuracy result is claimed from that run.
- Corrected the diagnostic to catch and report each failed historical date, continue with other dates, and refuse to produce a backtest if fewer than 35 valid dated sessions are retrieved. Latest retry is Integration #244 on code head `2cfcd3441409203c0faffe244b6d003a2c4f2c34`.
- Component Score Validation #165 PASS and OI Research Validation #73 PASS on that same code head. Integration #244 was queued/running at report update time.


### 60-session full-basket breadth backtest — completed 6 Nov 2026

The timeout-resilient workflow completed successfully using official NSE monthly constituent-weight PDFs and dated NSE cash-market Bhavcopies:
- Four monthly weight snapshots verified (Jul/Aug/Sep/Oct 2026): NIFTY 50 had 50 constituents per snapshot; NIFTY Bank had 14. Published weights summed between 99.98% and 100.01%.
- 67 dated cash sessions were downloaded from 3-Aug to 6-Nov; 3 individual dates were skipped after 25-second read timeouts. The workflow continued rather than aborting. Daily basket scores were available for 66 sessions, yielding 65 next-session observations.
- Chronological split: 45 in-sample observations / 20 untouched holdout observations; no parameter tuning.

| Index | In-sample direct | In-sample contrarian | In-sample correlation | Holdout direct | Holdout contrarian | Holdout correlation |
|---|---:|---:|---:|---:|---:|---:|
| NIFTY 50 | 22/45 (48.9%) | 23/45 (51.1%) | -0.160 | 11/20 (55.0%) | 9/20 (45.0%) | -0.091 |
| BANKNIFTY | 19/45 (42.2%) | 26/45 (57.8%) | -0.324 | 8/20 (40.0%) | 12/20 (60.0%) | -0.059 |

Interpretation:
- NIFTY holdout was slightly more often direct than contrarian; the basket-breadth score does not validate a contrarian NIFTY signal.
- BANKNIFTY holdout favored contrarian direction 12/20, but correlation was only -0.059 and 20 observations are too few to establish a reliable edge.
- Both holdout correlations are close to zero. Neither index's breadth candidate is admitted to Final. The 5-Nov descriptive readings remain NIFTY +6.53 and BANKNIFTY +10.00, but they are not trading recommendations or calibrated sentiment.
- This completes a useful rejection gate: full official baskets are retrievable and reconstructable, but their tested short-horizon breadth direction has not earned a score contribution.

Workflow Integration #244 completed successfully with the retry logic. The latest code-only follow-up head `e826b3b9f695560e67ba056b51ae577dde4e21af` also passed Component Score Validation #168 and OI Research Validation #75; Integration #246 is repeating the integration suite on that exact head.


### NSE UDiFF ↔ same-date MII Contract Master exact contract reconciliation — 6 Nov 2026

The official NSE Masters Data v1.6 specification resolves the previously unexplained numeric encodings:
- Master time fields are seconds elapsed from midnight 1-Jan-1980 (not Unix epoch).
- F&O price fields are in paise; divide by 100 to obtain rupees.
- The workflow now normalizes Contract Master expiry and strike using those published units and compares them with the ISO-date / rupee strike in the same-day UDiFF Bhavcopy.

Official NSE 5-Nov-2026 source results:
- UDiFF Bhavcopy: HTTP 200, 39,018 rows.
- Same-date NSE F&O MII Contract Master: HTTP 200, 88,325 rows.
- NIFTY OPTIDX: 2,050 / 2,050 unique instrument IDs matched; zero missing IDs, duplicate master IDs, symbol/side mismatches, expiry mismatches, expiry parse failures, strike mismatches or strike parse failures.
- BANKNIFTY OPTIDX: 975 / 975 unique instrument IDs matched; zero missing IDs, duplicate master IDs, symbol/side mismatches, expiry mismatches, expiry parse failures, strike mismatches or strike parse failures.
- Combined exact contract reconciliation: 3,025 / 3,025; all tested identity and expiry/strike fields match after applying NSE's documented units.
- The parser's per-index exchange-wide CE/PE totals remain available as diagnostics. This does not identify CLIENT-only positions. The existing 60-session OI proxy holdout remains weak (NIFTY direct 10/20, contrarian 10/20, correlation +0.138; BANKNIFTY direct 8/20, contrarian 12/20, correlation +0.037), so no EOD OI directional component is enabled.
- Integration #249 passed this normalized reconciliation on code head `4893eed7c2f4ff862b41e9809db4803b3c84d6f8`. The later manual-only workflow guard does not change the reconciliation logic.


### CLIENT CE/PE Long/Short and Index Futures — latest dated market-wide context

The repository's official participant OI history is updated at `2026-11-06T13:09Z`, but its latest available participant record is still 5-Nov-2026. Comparing 5-Nov with 4-Nov for the CLIENT category:

| CLIENT market-wide field | 4-Nov | 5-Nov | Change |
|---|---:|---:|---:|
| Index CE Long | 2,705,660 | 2,760,218 | +54,558 |
| Index CE Short | 2,613,755 | 2,669,313 | +55,558 |
| Index PE Long | 2,681,228 | 3,318,042 | +636,814 |
| Index PE Short | 3,179,458 | 3,745,090 | +565,632 |
| Index Futures Long | 215,941 | 187,440 | -28,501 |
| Index Futures Short | 66,148 | 82,799 | +16,651 |

- All four CE/PE changes are retained separately; they are not collapsed into one guessed directional score.
- The data is CLIENT participant-wise but market-wide across index F&O, not separately attributable to NIFTY, SENSEX or BANKNIFTY. It is context only, excluded from each asset Final.
- No 6-Nov participant record is present in the repository history as of the 6-Nov 13:09Z update; the values above must be labelled 5-Nov, not live/current 6-Nov data.


### CLIENT participant OI — 6-Nov-2026 record arrived after prior checkpoint

The next automated main-branch scan appended the 6-Nov official NSE participant-wise OI record at 2026-11-06T14:35Z (commit `035c50dabb46fb78c0ec1cc8e2d41d963a58a3d8`). This supersedes the earlier statement above that the repository's latest record was 5-Nov; the 5-Nov comparison remains historically correct.

CLIENT market-wide values, 5-Nov → 6-Nov:

| CLIENT market-wide field | 5-Nov | 6-Nov | Change |
|---|---:|---:|---:|
| Index CE Long | 2,760,218 | 2,906,186 | +145,968 |
| Index CE Short | 2,669,313 | 2,894,792 | +225,479 |
| Index PE Long | 3,318,042 | 4,070,036 | +751,994 |
| Index PE Short | 3,745,090 | 4,474,207 | +729,117 |
| Index Futures Long | 187,440 | 180,828 | -6,612 |
| Index Futures Short | 82,799 | 97,047 | +14,248 |

- The four CE/PE Long/Short changes remain separate. The net changes can be inspected as context, but no single bullish/bearish label is inferred from gross OI additions alone.
- CLIENT Index Futures net (Long minus Short) moved from +104,641 to +83,781, a deterioration of 20,860 contracts. This is market-wide context, not an index-specific futures position.
- The record's explicit scope is participant totals across F&O. It does not identify separate CLIENT positions for NIFTY, SENSEX or BANKNIFTY; therefore it remains excluded from every per-asset Final.
- This new dated record improves freshness of the context data only. It does not validate a predictive edge or authorize a score contribution.
