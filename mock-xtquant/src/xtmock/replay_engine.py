from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd

from .catalog import RecordingCatalog
from .config import MockConfig, load_config
from .market_clock import get_replay_clock
from .silver_store import SilverStore

try:
    from .parquet_store import ParquetStore
except ImportError:
    ParquetStore = None


PERIOD_DATASET = {
    "l2quote": "l2quote_raw",
    "full_tick": "full_tick_raw",
    "1d": "kline_1d_raw",
    "hktransaction": "hktransaction_raw",
    "hkorder": "hkorder_raw",
    "hkorderaux": "hkorderaux_raw",
    "l2thousand": "l2thousand_raw",
}

PERIOD_COLUMNS = {
    "1m": [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "settelementPrice",
        "openInterest",
        "preClose",
        "suspendFlag",
    ],
    "l2quote": [
        "time",
        "lastPrice",
        "open",
        "high",
        "low",
        "amount",
        "volume",
        "pvolume",
        "openInt",
        "stockStatus",
        "transactionNum",
        "lastClose",
        "lastSettlementPrice",
        "settlementPrice",
        "pe",
        "askPrice",
        "bidPrice",
        "askVol",
        "bidVol",
    ],
    "1d": [
        "time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "settelementPrice",
        "openInterest",
        "preClose",
        "suspendFlag",
    ],
    "hktransaction": [
        "time",
        "seq",
        "price",
        "volume",
        "dir",
        "tradeType",
        "brokerNo",
        "tradeID",
        "bidOrderID",
        "bidVolume",
        "askOrderID",
        "askVolume",
        "cancelFlag",
        "channel",
        "activeBrokerNo",
    ],
    "hkorder": [
        "time",
        "seq",
        "price",
        "volume",
        "preVolume",
        "orderId",
        "orderType",
        "level",
        "brokerNo",
        "channel",
        "extend",
    ],
    "hkorderaux": ["time", "seq", "orderId", "brokerNo"],
    "l2thousand": ["time", "askPrice", "askVolume", "bidPrice", "bidVolume", "price", "totalVol"],
    "hkbrokerqueueex": ["time", "askbrokerqueues", "bidbrokerqueues"],
}

PERIOD_DTYPES = {
    "1m": {
        "time": "int64",
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "int64",
        "amount": "float64",
        "settelementPrice": "float64",
        "openInterest": "int64",
        "preClose": "float64",
        "suspendFlag": "int32",
    },
    "l2quote": {
        "time": "int64",
        "lastPrice": "float64",
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "amount": "float64",
        "volume": "int64",
        "pvolume": "int64",
        "openInt": "int32",
        "stockStatus": "int32",
        "transactionNum": "int32",
        "lastClose": "float64",
        "lastSettlementPrice": "float64",
        "settlementPrice": "float64",
        "pe": "float64",
        "askPrice": "object",
        "bidPrice": "object",
        "askVol": "object",
        "bidVol": "object",
    },
    "1d": {
        "time": "int64",
        "open": "float64",
        "high": "float64",
        "low": "float64",
        "close": "float64",
        "volume": "int64",
        "amount": "float64",
        "settelementPrice": "float64",
        "openInterest": "int64",
        "preClose": "float64",
        "suspendFlag": "int32",
    },
    "hktransaction": {
        "time": "int64",
        "seq": "int64",
        "price": "float64",
        "volume": "int64",
        "dir": "int32",
        "tradeType": "int32",
        "brokerNo": "int32",
        "tradeID": "int32",
        "bidOrderID": "int64",
        "bidVolume": "int64",
        "askOrderID": "int64",
        "askVolume": "int64",
        "cancelFlag": "int32",
        "channel": "int32",
        "activeBrokerNo": "int32",
    },
    "hkorder": {
        "time": "int64",
        "seq": "int64",
        "price": "float64",
        "volume": "int64",
        "preVolume": "int64",
        "orderId": "int64",
        "orderType": "int32",
        "level": "int32",
        "brokerNo": "int32",
        "channel": "int32",
        "extend": "int32",
    },
    "hkorderaux": {
        "time": "int64",
        "seq": "int64",
        "orderId": "int64",
        "brokerNo": "int32",
    },
}


@dataclass
class Subscription:
    seq: int
    dataset: str
    symbol: str
    callback: Callable | None
    gear_num: int | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class ReplayEngine:
    def __init__(self, config: MockConfig | None = None):
        self.config = config or load_config()
        self.catalog = self._discover_catalog()
        self.store = ParquetStore(self.catalog) if self.catalog is not None and ParquetStore is not None else None
        self.silver = SilverStore(self.config.silver_root)
        self.clock = get_replay_clock()
        self._seq = itertools.count(1)
        self._subscriptions: dict[int, Subscription] = {}

    def reconnect(self) -> "ReplayEngine":
        return ReplayEngine(load_config())

    def _discover_catalog(self) -> RecordingCatalog | None:
        try:
            return RecordingCatalog.discover(self.config)
        except FileNotFoundError:
            return None

    def get_full_tick(self, code_list: list[str]) -> dict[str, dict]:
        records = self._parquet_payload_records("full_tick_raw", code_list)
        result = {}
        for code in code_list:
            rows = records[records["symbol"] == code]
            if not rows.empty:
                result[code] = dict(rows.iloc[-1]["payload"])
            elif self.silver.has_period("1m") or self.silver.has_period("hktransaction"):
                result[code] = self.silver.full_tick(code)
            else:
                result[code] = _synthetic_full_tick(code)
        return result

    def get_market_data_ex(
        self,
        field_list=None,
        stock_list=None,
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
        dividend_type: str = "none",
        fill_data: bool = True,
    ) -> dict:
        del dividend_type, fill_data
        field_list = list(field_list or [])
        stock_list = list(stock_list or [])
        if not stock_list:
            return {}
        if self.silver.has_period(period):
            if period == "hkbrokerqueueex":
                result: dict[str, pd.DataFrame] = {}
                for symbol in stock_list:
                    records = self.silver.broker_queue_payload_records([symbol], count=count)
                    records = _filter_records_time(records, start_time, end_time)
                    if count == 0:
                        records = records.iloc[0:0]
                    elif (start_time or end_time) and count and count > 0:
                        records = records.tail(count)
                    payloads = [dict(payload) for payload in records["payload"].tolist()]
                    df = _payloads_to_dataframe(payloads, period)
                    columns = field_list if field_list else PERIOD_COLUMNS.get(period, list(df.columns))
                    result[symbol] = _select_columns(df, columns)
                return result
            result: dict[str, pd.DataFrame] = {}
            for symbol in stock_list:
                df = self.silver.market_dataframe(period, symbol)
                if df.empty:
                    df = _empty_dataframe(period)
                filtered = _filter_time(df, start_time, end_time)
                if not filtered.empty or not (start_time or end_time):
                    df = filtered
                if count == 0:
                    df = df.iloc[0:0]
                elif count and count > 0:
                    df = df.tail(count)
                columns = field_list if field_list else PERIOD_COLUMNS.get(period, list(df.columns))
                result[symbol] = _select_columns(df, columns)
            return result
        dataset = PERIOD_DATASET.get(period, period)
        if dataset == period and not self._has_parquet_dataset(dataset):
            print(f"周期错误{period}, 可以用<get_period_list>函数获取支持的周期")
            return {}
        records = self._parquet_payload_records(dataset, stock_list or None)
        result: dict[str, pd.DataFrame] = {}
        for symbol in stock_list:
            rows = records[records["symbol"] == symbol]
            df = _payloads_to_dataframe(rows["payload"].tolist(), period)
            df = _filter_time(df, start_time, end_time)
            if count == 0:
                df = df.iloc[0:0]
            elif count and count > 0:
                df = df.tail(count)
            columns = field_list if field_list else PERIOD_COLUMNS.get(period, list(df.columns))
            result[symbol] = _select_columns(df, columns)
        return result

    def get_market_data(self, field_list=None, stock_list=None, period: str = "1d", **kwargs):
        data = self.get_market_data_ex(field_list or [], stock_list or [], period, **kwargs)
        if period == "1d":
            fields = list(field_list or PERIOD_COLUMNS["1d"])
            output: dict[str, pd.DataFrame] = {}
            for field_name in fields:
                series_rows = {}
                for symbol, df in data.items():
                    if field_name not in df.columns:
                        continue
                    cols = df.index.astype(str).tolist()
                    values = df[field_name].tolist()
                    series_rows[symbol] = dict(zip(cols, values))
                output[field_name] = pd.DataFrame.from_dict(series_rows, orient="index")
            return output
        if period == "l2quote":
            return {symbol: _dataframe_to_records_array(df) for symbol, df in data.items()}
        return data

    def get_instrument_detail(self, stock_code: str, iscomplete: bool = False):
        del iscomplete
        records = self._parquet_payload_records("instrument_detail_raw", [stock_code])
        if records.empty:
            return self._synthetic_instrument_detail(stock_code)
        return dict(records.iloc[-1]["payload"])

    def get_instrument_detail_list(self, stock_list: list[str], iscomplete: bool = False):
        return {symbol: self.get_instrument_detail(symbol, iscomplete=iscomplete) for symbol in stock_list}

    def get_trading_dates(self, market: str, start_time: str = "", end_time: str = "", count: int = -1):
        del start_time, end_time
        records = self._parquet_payload_records("trading_calendar", [market])
        if records.empty:
            dates = self.silver.trading_dates(market)
            if count and count > 0:
                return dates[-count:]
            return dates
        dates = list(records.iloc[-1]["payload"].get("dates", []))
        if count and count > 0:
            return dates[-count:]
        return dates

    def _synthetic_instrument_detail(self, stock_code: str) -> dict:
        records = self._parquet_payload_records("instrument_detail_raw")
        if records.empty:
            return {}
        payload = dict(records.iloc[0]["payload"])
        instrument_id, exchange = _split_stock_code(stock_code)
        payload["ExchangeID"] = exchange
        payload["InstrumentID"] = instrument_id
        payload["InstrumentName"] = "special-A"
        return payload

    def download_history_data(self, stock_code: str, period: str, start_time: str = "", end_time: str = "", incrementally=None):
        del incrementally
        if self.silver.has_period(period):
            self.download_history_data2([stock_code], period, start_time=start_time, end_time=end_time)
        return None

    def download_history_data2(self, stock_list: list[str], period: str, start_time: str = "", end_time: str = "", callback=None, incrementally=None):
        del incrementally
        stock_list = list(stock_list or [])
        result = {}
        if self.silver.has_period(period):
            for symbol in stock_list:
                records = self.silver.payload_records(period, [symbol])
                records = _filter_records_time(records, start_time, end_time)
                result[symbol] = _history_summary(records)
        elif self._has_parquet_dataset(PERIOD_DATASET.get(period, period)):
            records = self._parquet_payload_records(PERIOD_DATASET.get(period, period), stock_list or None)
            for symbol in stock_list:
                symbol_records = records[records["symbol"] == symbol] if not records.empty else records
                symbol_records = _filter_records_time(symbol_records, start_time, end_time)
                result[symbol] = _history_summary(symbol_records)
        else:
            result = {symbol: {"count": 0, "start_time": None, "end_time": None} for symbol in stock_list}
        if callback is not None:
            callback(result)
        return result

    def subscribe_quote(self, stock_code: str, period: str = "1d", callback=None, **kwargs) -> int:
        del kwargs
        dataset = f"silver:{period}" if self.silver.has_period(period) else PERIOD_DATASET.get(period, period)
        return self._subscribe(dataset=dataset, symbol=stock_code, callback=callback)

    def subscribe_l2thousand(self, stock_code: str, gear_num: int | None = None, callback=None) -> int:
        return self._subscribe(dataset="l2thousand_raw", symbol=stock_code, callback=callback, gear_num=gear_num)

    def unsubscribe_quote(self, seq: int):
        sub = self._subscriptions.pop(seq, None)
        if sub:
            sub.stop_event.set()
        return None

    def _subscribe(self, dataset: str, symbol: str, callback=None, gear_num: int | None = None) -> int:
        seq = next(self._seq)
        sub = Subscription(seq=seq, dataset=dataset, symbol=symbol, callback=callback, gear_num=gear_num)
        sub.thread = threading.Thread(target=self._run_subscription, args=(sub,), daemon=True)
        self._subscriptions[seq] = sub
        sub.thread.start()
        return seq

    def _run_subscription(self, sub: Subscription) -> None:
        if sub.dataset.startswith("silver:"):
            records = self.silver.payload_records(sub.dataset.removeprefix("silver:"), [sub.symbol])
        else:
            records = self._parquet_payload_records(sub.dataset, [sub.symbol])
        if records.empty:
            return
        payloads = records["payload"].tolist()
        times = records["event_time"].tolist()
        idx = 0
        emitted = 0
        while not sub.stop_event.is_set():
            payload = dict(payloads[idx])
            if sub.gear_num is not None:
                payload = _trim_depth(payload, sub.gear_num)
            self.clock.mark_current(sub.dataset, sub.symbol, idx, _safe_int(times[idx]))
            if sub.callback:
                sub.callback({sub.symbol: [payload]})
            emitted += 1
            max_events = self.config.replay_max_events_per_subscription
            if max_events and emitted >= max_events:
                return
            next_idx = (idx + 1) % len(payloads)
            sleep_s = _event_delay(times[idx], times[next_idx], self.config.replay_speed, singleton=len(payloads) == 1)
            sub.stop_event.wait(sleep_s)
            idx = next_idx

    def _has_parquet_dataset(self, dataset: str) -> bool:
        return self.catalog is not None and dataset in self.catalog.datasets and self.store is not None

    def _parquet_payload_records(self, dataset: str, symbols: list[str] | None = None) -> pd.DataFrame:
        if not self._has_parquet_dataset(dataset):
            return pd.DataFrame(columns=["symbol", "event_time", "recorded_at", "payload"])
        try:
            return self.store.payload_records(dataset, symbols)
        except FileNotFoundError:
            return pd.DataFrame(columns=["symbol", "event_time", "recorded_at", "payload"])


def _payloads_to_dataframe(payloads: list[dict], period: str) -> pd.DataFrame:
    df = pd.DataFrame(payloads)
    if df.empty:
        return _empty_dataframe(period)
    if "index" in df.columns:
        df = df.set_index("index", drop=True)
    elif "time" in df.columns:
        df.index = df["time"].map(_time_index)
    df.index.name = None
    df = _apply_known_dtypes(df, period)
    return df


def _select_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")
    return out.loc[:, columns]


def _empty_dataframe(period: str) -> pd.DataFrame:
    dtypes = PERIOD_DTYPES.get(period)
    if not dtypes:
        df = pd.DataFrame(columns=PERIOD_COLUMNS.get(period, []))
    else:
        df = pd.DataFrame({name: pd.Series(dtype=dtype) for name, dtype in dtypes.items()})
    df.index = pd.Index([], dtype="object")
    df.index.name = None
    return df


def _apply_known_dtypes(df: pd.DataFrame, period: str) -> pd.DataFrame:
    for col, dtype in PERIOD_DTYPES.get(period, {}).items():
        if col in df.columns and dtype != "object":
            try:
                df[col] = df[col].astype(dtype)
            except (TypeError, ValueError):
                pass
    return df


def _filter_time(df: pd.DataFrame, start_time: str, end_time: str) -> pd.DataFrame:
    if df.empty or "time" not in df.columns:
        return df
    start_ms = _parse_time_bound(start_time, is_end=False)
    end_ms = _parse_time_bound(end_time, is_end=True)
    out = df
    if start_ms is not None:
        out = out[out["time"] >= start_ms]
    if end_ms is not None:
        out = out[out["time"] <= end_ms]
    return out


def _filter_records_time(records: pd.DataFrame, start_time: str, end_time: str) -> pd.DataFrame:
    if records.empty or "event_time" not in records.columns:
        return records
    start_ms = _parse_time_bound(start_time, is_end=False)
    end_ms = _parse_time_bound(end_time, is_end=True)
    out = records
    if start_ms is not None:
        out = out[out["event_time"] >= start_ms]
    if end_ms is not None:
        out = out[out["event_time"] <= end_ms]
    return out.reset_index(drop=True)


def _history_summary(records: pd.DataFrame) -> dict:
    if records.empty or "event_time" not in records.columns:
        return {"count": 0, "start_time": None, "end_time": None}
    times = records["event_time"].dropna().astype("int64")
    if times.empty:
        return {"count": len(records), "start_time": None, "end_time": None}
    return {
        "count": len(records),
        "start_time": datetime.fromtimestamp(int(times.min()) / 1000),
        "end_time": datetime.fromtimestamp(int(times.max()) / 1000),
    }


def _select_payload_fields(payload: dict, fields: list[str]) -> dict:
    return {field: payload.get(field) for field in fields}


def _parse_time_bound(value: str, is_end: bool) -> int | None:
    if not value:
        return None
    text = str(value)
    try:
        if len(text) == 8:
            suffix = "235959" if is_end else "000000"
            dt = datetime.strptime(text + suffix, "%Y%m%d%H%M%S")
        elif len(text) == 14:
            dt = datetime.strptime(text, "%Y%m%d%H%M%S")
        else:
            return int(float(text))
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def _parse_yyyymmdd(value: str):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None


def _time_index(ms: int) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y%m%d%H%M%S")
    except Exception:
        return str(ms)


def _dataframe_to_records_array(df: pd.DataFrame):
    if df.empty:
        return np.array([], dtype=[])
    records = [tuple(row[col] for col in df.columns) for _, row in df.iterrows()]
    dtype = [(str(col), object if df[col].dtype == "object" else df[col].dtype) for col in df.columns]
    return np.array(records, dtype=dtype)


def _trim_depth(payload: dict, gear_num: int) -> dict:
    out = dict(payload)
    for key in ("askPrice", "askVolume", "bidPrice", "bidVolume", "askVol", "bidVol"):
        if isinstance(out.get(key), list):
            out[key] = out[key][:gear_num]
    return out


def _event_delay(current_ms, next_ms, speed: float, singleton: bool = False) -> float:
    speed = speed if speed and speed > 0 else 1.0
    if singleton:
        return max(0.05, min(1.0 / speed, 1.0))
    if not current_ms or not next_ms or next_ms <= current_ms:
        return 0.01
    return max(0.001, min((next_ms - current_ms) / 1000 / speed, 1.0))


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_stock_code(stock_code: str) -> tuple[str, str]:
    if "." in stock_code:
        instrument_id, exchange = stock_code.split(".", 1)
        return instrument_id, exchange
    return stock_code, ""


def _synthetic_full_tick(stock_code: str) -> dict:
    instrument_id, exchange = _split_stock_code(stock_code)
    del instrument_id, exchange
    return {
        "time": 0,
        "timetag": "",
        "lastPrice": 0,
        "open": 0,
        "high": 0,
        "low": 0,
        "lastClose": 0,
        "amount": 0,
        "volume": 0,
        "pvolume": 0,
        "tickvol": 0,
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
