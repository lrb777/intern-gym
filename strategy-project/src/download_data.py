from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from paths import RAW_DIR


def normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if text.isdigit() and len(text) == 8:
        return text
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text.replace("-", "")
    return parsed.strftime("%Y%m%d")


def fetch_json(base_url: str, path: str, params: dict[str, str] | None = None) -> dict:
    query = f"?{urlencode(params or {})}" if params else ""
    with urlopen(f"{base_url.rstrip('/')}{path}{query}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def download_from_api(base_url: str, start: str, end: str, raw_dir: Path = RAW_DIR) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    universe_payload = fetch_json(base_url, "/api/symbols/ipo-universe", {"start": start, "end": end})
    universe = pd.DataFrame(universe_payload["data"])
    if universe.empty:
        raise RuntimeError("IPO universe is empty for requested date range")

    daily_frames = []
    for symbol in universe["symbol"].astype(str).str.upper().tolist():
        payload = fetch_json(base_url, "/api/daily", {"symbol": symbol, "start": start, "end": end})
        daily_frames.append(pd.DataFrame(payload["data"]))
    daily = pd.concat(daily_frames, ignore_index=True) if daily_frames else pd.DataFrame()
    cost_model = fetch_json(base_url, "/api/cost-model")["data"]

    return write_raw_data(universe, daily, cost_model, raw_dir)


def copy_from_research_data(source_root: Path, raw_dir: Path = RAW_DIR) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    universe = read_table(source_root, "ipo_universe")
    daily = read_table(source_root, "daily_bars")
    cost_model = json.loads((source_root / "cost_model.json").read_text(encoding="utf-8"))
    return write_raw_data(universe, daily, cost_model, raw_dir)


def read_table(root: Path, name: str) -> pd.DataFrame:
    parquet = root / f"{name}.parquet"
    csv = root / f"{name}.csv"
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv)
    raise FileNotFoundError(f"missing table {name} in {root}")


def write_raw_data(universe: pd.DataFrame, daily: pd.DataFrame, cost_model: dict, raw_dir: Path) -> dict[str, object]:
    universe = normalize_universe(universe)
    daily = normalize_daily(daily)
    universe.to_parquet(raw_dir / "ipo_universe.parquet", index=False)
    daily.to_parquet(raw_dir / "daily_bars.parquet", index=False)
    (raw_dir / "cost_model.json").write_text(json.dumps(cost_model, ensure_ascii=False, indent=2), encoding="utf-8")
    coverage = coverage_summary(universe, daily)
    (raw_dir / "coverage_summary.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    return coverage


def normalize_universe(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    for column in ("coverage_start", "coverage_end"):
        result[column] = result[column].map(normalize_date)
    if "name" not in result.columns:
        result["name"] = ""
    return result[["symbol", "name", "coverage_start", "coverage_end"]].sort_values(["coverage_start", "symbol"])


def normalize_daily(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["trade_date"] = result["trade_date"].map(normalize_date)
    for column in ("open", "high", "low", "close", "volume", "turnover", "previous_close", "suspend_flag"):
        if column not in result.columns:
            result[column] = 0
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0)
    return result[
        ["symbol", "trade_date", "open", "high", "low", "close", "volume", "turnover", "previous_close", "suspend_flag"]
    ].sort_values(["symbol", "trade_date"])


def coverage_summary(universe: pd.DataFrame, daily: pd.DataFrame) -> dict[str, object]:
    daily_keys = daily[["symbol", "trade_date"]]
    duplicate_keys = int(daily_keys.duplicated().sum())
    daily_symbols = set(daily["symbol"].unique())
    universe_symbols = set(universe["symbol"].unique())
    return {
        "symbol_count": int(len(universe_symbols)),
        "daily_rows": int(len(daily)),
        "date_min": str(daily["trade_date"].min() or ""),
        "date_max": str(daily["trade_date"].max() or ""),
        "missing_daily_symbols": sorted(universe_symbols - daily_symbols),
        "duplicate_daily_keys": duplicate_keys,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download daily IPO strategy data from mock-research-api or research-data.")
    parser.add_argument("--base-url", default="http://127.0.0.1:9041")
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="")
    parser.add_argument("--output-root", type=Path, default=RAW_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.source_root is not None:
        coverage = copy_from_research_data(args.source_root, args.output_root)
    else:
        coverage = download_from_api(args.base_url, args.start, args.end, args.output_root)
    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
