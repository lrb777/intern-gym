from __future__ import annotations

import argparse
import json

import pandas as pd

from build_features import build_daily_ipo_features
from costs import load_cost_model
from metrics import calculate_metrics
from paths import PROCESSED_DIR, RAW_DIR, REPORTS_DIR
from strategy import generate_baseline_trades, generate_volume_filtered_trades


STRATEGIES = {
    "baseline": generate_baseline_trades,
    "volume_filtered": generate_volume_filtered_trades,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strategy backtest.")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Override signal threshold (default: use pre-built features)")
    parser.add_argument("--strategy", choices=list(STRATEGIES), default="baseline",
                        help="Strategy version to run (default: baseline)")
    parser.add_argument("--volume-percentile", type=float, default=0.5,
                        help="Volume/turnover percentile threshold for volume_filtered strategy")
    parser.add_argument("--compare", action="store_true",
                        help="Run both baseline and volume_filtered and print comparison")
    return parser.parse_args()


def run_strategy(strategy_name: str, features: pd.DataFrame, daily_bars: pd.DataFrame,
                 cost_model: dict, args: argparse.Namespace,
                 trades_path: str, metrics_path: str) -> dict:
    strategy_fn = STRATEGIES[strategy_name]
    if strategy_name == "volume_filtered":
        trades = strategy_fn(
            features, daily_bars, cost_model,
            volume_percentile=args.volume_percentile,
        )
    else:
        trades = strategy_fn(features, daily_bars, cost_model)

    metrics = calculate_metrics(trades)
    metrics["strategy"] = strategy_name
    if strategy_name == "volume_filtered":
        metrics["volume_percentile"] = args.volume_percentile

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    trades.to_csv(REPORTS_DIR / trades_path, index=False)
    (REPORTS_DIR / metrics_path).write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    return metrics


def main() -> int:
    args = parse_args()

    if args.threshold is not None:
        universe = pd.read_parquet(RAW_DIR / "ipo_universe.parquet")
        daily_bars = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
        features = build_daily_ipo_features(universe, daily_bars, threshold=args.threshold)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        features.to_parquet(PROCESSED_DIR / "features.parquet", index=False)
    else:
        features = pd.read_parquet(PROCESSED_DIR / "features.parquet")

    daily_bars = pd.read_parquet(RAW_DIR / "daily_bars.parquet")
    cost_model = load_cost_model()

    if args.compare:
        print("=" * 60)
        print("STRATEGY COMPARISON: baseline vs volume_filtered")
        print("=" * 60)

        baseline_metrics = run_strategy(
            "baseline", features, daily_bars, cost_model, args,
            trades_path="trades.csv", metrics_path="metrics.json")
        improved_metrics = run_strategy(
            "volume_filtered", features, daily_bars, cost_model, args,
            trades_path="volume_filtered_trades.csv", metrics_path="volume_filtered_metrics.json")

        key_fields = [
            ("trade_count", "Trade Count"),
            ("win_rate", "Win Rate"),
            ("total_return", "Total Return"),
            ("max_drawdown", "Max Drawdown"),
            ("profit_factor", "Profit Factor"),
            ("average_return", "Avg Return"),
            ("average_holding_days", "Avg Holding Days"),
        ]

        print(f"\n{'Metric':<25} {'Baseline':>12} {'Improved':>12} {'Delta':>12}")
        print("-" * 65)
        for field, label in key_fields:
            b = baseline_metrics.get(field, 0)
            i = improved_metrics.get(field, 0)
            if isinstance(b, float):
                delta = i - b
                print(f"{label:<25} {b:>12.4f} {i:>12.4f} {delta:>+12.4f}")
            else:
                print(f"{label:<25} {b:>12} {i:>12} {i-b:>+12}")

        comparison = {
            "baseline": baseline_metrics,
            "volume_filtered": improved_metrics,
        }
        (REPORTS_DIR / "comparison.json").write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nComparison saved to reports/comparison.json")

    else:
        metrics = run_strategy(
            args.strategy, features, daily_bars, cost_model, args,
            trades_path="trades.csv", metrics_path="metrics.json")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
