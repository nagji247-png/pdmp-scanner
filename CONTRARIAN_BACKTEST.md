# Offline contrarian market backtest

This is a research-only evaluator. It does not call Google Trends, NSE, BSE, Yahoo Finance or MCX, and it does not read or modify data.json.

## Signal and outcome contract

Use one end-of-session crowd snapshot per asset and exchange-local market date. Positive score means bullish crowd; negative score means bearish crowd. The contrarian forecast is the opposite direction.

Signal rows require: asset, signal_date, known_on, score, source, observed_at.
Close rows require: asset, market_date, close, source.

Example signal: {"asset":"NIFTY","signal_date":"2026-11-02","known_on":"2026-11-02","score":-6.0,"source":"dated crowd component archive","observed_at":"2026-11-02T10:00:00Z"}

Example close: {"asset":"NIFTY","market_date":"2026-11-02","close":24800.0,"source":"official daily close archive"}

The evaluator uses the signal-date close as the base and the next available session close as the outcome. known_on must not be later than signal_date. Conflicting duplicate closes fail closed. Multiple snapshots on the same asset/date are reduced to the latest observed_at.

## Run locally

python offline_contrarian_market_backtest.py signals.json closes.json --threshold 1 --out report.json

The report includes per-asset and combined contrarian accuracy, crowd-follow benchmark accuracy, average next-session return, signed contrarian return, sample counts, skipped rows and each evaluated trade.

## Important limitations

- This engine is not evidence of an edge until real, correctly dated historical crowd-score snapshots are paired with official closes for the same assets.
- history.csv stores intraday change_pct and score observations. It is not a daily close archive and must not be treated as one.
- NSE/MCX OI archives are separate diagnostic datasets, not historical crowd sentiment snapshots. They cannot be substituted for missing signals.
- Direction accuracy is not option buying profitability. Premiums, IV, theta, spreads, slippage, stop-losses and expiry are not modeled.
- A small sample is descriptive only. No performance claim should be made until a sufficiently large out-of-sample period is available.

This tool is offline by design: provider_calls=0 and production_score_modified=false are included in every report.