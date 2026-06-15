from __future__ import annotations

import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from market_research_api.server import make_handler
from market_research_api.store import ResearchStore


def data_root() -> Path:
    return Path(os.getenv("RESEARCH_DATA_ROOT", "research-data"))


def get_json(url: str) -> tuple[int, dict]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_research_api_contract():
    store = ResearchStore(data_root())
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, health = get_json(f"{base}/health")
        assert status == 200
        assert health["ok"] is True

        status, metadata = get_json(f"{base}/api/metadata")
        assert status == 200
        assert metadata["data"]["symbol_count"] > 0

        status, cost = get_json(f"{base}/api/cost-model")
        assert status == 200
        assert {"buy_cost_bps", "sell_cost_bps", "slippage_bps", "min_fee"} <= set(cost["data"])

        status, universe = get_json(f"{base}/api/symbols/ipo-universe?start=2026-01-01")
        assert status == 200
        assert universe["meta"]["row_count"] > 0
        symbol = universe["data"][0]["symbol"]

        status, daily = get_json(f"{base}/api/daily?symbol={symbol}&start=2026-01-01")
        assert status == 200
        assert daily["meta"]["symbol"] == symbol
        assert daily["meta"]["row_count"] > 0
        assert {"symbol", "trade_date", "open", "high", "low", "close", "previous_close", "suspend_flag"} <= set(daily["data"][0])

        status, missing = get_json(f"{base}/api/daily?symbol=NOPE.HK")
        assert status == 404
        assert missing["error"]["code"] == "invalid_symbol"
    finally:
        server.shutdown()
        thread.join(timeout=5)
