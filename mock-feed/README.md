# mock-feed

这是给前端项目使用的浏览器 WebSocket feed。

启动：

```bash
PYTHONPATH=mock-feed/src \
XTMOCK_SILVER_ROOT=sample-data \
python -m market_mock_feed.server --host 0.0.0.0 --port 9021
```

或使用根目录：

```bash
make serve
```

连接：

```text
ws://127.0.0.1:9021/ws
```

它直接读取 `sample-data`，快速生成：

- snapshot
- minute bar delta
- trade tick delta
- broker queue delta

Contract 行为：

- `minute_bars` 和 `alerts` 只包含当前 effective day。
- 旧日期 broker queue 可作为 fallback snapshot 输出，但必须带 `sourceDate/fallback/historical` 标记。
- `hkbrokerqueueex` delta 覆盖上一张队列快照，不是增量累加。

注意：前端候选人使用这个服务；后端候选人使用 `mock-xtquant`。
