from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import websockets
from xtquant import xtdata


PROTOCOL = "terminal-message-v3"
SCHEMA_VERSION = 1
DEFAULT_SYMBOLS = ("02723.HK", "02675.HK", "00100.HK", "02513.HK", "06082.HK")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def frame(message_type: str, *, symbol: str = "", seq: int = 0, request_id: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL,
        "type": message_type,
        "source": "candidate-backend",
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


@dataclass
class SymbolSnapshot:
    symbol: str
    seq: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


class MarketStateEngine:
    """Starter skeleton.

    Candidates should implement the actual state transitions here.
    Keep xtquant adapter code separate from state mutation logic.
    """

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self.snapshots = {symbol: SymbolSnapshot(symbol=symbol, payload=self.empty_snapshot(symbol)) for symbol in symbols}

    def empty_snapshot(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "snapshot": {"symbol": symbol, "name": symbol, "price": 0.0, "updatedAt": "", "tradeDate": ""},
            "minute_bars": [],
            "alerts": [],
            "broker_queue": {"ask": [], "bid": []},
            "freshness": {"runtime_state": "COLD", "source_dates": {}},
        }

    def hydrate(self) -> None:
        for symbol in self.symbols:
            minute_data = xtdata.get_market_data_ex([], [symbol], period="1m", count=120).get(symbol)
            queue_data = xtdata.get_market_data_ex([], [symbol], period="hkbrokerqueueex", count=1).get(symbol)
            # TODO: convert these DataFrames into the snapshot payload.
            # This placeholder proves the mock xtquant import path works.
            self.snapshots[symbol].payload["freshness"]["runtime_state"] = "WARM"
            self.snapshots[symbol].payload["freshness"]["mock_rows"] = {
                "minute_bars": 0 if minute_data is None else len(minute_data),
                "broker_queue": 0 if queue_data is None else len(queue_data),
            }

    def snapshot_frame(self, symbol: str) -> dict[str, Any]:
        snapshot = self.snapshots[symbol]
        return frame("snapshot", symbol=symbol, seq=max(1, snapshot.seq), payload=snapshot.payload)


async def handle_client(websocket: Any, engine: MarketStateEngine) -> None:
    await websocket.send(json.dumps(frame("hello", payload={"symbols": engine.symbols})))
    async for raw in websocket:
        command = json.loads(raw)
        symbols = [str(item).upper() for item in command.get("symbols", [])] or engine.symbols
        await websocket.send(
            json.dumps(frame("ack", request_id=command.get("request_id", ""), payload={"command": command.get("command"), "accepted": True}))
        )
        if command.get("command") in {"snapshot_request", "visible_set"}:
            for symbol in symbols:
                if symbol in engine.snapshots:
                    await websocket.send(json.dumps(engine.snapshot_frame(symbol)))


async def main_async() -> None:
    symbols = [item.strip().upper() for item in os.getenv("MARKET_SYMBOLS", ",".join(DEFAULT_SYMBOLS)).split(",") if item.strip()]
    engine = MarketStateEngine(symbols)
    engine.hydrate()
    async with websockets.serve(lambda websocket: handle_client(websocket, engine), "0.0.0.0", 9031):
        print("candidate backend listening on ws://127.0.0.1:9031/ws", flush=True)
        await asyncio.Future()


def main() -> int:
    asyncio.run(main_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
