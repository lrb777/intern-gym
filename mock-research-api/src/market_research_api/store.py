from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def normalize_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit() and len(text) == 8:
        return text
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text.replace("-", "")
    return parsed.strftime("%Y%m%d")


class ResearchStore:
    def __init__(self, root: Path):
        self.root = root
        self.universe = self._read_frame("ipo_universe")
        self.daily = self._read_frame("daily_bars")
        self.cost_model = json.loads((root / "cost_model.json").read_text(encoding="utf-8"))
        self.metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        self.universe["symbol"] = self.universe["symbol"].astype(str).str.upper()
        self.daily["symbol"] = self.daily["symbol"].astype(str).str.upper()
        self.universe["coverage_start"] = self.universe["coverage_start"].map(normalize_date)
        self.universe["coverage_end"] = self.universe["coverage_end"].map(normalize_date)
        self.daily["trade_date"] = self.daily["trade_date"].map(normalize_date)

    def new_listings(self, start: str = "", end: str = "") -> list[dict[str, Any]]:
        frame = self.universe.copy()
        start_date = normalize_date(start)
        end_date = normalize_date(end)
        if start_date:
            frame = frame[frame["coverage_start"] >= start_date]
        if end_date:
            frame = frame[frame["coverage_start"] <= end_date]
        return frame.sort_values(["coverage_start", "symbol"]).to_dict("records")

    def daily_bars(self, symbol: str, start: str = "", end: str = "") -> list[dict[str, Any]] | None:
        normalized = str(symbol or "").upper().strip()
        if not normalized:
            return None
        if normalized not in set(self.universe["symbol"]):
            return None
        frame = self.daily[self.daily["symbol"] == normalized].copy()
        start_date = normalize_date(start)
        end_date = normalize_date(end)
        if start_date:
            frame = frame[frame["trade_date"] >= start_date]
        if end_date:
            frame = frame[frame["trade_date"] <= end_date]
        return frame.sort_values("trade_date").to_dict("records")

    def as_of(self) -> str:
        return str(self.metadata.get("as_of") or "")

    def _read_frame(self, name: str) -> pd.DataFrame:
        parquet = self.root / f"{name}.parquet"
        csv = self.root / f"{name}.csv"
        if parquet.exists():
            return pd.read_parquet(parquet)
        if csv.exists():
            return pd.read_csv(csv)
        raise FileNotFoundError(f"missing research data table: {name}")
