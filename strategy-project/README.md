# Strategy Project: IPO / New Listing Daily Research

This scaffold is for the strategy internship project. The provided data is intentionally limited to:

- IPO universe coverage from the research daily dataset
- daily OHLCV bars
- cost model

IPO fundamentals, issue pricing, subscription multiples, sponsors, and grey-market data are not provided. Candidates must research those public data sources independently, store them under `data/external/`, and record source URLs or source notes.

## Run

Start the research API from the repository root:

```bash
make serve-research
```

Then run the strategy pipeline:

```bash
python src/download_data.py --base-url http://127.0.0.1:9041 --start 2026-01-01
python src/build_features.py
python src/backtest.py
```

Local fallback, useful for tests:

```bash
python src/download_data.py --source-root ../research-data
```

Outputs:

```text
data/raw/ipo_universe.parquet
data/raw/daily_bars.parquet
data/raw/cost_model.json
data/raw/coverage_summary.json
data/processed/features.parquet
reports/trades.csv
reports/metrics.json
reports/research_report.md
```

## Baseline

The scaffold implements a simple first-trading-day daily momentum baseline:

1. Treat the first daily bar in the provided coverage as day 1.
2. If `day_1 close / day_1 open - 1 > threshold`, enter at day 2 open.
3. Hold for a fixed number of trading days, with optional stop-loss/take-profit.
4. Deduct buy/sell costs, slippage, and minimum fees.

Candidates should improve this baseline and compare results.

## External Research Templates

Use these templates for independently researched data:

```text
data/external/ipo_info_template.csv
data/external/grey_market_template.csv
```

Do not fill missing public data with zero. Leave missing values blank and explain coverage limitations in the report.
