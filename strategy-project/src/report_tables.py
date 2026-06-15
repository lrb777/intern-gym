from __future__ import annotations

from pathlib import Path


def write_report_template(metrics: dict[str, float], path: Path) -> None:
    content = f"""# IPO / New Listing Daily Strategy Research

## Executive Summary

Baseline scaffold result:

- trade_count: {metrics.get("trade_count", 0)}
- win_rate: {metrics.get("win_rate", 0.0):.4f}
- total_return: {metrics.get("total_return", 0.0):.4f}
- max_drawdown: {metrics.get("max_drawdown", 0.0):.2f}

Replace this section with the candidate's final interpretation.

## Data

Document API download coverage, missing values, suspended or inactive symbols, and any independently researched IPO or grey-market sources.

## Strategy Definition

Describe the first-trading-day baseline, improved version, execution model, cost model, and no-lookahead safeguards.

## Results

Include baseline vs improved metrics, trade logs, cost sensitivity, and symbol/listing-day breakdowns.

## Analysis

Explain where the strategy works, where it fails, and whether the improvement is robust.

## Next Steps

List additional data, execution modeling, or risk controls required before this could be considered production research.
"""
    path.write_text(content, encoding="utf-8")
