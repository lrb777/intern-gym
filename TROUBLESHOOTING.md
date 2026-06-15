# Troubleshooting

## Recommended Versions

- Python: 3.12 or 3.13
- Node.js: 20.19.0 or newer for `frontend-project`
- Docker Compose: v2

## Mock Data Smoke

```bash
python -m venv .venv
source .venv/bin/activate
make install
make smoke
```

Expected signs of success:

```text
1m {'02723.HK': 2, '02675.HK': 2}
hktransaction {'02723.HK': 2, '02675.HK': 2}
hkbrokerqueueex {'02723.HK': 2, '02675.HK': 2}
callback_count ...
```

`make smoke` intentionally prints callback progress while replaying a short subscription.

## Browser Mock Feed

```bash
make serve
```

Verify manually:

```bash
python - <<'PY'
import asyncio, json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:9021/ws") as ws:
        print(await ws.recv())
        print(await ws.recv())
        await ws.send(json.dumps({
            "schema_version": 1,
            "protocol": "terminal-message-v3",
            "command": "snapshot_request",
            "request_id": "manual-1",
            "symbols": ["02723.HK"],
        }))
        print(await ws.recv())
        print(await ws.recv())

asyncio.run(main())
PY
```

## Frontend

```bash
cd frontend-project
npm install
npm run dev
```

If Vite reports that Node is too old, upgrade to Node.js `>=20.19.0`.

## Backend Skeleton

```bash
cd backend-project
PYTHONPATH=../mock-xtquant/src:src \
XTMOCK_SILVER_ROOT=../sample-data \
python -m market_state_engine.app
```

The skeleton is intentionally incomplete. It proves import and WebSocket plumbing; candidates must implement the state engine.

## Strategy Scaffold

```bash
make serve-research
```

In another shell:

```bash
cd strategy-project
python src/download_data.py --base-url http://127.0.0.1:9041 --start 2026-01-01
python src/build_features.py
python src/backtest.py
```

Outputs are written to `data/processed/` and `reports/`.

Local fallback without the HTTP API:

```bash
cd strategy-project
python src/download_data.py --source-root ../research-data
```
