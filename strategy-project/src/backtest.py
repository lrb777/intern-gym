from __future__ import annotations

import json

import pandas as pd

from costs import load_cost_model
from metrics import calculate_metrics
from paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR
from report_tables import write_report_template
from strategy import generate_baseline_trades


def main() -> int:
    features = pd.read_parquet(PROCESSED_DIR / "features.parquet")
    daily_bars = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    cost_model = load_cost_model()
    trades = generate_baseline_trades(features, daily_bars, cost_model)
    metrics = calculate_metrics(trades)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    trades.to_csv(REPORTS_DIR / "trades.csv", index=False)
    (REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report_template(metrics, REPORTS_DIR / "research_report.md")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
