from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from build_features import build_daily_ipo_features
from costs import load_cost_model
from metrics import calculate_metrics
from strategy import generate_baseline_trades


def test_strategy_scaffold_builds_daily_features_and_trades():
    universe = pd.read_parquet(REPO_ROOT / "research-data" / "ipo_universe.parquet")
    daily_bars = pd.read_parquet(REPO_ROOT / "research-data" / "daily_bars.parquet")
    features = build_daily_ipo_features(universe, daily_bars, threshold=-1.0)
    cost_model = load_cost_model(REPO_ROOT / "research-data" / "cost_model.json")
    trades = generate_baseline_trades(features, daily_bars, cost_model)
    metrics = calculate_metrics(trades)

    assert not features.empty
    assert set(features.columns) >= {"symbol", "trade_date_1", "entry_date", "first_day_return_vs_open", "baseline_signal"}
    assert set(trades.columns) >= {"symbol", "entry_date", "exit_date", "net_pnl", "strategy_version"}
    assert set(metrics) >= {"trade_count", "win_rate", "total_return", "max_drawdown", "average_holding_days"}
