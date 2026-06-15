from __future__ import annotations

import pandas as pd


def calculate_metrics(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "average_win": 0.0,
            "average_loss": 0.0,
            "profit_factor": 0.0,
            "total_return": 0.0,
            "max_drawdown": 0.0,
            "turnover": 0.0,
            "average_holding_days": 0.0,
        }

    returns = trades["return"].astype(float)
    pnl = trades["net_pnl"].astype(float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    equity = pnl.cumsum()
    drawdown = equity - equity.cummax()
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    if "holding_days" in trades.columns:
        holding_days = pd.to_numeric(trades["holding_days"], errors="coerce").fillna(0)
    else:
        holding_days = (
            pd.to_datetime(trades["exit_date"], format="%Y%m%d", errors="coerce")
            - pd.to_datetime(trades["entry_date"], format="%Y%m%d", errors="coerce")
        ).dt.days + 1

    return {
        "trade_count": int(len(trades)),
        "win_rate": float((returns > 0).mean()),
        "average_return": float(returns.mean()),
        "average_win": float(wins.mean()) if not wins.empty else 0.0,
        "average_loss": float(losses.mean()) if not losses.empty else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else 0.0,
        "total_return": float(returns.sum()),
        "max_drawdown": float(drawdown.min()) if not drawdown.empty else 0.0,
        "turnover": float(trades["entry_price"].mul(trades["shares"]).sum()),
        "average_holding_days": float(holding_days.mean()) if not holding_days.empty else 0.0,
    }
