# API Contract

本 lab 使用简化版 `terminal-message-v3` WebSocket 协议。

默认 mock feed：

```text
ws://127.0.0.1:9021/ws
```

## Client Commands

所有命令：

```json
{
  "schema_version": 1,
  "protocol": "terminal-message-v3",
  "command": "snapshot_request",
  "request_id": "req-1",
  "symbols": ["02723.HK"]
}
```

支持：

| command | 说明 |
| --- | --- |
| `snapshot_request` | 请求一个或多个 symbol 的完整 snapshot |
| `visible_set` | 声明当前屏幕关注的 symbols |
| `watchlist_set` | 声明 watchlist symbols |
| `health_request` | 请求健康状态 |

## Server Frames

### hello

```json
{
  "schema_version": 1,
  "protocol": "terminal-message-v3",
  "type": "hello",
  "payload": {
    "symbols": ["02723.HK", "02675.HK"]
  }
}
```

### snapshot

```json
{
  "schema_version": 1,
  "protocol": "terminal-message-v3",
  "type": "snapshot",
  "symbol": "02723.HK",
  "seq": 1,
  "payload": {
    "symbol": "02723.HK",
    "snapshot": {},
    "minute_bars": [],
    "alerts": [],
    "broker_queue": {"ask": [], "bid": []},
    "freshness": {}
  }
}
```

### delta

```json
{
  "schema_version": 1,
  "protocol": "terminal-message-v3",
  "type": "delta",
  "symbol": "02723.HK",
  "seq": 2,
  "payload": {
    "delta_type": "broker_queue"
  }
}
```

## Snapshot Payload Rules

- `snapshot.tradeDate` 是当前业务视图的 effective day。
- `minute_bars` 必须只包含当前 effective day。
- `alerts` 必须只包含当前 effective day。
- `broker_queue.ask/bid` 是最新完整快照。
- 如果 `broker_queue` 来源日期不同于 effective day，服务端必须显式标记 `fallback: true` 和 `historical: true`，并填写 `sourceDate`。
- `freshness.source_dates` 应记录 `minute_bars`、`alerts`、`broker_queue` 的数据来源时间。

## Broker Queue Rules

- 每个 row 是一个价格档。
- `position` / `gear` 是原始档位，不能重新编号。
- `10 / 100 / 1000` 档切换只按原始档位过滤。
- 每个价格档的 `volume` 是该档内所有 broker volume 的合计。
- `hkbrokerqueueex` 到达时应覆盖上一张队列快照。

带 fallback 标记的 broker queue 示例：

```json
{
  "broker_queue": {
    "ask": [],
    "bid": [],
    "sourceDate": "20260603",
    "historical": true,
    "fallback": true
  }
}
```

## Alert Rules

大额交易阈值：

```text
tick.volume >= max(1, daily_baseline_volume * 0.0005)
```

每条 alert 应包含：

```json
{
  "id": "big-02723.HK-1",
  "timestamp": "2026-06-12T10:31:00.000+08:00",
  "tradeDate": "20260612",
  "sourceDate": "20260612",
  "historical": false,
  "price": 350.0,
  "volume": 10000,
  "thresholdVolume": 5000
}
```
