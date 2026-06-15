import os
import time
from pathlib import Path

from market_mock_feed.server import DEFAULT_SYMBOLS, MarketFeed, SampleDataStore, broker_queue_from_rows
from market_state_engine.app import frame
from xtquant import xtdata


def sample_root() -> Path:
    return Path(os.getenv("XTMOCK_SILVER_ROOT", "sample-data"))


def test_hkbrokerqueueex_count_one_is_fast_for_default_symbols():
    started = time.perf_counter()
    for symbol in DEFAULT_SYMBOLS:
        data = xtdata.get_market_data_ex([], [symbol], period="hkbrokerqueueex", count=1)
        assert symbol in data
        assert len(data[symbol]) == 1
    assert time.perf_counter() - started < 3.0


def test_mock_feed_snapshot_respects_effective_day_contract():
    feed = MarketFeed(list(DEFAULT_SYMBOLS), SampleDataStore(sample_root()))

    for symbol in DEFAULT_SYMBOLS:
        snapshot = feed.snapshot_frame(symbol)
        payload = snapshot["payload"]
        effective_day = payload["snapshot"]["tradeDate"]

        assert effective_day
        assert payload["freshness"]["effective_day"] == effective_day
        assert {bar["timestamp"][:10].replace("-", "") for bar in payload["minute_bars"]} == {effective_day}
        assert {alert["tradeDate"] for alert in payload["alerts"]} <= {effective_day}

        queue = payload["broker_queue"]
        assert set(queue) >= {"ask", "bid", "sourceDate", "historical", "fallback"}
        if queue["sourceDate"] and queue["sourceDate"] != effective_day:
            assert queue["historical"] is True
            assert queue["fallback"] is True


def test_broker_queue_keeps_original_sparse_positions():
    queue = broker_queue_from_rows(
        [
            {"side": "ask", "position": 1, "gear": 1, "price": 10.0, "broker_code": "1", "volume": 100, "queue_ts": "2026-06-01T09:30:00+08:00"},
            {"side": "ask", "position": 3, "gear": 3, "price": 10.2, "broker_code": "2", "volume": 200, "queue_ts": "2026-06-01T09:30:00+08:00"},
            {"side": "ask", "position": 11, "gear": 11, "price": 11.0, "broker_code": "3", "volume": 300, "queue_ts": "2026-06-01T09:30:00+08:00"},
        ],
        {},
        effective_day="20260601",
    )
    assert [level["position"] for level in queue["ask"]] == [1, 3, 11]
    assert [level["gear"] for level in queue["ask"]] == [1, 3, 11]


def test_backend_frame_shape_is_aligned_with_mock_feed_protocol():
    message = frame("hello", payload={"symbols": ["02723.HK"]})
    assert message["schema_version"] == 1
    assert message["protocol"] == "terminal-message-v3"
    assert message["type"] == "hello"
    assert message["source"] == "candidate-backend"
    assert message["server_ts"]
    assert message["payload"]["symbols"] == ["02723.HK"]
