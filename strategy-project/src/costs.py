from __future__ import annotations

import json
from pathlib import Path

from paths import RAW_DIR


def load_cost_model(path: Path = RAW_DIR / "cost_model.json") -> dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {key: float(value) if isinstance(value, int | float) else value for key, value in raw.items()}


def trade_cost(notional: float, side: str, model: dict[str, float]) -> float:
    bps_key = "buy_cost_bps" if side == "buy" else "sell_cost_bps"
    fee = notional * float(model.get(bps_key, 0.0)) / 10_000.0
    return max(float(model.get("min_fee", 0.0)), fee)


def apply_slippage(price: float, side: str, model: dict[str, float]) -> float:
    direction = 1 if side == "buy" else -1
    return price * (1 + direction * float(model.get("slippage_bps", 0.0)) / 10_000.0)
