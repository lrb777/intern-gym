from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .responses import error, ok
from .store import ResearchStore


def first(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    return values[0] if values else default


def make_handler(store: ResearchStore):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if parsed.path == "/health":
                self._json(200, {"ok": True, "source": "mock-research-api"})
                return
            if parsed.path == "/api/metadata":
                self._json(200, ok(store.metadata, as_of=store.as_of()))
                return
            if parsed.path == "/api/cost-model":
                self._json(200, ok(store.cost_model, as_of=store.as_of()))
                return
            if parsed.path == "/api/symbols/ipo-universe":
                data = store.new_listings(start=first(params, "start"), end=first(params, "end"))
                self._json(200, ok(data, as_of=store.as_of()))
                return
            if parsed.path == "/api/daily":
                symbol = first(params, "symbol")
                if not symbol:
                    self._json(400, error("invalid_request", "symbol is required"))
                    return
                data = store.daily_bars(symbol, start=first(params, "start"), end=first(params, "end"))
                if data is None:
                    self._json(404, error("invalid_symbol", f"unknown symbol: {symbol}"))
                    return
                self._json(200, ok(data, as_of=store.as_of(), extra_meta={"symbol": symbol.upper()}))
                return

            self._json(404, error("not_found", "endpoint not found"))

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def run_server(host: str, port: int, data_root: Path) -> None:
    store = ResearchStore(data_root)
    server = ThreadingHTTPServer((host, port), make_handler(store))
    print(f"mock research API listening on http://{host}:{port}", flush=True)
    server.serve_forever()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start daily-only strategy research mock API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9041)
    parser.add_argument("--data-root", type=Path, default=Path(os.getenv("RESEARCH_DATA_ROOT", "research-data")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_server(args.host, args.port, args.data_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
