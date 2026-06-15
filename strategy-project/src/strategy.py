from __future__ import annotations

import pandas as pd

from costs import apply_slippage, trade_cost


def generate_baseline_trades(
    features: pd.DataFrame,
    daily_bars: pd.DataFrame,
    cost_model: dict[str, float],
    *,
    notional_per_trade: float = 100_000.0,
    holding_days: int = 3,
    stop_loss_pct: float = 0.08,
    take_profit_pct: float = 0.20,
) -> pd.DataFrame:
    bars = normalize_daily(daily_bars)
    trades = []

    for feature in features[features["baseline_signal"]].to_dict("records"):
        symbol = str(feature["symbol"])
        entry_date = str(feature["entry_date"])
        symbol_bars = bars[bars["symbol"] == symbol].sort_values("trade_date").reset_index(drop=True)
        entry_matches = symbol_bars[symbol_bars["trade_date"] == entry_date]
        if entry_matches.empty:
            continue
        entry_index = int(entry_matches.index[0])
        path = symbol_bars.iloc[entry_index : entry_index + max(1, holding_days)]
        if path.empty:
            continue

        entry_row = path.iloc[0]
        entry_raw = float(entry_row["open"])
        entry_price = apply_slippage(entry_raw, "buy", cost_model)
        shares = int(notional_per_trade // entry_price) if entry_price > 0 else 0
        if shares <= 0:
            continue

        exit_row = path.iloc[-1]
        exit_reason = "holding_period"
        stop_level = entry_price * (1 - stop_loss_pct)
        take_profit_level = entry_price * (1 + take_profit_pct)
        for _, row in path.iterrows():
            low = float(row["low"])
            high = float(row["high"])
            if low <= stop_level:
                exit_row = row
                exit_reason = "stop_loss"
                break
            if high >= take_profit_level:
                exit_row = row
                exit_reason = "take_profit"
                break
        holding_days = int(path[path["trade_date"] <= str(exit_row["trade_date"])].shape[0])

        exit_raw = float(exit_row["close"])
        exit_price = apply_slippage(exit_raw, "sell", cost_model)
        buy_notional = entry_price * shares
        sell_notional = exit_price * shares
        buy_fee = trade_cost(buy_notional, "buy", cost_model)
        sell_fee = trade_cost(sell_notional, "sell", cost_model)
        gross_pnl = sell_notional - buy_notional
        fees = buy_fee + sell_fee
        slippage = abs(entry_price - entry_raw) * shares + abs(exit_raw - exit_price) * shares
        net_pnl = gross_pnl - fees

        trades.append(
            {
                "symbol": symbol,
                "coverage_start": str(feature.get("coverage_start") or ""),
                "entry_date": str(entry_row["trade_date"]),
                "entry_price": entry_price,
                "exit_date": str(exit_row["trade_date"]),
                "exit_price": exit_price,
                "shares": shares,
                "gross_pnl": gross_pnl,
                "fees": fees,
                "slippage": slippage,
                "net_pnl": net_pnl,
                "return": net_pnl / buy_notional if buy_notional else 0.0,
                "exit_reason": exit_reason,
                "holding_days": holding_days,
                "strategy_version": "baseline_first_day_momentum_daily",
            }
        )

    return pd.DataFrame(trades)


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["trade_date"] = result["trade_date"].astype(str).str.replace("-", "", regex=False)
    for column in ("open", "high", "low", "close", "volume", "turnover"):
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    return result
