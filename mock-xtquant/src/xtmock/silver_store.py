from __future__ import annotations

import os
from pathlib import Path
import threading
from typing import Iterable

import pandas as pd

try:
    import pyarrow.dataset as pa_dataset
except ImportError:  # pragma: no cover - exercised only on minimal installs.
    pa_dataset = None


SILVER_FAMILIES = {
    "1m": "silver_minute_bars_v1",
    "hktransaction": "silver_trade_ticks_v1",
    "hkbrokerqueueex": "silver_broker_queue_v1",
}

MINUTE_COLUMNS = (
    "symbol",
    "bar_ts",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
)
TICK_COLUMNS = (
    "symbol",
    "tick_ts",
    "price",
    "volume",
    "turnover",
    "side",
    "broker_code",
    "broker_name",
    "participant_id",
    "participant_name",
    "trade_id",
    "trade_type",
    "bid_order_id",
    "ask_order_id",
    "active_broker_code",
    "active_broker_name",
    "active_participant_id",
    "active_participant_name",
)
BROKER_QUEUE_COLUMNS = (
    "symbol",
    "queue_ts",
    "side",
    "gear",
    "position",
    "broker_code",
    "broker_name",
    "participant_id",
    "participant_name",
    "order_id",
    "price",
    "volume",
)


class SilverStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._raw_cache: dict[tuple[str, str, tuple[str, ...]], pd.DataFrame] = {}
        self._record_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._cache_lock = threading.RLock()
        self.cache_mode = os.getenv("XTMOCK_SILVER_CACHE_MODE", "symbol").strip().lower()
        self.max_events_per_subscription = max(0, int(os.getenv("XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION", "0") or "0"))

    def has_period(self, period: str) -> bool:
        return _has_parquet_dataset(self.parquet_path_for_period(period)) or self.csv_path_for_period(period).exists()

    def path_for_period(self, period: str) -> Path:
        return self.parquet_path_for_period(period) if _has_parquet_dataset(self.parquet_path_for_period(period)) else self.csv_path_for_period(period)

    def csv_path_for_period(self, period: str) -> Path:
        family = SILVER_FAMILIES.get(str(period))
        if family is None:
            return self.root / "__missing__"
        return self.root / f"{family}.csv"

    def parquet_path_for_period(self, period: str) -> Path:
        family = SILVER_FAMILIES.get(str(period))
        if family is None:
            return self.root / "__missing__"
        return self.root / family

    def symbols(self, period: str) -> list[str]:
        raw = self._raw(period, columns=["symbol"])
        if raw.empty or "symbol" not in raw.columns:
            return []
        return sorted(_normalize_symbol(value) for value in raw["symbol"].dropna().unique())

    def payload_records(self, period: str, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        period = str(period)
        if symbols is None:
            key = (period, "*")
            if key not in self._record_cache:
                self._record_cache[key] = self._build_records(period)
            return self._record_cache[key].copy()

        frames = []
        for symbol in symbols:
            normalized = _normalize_symbol(symbol)
            key = (period, normalized)
            if key not in self._record_cache:
                self._record_cache[key] = self._build_records(period, [normalized])
            frames.append(self._record_cache[key])
        if not frames:
            return pd.DataFrame(columns=["symbol", "event_time", "payload"])
        records = pd.concat(frames, ignore_index=True)
        if records.empty:
            return records.copy()
        return records.reset_index(drop=True)

    def broker_queue_payload_records(
        self,
        symbols: Iterable[str] | None = None,
        *,
        count: int = -1,
    ) -> pd.DataFrame:
        if count and count > 0:
            return self._broker_queue_records(symbols, snapshot_limit=count)
        return self.payload_records("hkbrokerqueueex", symbols)

    def market_dataframe(self, period: str, symbol: str) -> pd.DataFrame:
        records = self.payload_records(period, [symbol])
        if records.empty:
            return pd.DataFrame()
        payloads = records["payload"].tolist()
        df = pd.DataFrame(payloads)
        if df.empty:
            return df
        if "time" in df.columns:
            df.index = df["time"].map(_time_index)
        df.index.name = None
        return df

    def full_tick(self, symbol: str) -> dict:
        symbol = _normalize_symbol(symbol)
        minute_row = self._latest_raw_row("1m", symbol, "bar_ts", columns=MINUTE_COLUMNS)
        tick_row = self._latest_raw_row("hktransaction", symbol, "tick_ts", columns=TICK_COLUMNS)
        price = _safe_float(tick_row.get("price"), _safe_float(minute_row.get("close"), 0.0))
        volume = _safe_int(minute_row.get("volume"), _safe_int(tick_row.get("volume"), 0))
        amount = _safe_float(minute_row.get("turnover"), _safe_float(tick_row.get("turnover"), 0.0))
        event_time = _safe_int(
            _timestamp_scalar(tick_row.get("tick_ts")),
            _safe_int(_timestamp_scalar(minute_row.get("bar_ts")), 0),
        )

        return {
            "time": event_time,
            "timetag": _time_index(event_time) if event_time else "",
            "lastPrice": price,
            "open": _safe_float(minute_row.get("open"), price),
            "high": _safe_float(minute_row.get("high"), price),
            "low": _safe_float(minute_row.get("low"), price),
            "lastClose": _safe_float(minute_row.get("close"), price),
            "amount": amount,
            "volume": volume,
            "pvolume": volume,
            "tickvol": _safe_int(tick_row.get("volume"), 0),
            "stockStatus": 0,
            "openInt": 0,
            "transactionNum": 0,
            "settlementPrice": 0,
            "lastSettlementPrice": 0,
            "pe": 0,
            "askPrice": [0, 0, 0, 0, 0],
            "bidPrice": [0, 0, 0, 0, 0],
            "askVol": [0, 0, 0, 0, 0],
            "bidVol": [0, 0, 0, 0, 0],
        }

    def trading_dates(self, market: str = "") -> list[int]:
        del market
        dates: set[int] = set()
        for period in SILVER_FAMILIES:
            raw = self._raw(period, columns=["trade_date"])
            if "trade_date" in raw.columns:
                for value in raw["trade_date"].dropna().unique():
                    dates.add(_safe_int(value, 0))
        return sorted(date for date in dates if date > 0)

    def _latest_raw_row(
        self,
        period: str,
        symbol: str,
        timestamp_column: str,
        *,
        columns: Iterable[str] | None = None,
    ) -> dict:
        requested_columns = tuple(dict.fromkeys((*tuple(columns or ()), "symbol", timestamp_column)))
        raw = self._raw(period, symbols=[symbol], columns=requested_columns)
        if raw.empty or "symbol" not in raw.columns or timestamp_column not in raw.columns:
            return {}
        df = raw.copy()
        df["symbol"] = df["symbol"].map(_normalize_symbol)
        df = df[df["symbol"] == symbol]
        if df.empty:
            return {}
        return df.sort_values(timestamp_column, kind="mergesort").iloc[-1].to_dict()

    def _build_records(self, period: str, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        if period == "1m":
            return self._minute_records(symbols)
        if period == "hktransaction":
            return self._tick_records(symbols)
        if period == "hkbrokerqueueex":
            return self._broker_queue_records(symbols)
        return pd.DataFrame(columns=["symbol", "event_time", "payload"])

    def _raw(
        self,
        period: str,
        *,
        symbols: Iterable[str] | None = None,
        columns: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        symbol_values = tuple(symbols) if symbols is not None else None
        column_values = tuple(columns) if columns is not None else None
        symbol_key = _symbols_cache_key(symbol_values)
        column_key = tuple(sorted(set(column_values or ())))
        key = (str(period), symbol_key, column_key)
        with self._cache_lock:
            if key in self._raw_cache:
                return self._raw_cache[key]
            if self.cache_mode == "full" and symbol_values is not None:
                full_key = (str(period), "*", column_key)
                if full_key not in self._raw_cache:
                    self._raw_cache[full_key] = self._read_raw(period, symbols=None, columns=column_values)
                df = _filter_raw_symbols(self._raw_cache[full_key], symbol_values)
            else:
                df = self._read_raw(period, symbols=symbol_values, columns=column_values)
            self._raw_cache[key] = df
            return df

    def _read_raw(
        self,
        period: str,
        *,
        symbols: Iterable[str] | None,
        columns: Iterable[str] | None,
    ) -> pd.DataFrame:
        parquet_path = self.parquet_path_for_period(period)
        csv_path = self.csv_path_for_period(period)
        if _has_parquet_dataset(parquet_path) and pa_dataset is not None:
            return _read_parquet_dataset(parquet_path, symbols=symbols, columns=columns)
        if csv_path.exists():
            return _read_csv(csv_path, symbols=symbols, columns=columns)
        return pd.DataFrame()

    def _minute_records(self, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        raw = self._raw("1m", symbols=symbols, columns=MINUTE_COLUMNS)
        if raw.empty:
            return pd.DataFrame(columns=["symbol", "event_time", "payload"])
        df = raw.copy()
        df["symbol"] = df["symbol"].map(_normalize_symbol)
        df = _filter_symbols(df, symbols)
        df["event_time"] = _timestamp_ms(df["bar_ts"])
        df = df.sort_values(["symbol", "event_time"], kind="mergesort")
        df = _limit_rows_per_symbol(df, self.max_events_per_subscription if symbols is not None else 0)
        df["payload"] = [_minute_payload(row) for row in df.to_dict("records")]
        return df[["symbol", "event_time", "payload"]].reset_index(drop=True)

    def _tick_records(self, symbols: Iterable[str] | None = None) -> pd.DataFrame:
        raw = self._raw("hktransaction", symbols=symbols, columns=TICK_COLUMNS)
        if raw.empty:
            return pd.DataFrame(columns=["symbol", "event_time", "payload"])
        df = raw.copy()
        df["symbol"] = df["symbol"].map(_normalize_symbol)
        df = _filter_symbols(df, symbols)
        df["event_time"] = _timestamp_ms(df["tick_ts"])
        sort_columns = ["symbol", "event_time"]
        if "trade_id" in df.columns:
            df["_sort_trade_id"] = df["trade_id"].map(_safe_int)
            sort_columns.append("_sort_trade_id")
        df = df.sort_values(sort_columns, kind="mergesort")
        df = _limit_rows_per_symbol(df, self.max_events_per_subscription if symbols is not None else 0)
        df["payload"] = [_tick_payload(row) for row in df.to_dict("records")]
        return df[["symbol", "event_time", "payload"]].reset_index(drop=True)

    def _broker_queue_records(self, symbols: Iterable[str] | None = None, *, snapshot_limit: int = 0) -> pd.DataFrame:
        raw = self._raw("hkbrokerqueueex", symbols=symbols, columns=BROKER_QUEUE_COLUMNS)
        if raw.empty:
            return pd.DataFrame(columns=["symbol", "event_time", "payload"])
        df = raw.copy()
        df["symbol"] = df["symbol"].map(_normalize_symbol)
        df = _filter_symbols(df, symbols)
        df["event_time"] = _timestamp_ms(df["queue_ts"])
        sort_columns = ["symbol", "event_time"]
        for optional in ("side", "gear", "position", "order_id", "broker_code"):
            if optional in df.columns:
                sort_columns.append(optional)
        df = df.sort_values(sort_columns, kind="mergesort")
        rows = []
        for symbol, group in df.groupby("symbol", sort=True):
            book_rows: dict[tuple[str, str], dict] = {}
            event_times = list(group["event_time"].drop_duplicates())
            selected_event_times = set(event_times[-snapshot_limit:]) if snapshot_limit > 0 else set(event_times)
            for event_time, event_group in group.groupby("event_time", sort=True):
                for _, row in event_group.iterrows():
                    row_dict = row.to_dict()
                    side = str(row_dict.get("side") or "").lower()
                    order_id = _clean_code(row_dict.get("order_id"))
                    if order_id:
                        row_key = (side, f"order:{order_id}")
                    else:
                        row_key = (
                            side,
                            "level:"
                            + "|".join(
                                [
                                    str(_safe_int(row_dict.get("gear"), _safe_int(row_dict.get("position"), 0))),
                                    _clean_code(row_dict.get("broker_code")) or "0",
                                    str(_safe_float(row_dict.get("price"), 0.0)),
                                ]
                            ),
                        )
                    book_rows[row_key] = row_dict
                if event_time not in selected_event_times:
                    continue
                snapshot_group = pd.DataFrame(book_rows.values())
                queues = _broker_queue_levels(snapshot_group)
                queue_ts = str(event_group.iloc[-1].get("queue_ts") or "")
                rows.append(
                    {
                        "symbol": symbol,
                        "event_time": _safe_int(event_time, 0),
                        "payload": {
                            "time": _safe_int(event_time, 0),
                            "Time": _safe_int(event_time, 0),
                            "timestamp": queue_ts,
                            "queue_ts": queue_ts,
                            "askbrokerqueues": queues["ask"],
                            "bidbrokerqueues": queues["bid"],
                            "askQueues": queues["ask"],
                            "bidQueues": queues["bid"],
                        },
                    }
                )
        records = pd.DataFrame(rows, columns=["symbol", "event_time", "payload"])
        return _limit_rows_per_symbol(records, self.max_events_per_subscription if symbols is not None else 0).reset_index(drop=True)


def _has_parquet_dataset(path: Path) -> bool:
    if path.is_file() and path.suffix == ".parquet":
        return True
    if not path.is_dir():
        return False
    return any(path.rglob("*.parquet"))


def _read_parquet_dataset(
    path: Path,
    *,
    symbols: Iterable[str] | None,
    columns: Iterable[str] | None,
) -> pd.DataFrame:
    if pa_dataset is None:
        return pd.DataFrame()
    dataset = pa_dataset.dataset(str(path), format="parquet", partitioning="hive")
    schema_columns = set(dataset.schema.names)
    requested_columns = tuple(columns or ())
    projected_columns = _projected_columns(requested_columns, schema_columns)
    wanted_symbols = _normalized_symbols(symbols)
    filter_expression = None
    if wanted_symbols and "symbol" in schema_columns:
        filter_expression = pa_dataset.field("symbol").isin(sorted(wanted_symbols))
        if requested_columns:
            projected_columns = _projected_columns((*projected_columns, "symbol"), schema_columns)
    table = dataset.to_table(
        columns=list(projected_columns) if requested_columns else None,
        filter=filter_expression,
    )
    return table.to_pandas()


def _read_csv(
    path: Path,
    *,
    symbols: Iterable[str] | None,
    columns: Iterable[str] | None,
) -> pd.DataFrame:
    wanted_columns = set(columns or ())
    wanted_symbols = _normalized_symbols(symbols)
    usecols = None
    if wanted_columns:
        usecols = lambda column: column in wanted_columns or (wanted_symbols and column == "symbol")
    df = pd.read_csv(path, low_memory=False, usecols=usecols)
    if wanted_symbols and "symbol" in df.columns:
        normalized = df["symbol"].map(_normalize_symbol)
        df = df[normalized.isin(wanted_symbols)].copy()
    return df


def _projected_columns(columns: Iterable[str] | None, schema_columns: set[str]) -> tuple[str, ...]:
    if not columns:
        return ()
    return tuple(column for column in dict.fromkeys(columns) if column in schema_columns)


def _normalized_symbols(symbols: Iterable[str] | None) -> set[str]:
    if symbols is None:
        return set()
    return {_normalize_symbol(symbol) for symbol in symbols}


def _filter_raw_symbols(df: pd.DataFrame, symbols: Iterable[str] | None) -> pd.DataFrame:
    wanted = _normalized_symbols(symbols)
    if not wanted or "symbol" not in df.columns:
        return df.copy()
    normalized = df["symbol"].map(_normalize_symbol)
    return df[normalized.isin(wanted)].copy()


def _symbols_cache_key(symbols: Iterable[str] | None) -> str:
    if symbols is None:
        return "*"
    return ",".join(sorted(_normalized_symbols(symbols)))


def _minute_payload(row: pd.Series) -> dict:
    event_time = _safe_int(row.get("event_time"), 0)
    turnover = _safe_float(row.get("turnover"), 0.0)
    close = _safe_float(row.get("close"), 0.0)
    volume = _safe_int(row.get("volume"), 0)
    return {
        "time": event_time,
        "Time": event_time,
        "open": _safe_float(row.get("open"), close),
        "Open": _safe_float(row.get("open"), close),
        "high": _safe_float(row.get("high"), close),
        "High": _safe_float(row.get("high"), close),
        "low": _safe_float(row.get("low"), close),
        "Low": _safe_float(row.get("low"), close),
        "close": close,
        "Close": close,
        "price": close,
        "Price": close,
        "volume": volume,
        "Volume": volume,
        "amount": turnover,
        "Amount": turnover,
        "settelementPrice": 0.0,
        "openInterest": 0,
        "preClose": 0.0,
        "suspendFlag": 0,
    }


def _tick_payload(row: pd.Series) -> dict:
    event_time = _safe_int(row.get("event_time"), 0)
    tick_ts = str(row.get("tick_ts") or "")
    price = _safe_float(row.get("price"), 0.0)
    volume = _safe_int(row.get("volume"), 0)
    turnover = _safe_float(row.get("turnover"), price * volume)
    side = str(row.get("side") or "neutral").lower()
    broker_no = _clean_code(row.get("broker_code"))
    active_broker_no = _clean_code(row.get("active_broker_code"))
    trade_id = _safe_int(row.get("trade_id"), 0)
    bid_order_id = _safe_int(row.get("bid_order_id"), 0)
    ask_order_id = _safe_int(row.get("ask_order_id"), 0)
    return {
        "time": event_time,
        "Time": event_time,
        "timestamp": tick_ts,
        "tick_ts": tick_ts,
        "seq": trade_id,
        "price": price,
        "Price": price,
        "volume": volume,
        "Volume": volume,
        "turnover": turnover,
        "Turnover": turnover,
        "amount": turnover,
        "Amount": turnover,
        "side": side,
        "Side": side,
        "dir": _side_dir(side),
        "Dir": _side_dir(side),
        "tradeType": _safe_int(row.get("trade_type"), 0),
        "trade_type": _safe_int(row.get("trade_type"), 0),
        "brokerNo": _safe_int(broker_no, 0),
        "BrokerNo": broker_no,
        "broker_code": broker_no,
        "broker_name": _clean_text(row.get("broker_name")),
        "BrokerName": _clean_text(row.get("broker_name")),
        "participant_id": _clean_text(row.get("participant_id")),
        "ParticipantID": _clean_text(row.get("participant_id")),
        "participant_name": _clean_text(row.get("participant_name")),
        "ParticipantName": _clean_text(row.get("participant_name")),
        "tradeID": trade_id,
        "trade_id": trade_id,
        "bidOrderID": bid_order_id,
        "bid_order_id": bid_order_id,
        "bidVolume": volume if bid_order_id else 0,
        "askOrderID": ask_order_id,
        "ask_order_id": ask_order_id,
        "askVolume": volume if ask_order_id else 0,
        "cancelFlag": 0,
        "channel": 0,
        "activeBrokerNo": _safe_int(active_broker_no, 0),
        "active_broker_code": active_broker_no,
        "active_broker_name": _clean_text(row.get("active_broker_name")),
        "active_participant_id": _clean_text(row.get("active_participant_id")),
        "active_participant_name": _clean_text(row.get("active_participant_name")),
    }


def _broker_queue_levels(group: pd.DataFrame) -> dict[str, list[dict]]:
    result = {"ask": [], "bid": []}
    if group.empty:
        return result
    work = group.copy()
    for column, default in (("side", ""), ("price", 0.0), ("gear", 0), ("position", 0), ("queue_ts", ""), ("broker_code", ""), ("volume", 0)):
        if column not in work.columns:
            work[column] = default
    work["_side"] = work["side"].map(lambda value: str(value or "").lower())
    work["_price"] = work["price"].map(lambda value: _safe_float(value, 0.0))
    work["_gear"] = work["gear"].map(lambda value: _safe_int(value, 0))
    work["_position"] = work["position"].map(lambda value: _safe_int(value, 0))
    work["_level_position"] = work.apply(
        lambda row: _safe_int(row.get("_gear"), 0) or _safe_int(row.get("_position"), 0),
        axis=1,
    )
    work["_queue_ts"] = work["queue_ts"].map(lambda value: str(value or ""))
    for side in ("ask", "bid"):
        side_rows = work[work["_side"] == side].copy()
        if side_rows.empty:
            continue
        level_groups: list[tuple[int, float, pd.DataFrame]] = []
        for price, price_group in side_rows.groupby("_price", sort=False):
            positive_positions = [
                _safe_int(value, 0)
                for value in price_group["_level_position"].tolist()
                if _safe_int(value, 0) > 0
            ]
            fallback_rank = len(level_groups) + 1
            gear = min(positive_positions) if positive_positions else fallback_rank
            level_groups.append((gear, float(price), price_group))
        level_groups.sort(key=lambda item: (item[0], item[1] if side == "ask" else -item[1]))
        for gear, price, price_group in level_groups:
            price_rows = price_group.sort_values(
                ["_level_position", "_position", "_queue_ts", "broker_code"],
                kind="mergesort",
            )
            broker_volumes: dict[str, int] = {}
            for _, row in price_rows.iterrows():
                broker = _clean_code(row.get("broker_code")) or "0"
                broker_volumes[broker] = broker_volumes.get(broker, 0) + _safe_int(row.get("volume"), 0)
            brokers = list(broker_volumes.keys())
            volumes = [broker_volumes[broker] for broker in brokers]
            result[side].append(
                {
                    "gear": gear,
                    "position": gear,
                    "price": float(price),
                    "brokerCount": len(brokers),
                    "brokers": brokers,
                    "volumes": volumes,
                }
            )
    return result


def _broker_queue_entry(row: pd.Series, index: int) -> dict:
    side = str(row.get("side") or "bid").lower()
    broker_code = _clean_code(row.get("broker_code"))
    position = _safe_int(row.get("position"), index + 1)
    price = _safe_float(row.get("price"), 0.0)
    volume = _safe_int(row.get("volume"), 0)
    order_id = _clean_code(row.get("order_id"))
    return {
        "id": f"{side}-{position}-{broker_code or '0'}-{order_id or index + 1}",
        "side": side,
        "position": position,
        "broker_code": broker_code,
        "brokerCode": broker_code,
        "BrokerID": broker_code,
        "broker_name": _clean_text(row.get("broker_name")),
        "participant_id": _clean_text(row.get("participant_id")),
        "participant_name": _clean_text(row.get("participant_name")),
        "order_id": order_id,
        "price": price,
        "Price": price,
        "volume": volume,
        "Volume": volume,
    }


def _timestamp_ms(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    ns = parsed.astype("int64")
    ms = ns // 1_000_000
    return ms.where(parsed.notna(), 0).astype("int64")


def _timestamp_scalar(value: object) -> int:
    if value in (None, "") or pd.isna(value):
        return 0
    return _safe_int(_timestamp_ms(pd.Series([value])).iloc[0], 0)


def _filter_symbols(df: pd.DataFrame, symbols: Iterable[str] | None) -> pd.DataFrame:
    if symbols is None:
        return df
    wanted = {_normalize_symbol(symbol) for symbol in symbols}
    if not wanted:
        return df.iloc[0:0].copy()
    return df[df["symbol"].isin(wanted)].copy()


def _limit_rows_per_symbol(df: pd.DataFrame, max_rows: int) -> pd.DataFrame:
    if max_rows <= 0 or df.empty or "symbol" not in df.columns:
        return df
    return df.groupby("symbol", sort=False, group_keys=False).head(max_rows).copy()


def _time_index(ms: int) -> str:
    try:
        return pd.Timestamp(int(ms), unit="ms", tz="UTC").tz_convert("Asia/Shanghai").strftime("%Y%m%d%H%M%S")
    except Exception:
        return str(ms)


def _normalize_symbol(symbol: object) -> str:
    text = str(symbol or "").strip().upper()
    if "." not in text and text.isdigit():
        return f"{text.zfill(5)}.HK"
    return text


def _side_dir(side: str) -> int:
    if side == "buy":
        return 1
    if side == "sell":
        return 2
    return 0


def _safe_int(value: object, default: int = 0) -> int:
    if value in (None, "") or pd.isna(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    if value in (None, "") or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_code(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return ""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value).strip()


def _clean_text(value: object) -> str:
    if value in (None, "") or pd.isna(value):
        return ""
    return str(value)
