# Frontend Task

实现 `frontend-project` 中的 Market Terminal Lite。

前端默认消费 `mock-feed`：

```text
ws://127.0.0.1:9021/ws
```

`mock-feed` 保证分钟线和 alerts 不跨 effective day；旧 broker queue fallback 会通过 `broker_queue.sourceDate/fallback/historical` 标记。

## Must Have

- watchlist + symbol 切换。
- 分钟 K 线和成交量。
- 大额交易表。
- 买卖 broker queue。
- `10 / 100 / 1000` 档切换。
- 桌面和手机可用。
- 数据时间展示。
- WebSocket 重连。

## Broker Queue Acceptance

如果原始档位是：

```text
1, 3, 5, 11, 13, 15
```

那么：

- 10 档显示 `1, 3, 5`；
- 100 档显示 `1, 3, 5, 11, 13, 15`；
- 档位数字仍显示原始数字；
- 每档内 volume 计算不随 10/100/1000 切换改变。

## Suggested Tests

- 10 档过滤不重排档位。
- 档内 broker volume 合计正确。
- 展开/收起不改变左右两列宽度。
- 旧日期 alert 不显示。
- WebSocket reconnect 后不会重复插入同一 alert。
