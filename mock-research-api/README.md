# mock-research-api

HTTP historical data API for the strategy internship project.

This service intentionally provides only:

- 2026 IPO universe coverage from the provided daily dataset
- daily bars
- cost model
- metadata

Current bundled dataset: 65 ordinary 2026 HK IPO symbols, 3,673 daily rows, through 2026-06-15.

It does not provide IPO fundamentals, issue pricing, subscription multiples, or grey-market data. Strategy candidates must research those public data sources independently and record their sources.

## Run

```bash
PYTHONPATH=mock-research-api/src \
RESEARCH_DATA_ROOT=research-data \
python -m market_research_api.server --host 0.0.0.0 --port 9041
```

## Endpoints

```text
GET /health
GET /api/metadata
GET /api/cost-model
GET /api/symbols/ipo-universe?start=2026-01-01&end=2026-06-15
GET /api/daily?symbol=02723.HK&start=2026-06-01&end=2026-06-15
```
