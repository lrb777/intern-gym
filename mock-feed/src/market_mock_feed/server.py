from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import websockets


PROTOCOL = "terminal-message-v3"
SCHEMA_VERSION = 1
DEFAULT_SYMBOLS = ("02723.HK", "02675.HK", "00100.HK", "02513.HK", "06082.HK")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_symbols() -> list[str]:
    raw = os.getenv("MARKET_SYMBOLS", ",".join(DEFAULT_SYMBOLS))
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def iso_from_any(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    text = str(value)
    if text and text != "nan":
        if text.isdigit():
            return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")
        return text
    return ""


def trade_date_from_timestamp(value: Any) -> str:
    text = iso_from_any(value)
    return text[:10].replace("-", "") if len(text) >= 10 else ""


def compact_name(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("证券有限公司", "證券有限公司", "证券国际(香港)有限公司", "證券國際(香港)有限公司", "有限公司", "证券", "證券"):
        text = text.replace(suffix, "")
    return text[:8] or "未披露"


def queue_row_key(row: dict[str, Any]) -> tuple[str, str]:
    side = str(row.get("side") or "").lower()
    order_id = str(row.get("order_id") or "").strip()
    if order_id:
        return (side, f"order:{order_id}")
    return (
        side,
        "level:"
        + "|".join(
            [
                str(int(float(row.get("position") or row.get("gear") or 0))),
                str(row.get("broker_code") or "0"),
                str(float(row.get("price") or 0.0)),
            ]
        ),
    )


@dataclass
class SymbolState:
    symbol: str
    name: str
    baseline_volume: int
    effective_day: str
    seq: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


class SampleDataStore:
    def __init__(self, root: Path):
        self.root = root
        self.minute = pd.read_parquet(root / "silver_minute_bars_v1")
        self.ticks = pd.read_parquet(root / "silver_trade_ticks_v1")
        self.queue = pd.read_parquet(root / "silver_broker_queue_v1")
        self.instruments = pd.read_csv(root / "silver_instruments_v1.csv")
        self.daily = pd.read_csv(root / "silver_daily_bars_v1.csv")
        self.broker_mapping = pd.read_csv(root / "silver_broker_mapping_v1.csv")
        self.names = {
            str(row["symbol"]).upper(): str(row["name"])
            for row in self.instruments.to_dict("records")
            if str(row.get("symbol") or "").strip()
        }
        self.baseline_volume = latest_daily_volume(self.daily)
        self.brokers = {
            str(row["broker_code"]).strip(): compact_name(row.get("participant_name") or row.get("broker_name"))
            for row in self.broker_mapping.to_dict("records")
            if str(row.get("broker_code") or "").strip()
        }

    def minute_rows(self, symbol: str, limit: int = 240) -> list[dict[str, Any]]:
        frame = self.minute[self.minute["symbol"].astype(str).str.upper() == symbol].sort_values("bar_ts")
        return frame.tail(limit).to_dict("records")

    def minute_rows_for_day(self, symbol: str, trade_date: str, limit: int = 420) -> list[dict[str, Any]]:
        frame = self.minute[self.minute["symbol"].astype(str).str.upper() == symbol].copy()
        frame["_trade_date"] = frame["bar_ts"].map(trade_date_from_timestamp)
        frame = frame[frame["_trade_date"] == trade_date].sort_values("bar_ts")
        return frame.tail(limit).drop(columns=["_trade_date"], errors="ignore").to_dict("records")

    def tick_rows(self, symbol: str, limit: int = 500, trade_date: str = "") -> list[dict[str, Any]]:
        frame = self.ticks[self.ticks["symbol"].astype(str).str.upper() == symbol].sort_values("tick_ts")
        if trade_date:
            frame = frame.copy()
            frame["_trade_date"] = frame["tick_ts"].map(trade_date_from_timestamp)
            frame = frame[frame["_trade_date"] == trade_date]
            frame = frame.drop(columns=["_trade_date"], errors="ignore")
        return frame.head(limit).to_dict("records")

    def latest_queue_rows(self, symbol: str) -> list[dict[str, Any]]:
        book_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for row in self.queue_rows(symbol):
            book_rows[queue_row_key(row)] = row
        return list(book_rows.values())

    def queue_frames(self, symbol: str, limit: int = 120) -> list[dict[str, Any]]:
        book_rows: dict[tuple[str, str], dict[str, Any]] = {}
        snapshots: list[dict[str, Any]] = []
        for row in self.queue_rows(symbol):
            book_rows[queue_row_key(row)] = row
            snapshots.append({"queue_ts": row.get("queue_ts"), "rows": list(book_rows.values())})
            if len(snapshots) >= limit:
                break
        return snapshots

    def queue_rows(self, symbol: str) -> list[dict[str, Any]]:
        frame = self.queue[self.queue["symbol"].astype(str).str.upper() == symbol].sort_values("queue_ts")
        return frame.to_dict("records")

    def effective_day(self, symbol: str) -> str:
        configured = os.getenv("MARKET_EFFECTIVE_DAY", "").strip()
        if configured:
            return configured.replace("-", "")
        frame = self.minute[self.minute["symbol"].astype(str).str.upper() == symbol].copy()
        if frame.empty:
            return ""
        frame["_trade_date"] = frame["bar_ts"].map(trade_date_from_timestamp)
        dates = sorted(date for date in frame["_trade_date"].dropna().unique() if date)
        return str(dates[-1]) if dates else ""


def latest_daily_volume(frame: pd.DataFrame) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in frame.sort_values("trade_date").to_dict("records"):
        symbol = str(row.get("symbol") or "").upper()
        try:
            volume = int(float(row.get("volume") or 0))
        except ValueError:
            volume = 0
        if symbol and volume > 0:
            result[symbol] = volume
    return result


class MarketFeed:
    def __init__(self, symbols: list[str], store: SampleDataStore):
        self.symbols = symbols
        self.store = store
        self.clients: set[Any] = set()
        self.replay_tasks: list[asyncio.Task[Any]] = []
        self.states = {
            symbol: SymbolState(
                symbol=symbol,
                name=store.names.get(symbol, symbol),
                baseline_volume=store.baseline_volume.get(symbol, 0),
                effective_day=store.effective_day(symbol),
            )
            for symbol in symbols
        }
        for symbol in symbols:
            self.hydrate(symbol)

    def hydrate(self, symbol: str) -> None:
        state = self.states[symbol]
        state.payload = empty_snapshot(symbol, state.name, state.effective_day)
        for row in self.store.minute_rows_for_day(symbol, state.effective_day):
            bar = minute_bar(row)
            upsert_bar(state.payload["minute_bars"], bar)
            update_quote_from_bar(state, bar)
        state.payload["alerts"] = filter_current_day(state.payload["alerts"], state.effective_day)
        state.payload["minute_bars"] = filter_current_day(state.payload["minute_bars"], state.effective_day)
        state.payload["broker_queue"] = broker_queue_from_rows(
            self.store.latest_queue_rows(symbol),
            self.store.brokers,
            effective_day=state.effective_day,
        )

    def start_replay(self) -> None:
        for symbol in self.symbols:
            self.replay_tasks.append(asyncio.create_task(self.replay_minutes(symbol)))
            self.replay_tasks.append(asyncio.create_task(self.replay_ticks(symbol)))
            self.replay_tasks.append(asyncio.create_task(self.replay_queues(symbol)))

    def stop_replay(self) -> None:
        for task in self.replay_tasks:
            task.cancel()

    async def replay_minutes(self, symbol: str) -> None:
        state = self.states[symbol]
        for row in self.store.minute_rows_for_day(symbol, state.effective_day, limit=500):
            await asyncio.sleep(replay_interval())
            await self.apply("1m", symbol, row)

    async def replay_ticks(self, symbol: str) -> None:
        state = self.states[symbol]
        max_events = int(os.getenv("XTMOCK_REPLAY_MAX_EVENTS_PER_SUBSCRIPTION", "500"))
        for row in self.store.tick_rows(symbol, limit=max_events, trade_date=state.effective_day):
            await asyncio.sleep(replay_interval())
            await self.apply("hktransaction", symbol, row)

    async def replay_queues(self, symbol: str) -> None:
        for snapshot in self.store.queue_frames(symbol, limit=120):
            await asyncio.sleep(replay_interval() * 4)
            await self.apply("hkbrokerqueueex", symbol, snapshot)

    async def apply(self, period: str, symbol: str, payload: dict[str, Any]) -> None:
        state = self.states[symbol]
        if period == "1m":
            bar = minute_bar(payload)
            if trade_date_from_timestamp(bar["timestamp"]) != state.effective_day:
                return
            upsert_bar(state.payload["minute_bars"], bar)
            update_quote_from_bar(state, bar)
            delta = {"delta_type": "minute_bar", "minute_bar": bar}
        elif period == "hktransaction":
            tick = trade_tick(payload)
            if tick["tradeDate"] != state.effective_day:
                return
            update_quote_from_tick(state, tick)
            alert = big_trade_alert(state, tick)
            if alert is not None:
                merge_alert(state.payload["alerts"], alert)
                touch_freshness(state, alert["timestamp"], "alerts")
            delta = {"delta_type": "trade_tick", "tick": tick, "alert": alert}
        elif period == "hkbrokerqueueex":
            queue = broker_queue_from_rows(list(payload.get("rows") or []), self.store.brokers, effective_day=state.effective_day)
            state.payload["broker_queue"] = queue
            touch_freshness(state, queue_timestamp(payload), "broker_queue")
            delta = {"delta_type": "broker_queue", "broker_queue": queue}
        else:
            return
        state.seq += 1
        await self.broadcast(frame("delta", symbol=symbol, seq=state.seq, payload=delta))

    def snapshot_frame(self, symbol: str) -> dict[str, Any] | None:
        state = self.states.get(symbol)
        if state is None:
            return None
        return frame("snapshot", symbol=symbol, seq=max(1, state.seq), payload=state.payload)

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self.clients:
            return
        encoded = json.dumps(message, ensure_ascii=False)
        dead = []
        for client in list(self.clients):
            try:
                await client.send(encoded)
            except Exception:
                dead.append(client)
        for client in dead:
            self.clients.discard(client)


async def handle_client(websocket: Any, feed: MarketFeed) -> None:
    feed.clients.add(websocket)
    try:
        await websocket.send(json.dumps(frame("hello", payload={"symbols": feed.symbols}), ensure_ascii=False))
        await websocket.send(json.dumps(frame("heartbeat", payload={"ready": True}), ensure_ascii=False))
        async for raw in websocket:
            command = json.loads(raw)
            request_id = str(command.get("request_id") or "")
            name = str(command.get("command") or "")
            symbols = [str(item).upper() for item in command.get("symbols", []) if str(item).strip()] or feed.symbols
            await websocket.send(json.dumps(frame("ack", request_id=request_id, payload={"command": name, "accepted": True}), ensure_ascii=False))
            if name in {"snapshot_request", "visible_set", "watchlist_set"}:
                for symbol in symbols:
                    snapshot = feed.snapshot_frame(symbol)
                    if snapshot is not None:
                        await websocket.send(json.dumps(snapshot, ensure_ascii=False))
            elif name == "health_request":
                await websocket.send(json.dumps(frame("heartbeat", request_id=request_id, payload={"ready": True}), ensure_ascii=False))
    finally:
        feed.clients.discard(websocket)


def frame(message_type: str, *, symbol: str = "", seq: int = 0, request_id: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "type": message_type,
        "source": "internship-mock-feed",
        "server_ts": now_iso(),
        "payload": payload or {},
    }
    if symbol:
        result["symbol"] = symbol
    if seq:
        result["seq"] = seq
    if request_id:
        result["request_id"] = request_id
    return result


def empty_snapshot(symbol: str, name: str, effective_day: str = "") -> dict[str, Any]:
    return {
        "symbol": symbol,
        "snapshot": {"symbol": symbol, "name": name, "currency": "HKD", "price": 0.0, "updatedAt": "", "tradeDate": effective_day},
        "minute_bars": [],
        "alerts": [],
        "broker_queue": {"ask": [], "bid": [], "sourceDate": "", "historical": False, "fallback": False},
        "freshness": {"runtime_state": "WARM", "effective_day": effective_day, "source_dates": {}},
    }


def minute_bar(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_from_any(row.get("bar_ts") or row.get("timestamp") or row.get("time"))
    close = float(row.get("close") or row.get("price") or 0.0)
    return {
        "timestamp": timestamp,
        "price": close,
        "open": float(row.get("open") or close),
        "high": float(row.get("high") or close),
        "low": float(row.get("low") or close),
        "close": close,
        "volume": int(float(row.get("volume") or 0)),
        "turnover": float(row.get("turnover") or row.get("amount") or 0.0),
    }


def trade_tick(row: dict[str, Any]) -> dict[str, Any]:
    timestamp = iso_from_any(row.get("tick_ts") or row.get("timestamp") or row.get("time"))
    return {
        "id": str(row.get("trade_id") or row.get("tradeID") or row.get("seq") or row.get("row_hash") or timestamp),
        "timestamp": timestamp,
        "tradeDate": trade_date_from_timestamp(timestamp),
        "price": float(row.get("price") or 0.0),
        "volume": int(float(row.get("volume") or row.get("qty") or 0)),
        "turnover": float(row.get("turnover") or row.get("amount") or 0.0),
        "side": str(row.get("side") or "neutral").lower(),
        "brokerCode": str(row.get("active_broker_code") or row.get("broker_code") or row.get("brokerNo") or ""),
    }


def broker_queue_from_rows(rows: list[dict[str, Any]], brokers: dict[str, str], *, effective_day: str = "") -> dict[str, Any]:
    source_date = queue_source_date(rows)
    result: dict[str, Any] = {
        "ask": [],
        "bid": [],
        "sourceDate": source_date,
        "historical": bool(source_date and effective_day and source_date != effective_day),
        "fallback": bool(source_date and effective_day and source_date != effective_day),
    }
    if not rows:
        return result
    frame = pd.DataFrame(rows)
    for (side, price), group in frame.groupby(["side", "price"], sort=True):
        side_text = str(side).lower()
        position = int(float(group["position"].dropna().astype(float).min())) if "position" in group.columns and not group.empty else len(result.get(side_text, [])) + 1
        cells = []
        for row in group.to_dict("records"):
            code = str(row.get("broker_code") or "0")
            volume = int(float(row.get("volume") or 0))
            cells.append({"brokerCode": code, "displayName": brokers.get(code, code if code != "0" else "未披露"), "volume": volume})
        entry = {
            "id": f"{side_text}-{int(position)}-{float(price)}",
            "side": side_text,
            "position": int(position),
            "gear": int(position),
            "price": float(price),
            "volume": sum(item["volume"] for item in cells),
            "brokerCount": len(cells),
            "brokers": cells,
        }
        if side_text in result:
            result[side_text].append(entry)
    for side in ("ask", "bid"):
        result[side].sort(key=lambda item: int(item["position"]))
    return result


def queue_source_date(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        trade_date = trade_date_from_timestamp(row.get("queue_ts"))
        if trade_date:
            return trade_date
    return ""


def filter_current_day(rows: list[dict[str, Any]], effective_day: str) -> list[dict[str, Any]]:
    if not effective_day:
        return rows
    filtered = []
    for row in rows:
        timestamp = row.get("timestamp") or row.get("updatedAt") or row.get("bar_ts") or row.get("tick_ts")
        if trade_date_from_timestamp(timestamp) == effective_day or row.get("tradeDate") == effective_day:
            filtered.append(row)
    return filtered


def queue_timestamp(payload: dict[str, Any]) -> str:
    rows = list(payload.get("rows") or [])
    if not rows:
        return now_iso()
    return iso_from_any(rows[0].get("queue_ts"))


def update_quote_from_bar(state: SymbolState, bar: dict[str, Any]) -> None:
    quote = state.payload["snapshot"]
    quote.update(
        {
            "price": bar["close"],
            "open": bar["open"],
            "high": max(float(quote.get("high") or 0.0), bar["high"]),
            "low": bar["low"] if not quote.get("low") else min(float(quote["low"]), bar["low"]),
            "volume": sum(int(item.get("volume") or 0) for item in state.payload["minute_bars"]),
            "turnover": sum(float(item.get("turnover") or 0.0) for item in state.payload["minute_bars"]),
            "updatedAt": bar["timestamp"],
            "tradeDate": trade_date_from_timestamp(bar["timestamp"]),
        }
    )
    touch_freshness(state, bar["timestamp"], "minute_bars")


def update_quote_from_tick(state: SymbolState, tick: dict[str, Any]) -> None:
    quote = state.payload["snapshot"]
    quote["price"] = tick["price"]
    quote["updatedAt"] = tick["timestamp"]
    quote["tradeDate"] = tick["tradeDate"]


def upsert_bar(bars: list[dict[str, Any]], bar: dict[str, Any]) -> None:
    for index, item in enumerate(bars):
        if item.get("timestamp") == bar["timestamp"]:
            bars[index] = bar
            return
    bars.append(bar)
    bars.sort(key=lambda item: str(item.get("timestamp") or ""))
    del bars[:-420]


def big_trade_alert(state: SymbolState, tick: dict[str, Any]) -> dict[str, Any] | None:
    threshold = max(1, int(state.baseline_volume * 0.0005)) if state.baseline_volume > 0 else 1000
    if tick["volume"] < threshold:
        return None
    return {
        "id": f"big-{state.symbol}-{tick['id']}",
        "timestamp": tick["timestamp"],
        "tradeDate": tick["tradeDate"],
        "sourceDate": tick["tradeDate"],
        "historical": False,
        "source": "mock_hktransaction",
        "price": tick["price"],
        "volume": tick["volume"],
        "turnover": tick["turnover"],
        "side": tick["side"],
        "brokerCode": tick["brokerCode"],
        "thresholdVolume": threshold,
        "thresholdRatio": 0.0005,
        "baselineVolume": state.baseline_volume,
    }


def merge_alert(alerts: list[dict[str, Any]], alert: dict[str, Any]) -> None:
    if any(item.get("id") == alert.get("id") for item in alerts):
        return
    alerts.insert(0, alert)
    del alerts[100:]


def touch_freshness(state: SymbolState, timestamp: Any, key: str) -> None:
    state.payload["freshness"]["runtime_state"] = "LIVE"
    state.payload["freshness"].setdefault("source_dates", {})[key] = iso_from_any(timestamp) or str(timestamp or now_iso())


def replay_interval() -> float:
    return max(0.02, float(os.getenv("MOCK_FEED_INTERVAL_SECONDS", "0.15")))


async def run_server(host: str, port: int) -> None:
    store = SampleDataStore(Path(os.getenv("XTMOCK_SILVER_ROOT", "sample-data")))
    feed = MarketFeed(parse_symbols(), store)
    async with websockets.serve(lambda websocket: handle_client(websocket, feed), host, port):
        print(f"mock feed listening on ws://{host}:{port}/ws", flush=True)
        feed.start_replay()
        await asyncio.Future()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the internship browser-facing mock feed.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9021)
    args = parser.parse_args()
    asyncio.run(run_server(args.host, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
