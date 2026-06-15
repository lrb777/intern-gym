# Frontend / Backend Internship Projects

本文档用于发布两个工程实习项目：

- Frontend Project: Market Terminal Lite
- Backend Project: Market State Engine Lite

两个项目共用本仓库的 `sample-data` 和 mock 数据源，但考察重点不同。前端项目重点考察实时 UI、复杂表格和移动端体验；后端项目重点考察实时状态引擎、数据语义和 WebSocket contract。

## Common Setup

候选人 fork 或 clone 仓库后，先跑通 mock 数据：

```bash
python -m venv .venv
source .venv/bin/activate
make install
make smoke
```

前端项目需要 Node.js `>=20.19.0`。

前端 mock feed：

```bash
make serve
```

默认 WebSocket：

```text
ws://127.0.0.1:9021/ws
```

默认股票池：

```text
02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK
```

数据包：

```text
sample-data/
  silver_minute_bars_v1/part-00000.parquet
  silver_trade_ticks_v1/part-00000.parquet
  silver_broker_queue_v1/part-00000.parquet
  silver_ccass_holdings_v1/part-00000.parquet
  silver_daily_bars_v1.csv
  silver_instruments_v1.csv
  silver_broker_mapping_v1.csv
  manifest.json
```

## Shared Data Semantics

### Minute Bars

`silver_minute_bars_v1` 是分钟 K 线数据。

核心字段：

```text
symbol
trade_date
bar_ts
open
high
low
close
volume
turnover
```

要求：

- K 线展示和状态计算只能使用当前时刻及以前的数据。
- 不允许使用完整日内数据提前构造未来信号。
- 如果 live replay 切换到新的 trade day，需要清理旧日期 bars。

### Trade Ticks

`silver_trade_ticks_v1` 是逐笔成交数据，用于生成大额交易。

核心字段：

```text
symbol
trade_date
tick_ts
price
volume
turnover
side
broker_code
participant_name
trade_id
```

大额交易默认定义：

```text
tick.volume >= max(1, daily_baseline_volume * 0.0005)
```

要求：

- alert 需要去重。
- alert 必须带 `tradeDate/sourceDate/historical/source`。
- 当前 live 视图不能混入其他 effective day 的 historical alerts。

### Broker Queue

`silver_broker_queue_v1` 是 broker queue 事件数据。mock feed 会输出聚合后的 queue snapshot。

业务语义：

- 每个 row 是一个价格档。
- 每个价格档内包含多个 broker cell。
- `position/gear` 是原始档位，不能重新归一化。
- `10 / 100 / 1000` 档切换只过滤原始档位范围。
- `hkbrokerqueueex` 是完整快照覆盖，不是增量累加。
- 如果最新可用 broker queue 日期早于当前 effective day，`mock-feed` 会输出 fallback snapshot，并在 `broker_queue.sourceDate/fallback/historical` 中标记。

示例：

如果原始档位为：

```text
1, 3, 5, 11, 13, 15
```

则：

```text
10档: 1, 3, 5
100档: 1, 3, 5, 11, 13, 15
```

每个档位的总挂单量始终等于该档内所有 broker volume 之和，不应因 10/100/1000 切换而改变。

## WebSocket Contract

客户端命令：

```json
{
  "schema_version": 1,
  "protocol": "terminal-message-v3",
  "command": "snapshot_request",
  "request_id": "req-1",
  "symbols": ["02723.HK"]
}
```

支持命令：

```text
snapshot_request
visible_set
watchlist_set
health_request
```

服务端帧：

```text
hello
heartbeat
ack
snapshot
delta
error
```

Snapshot payload 形态：

```json
{
  "symbol": "02723.HK",
  "snapshot": {
    "symbol": "02723.HK",
    "name": "深演智能",
    "price": 350.0,
    "updatedAt": "2026-06-09T08:10:00.000+00:00",
    "tradeDate": "20260609"
  },
  "minute_bars": [],
  "alerts": [],
  "broker_queue": {
    "ask": [],
    "bid": []
  },
  "freshness": {
    "runtime_state": "LIVE",
    "source_dates": {}
  }
}
```

## Frontend Project: Market Terminal Lite

### Goal

实现一个轻量行情终端页面，连接 `mock-feed`，展示 5 支港股新股/活跃股票的实时 replay 行情。

候选人只需要通过 WebSocket 消费 `snapshot/delta`。

### Required Features

1. Watchlist

- 展示默认 5 支股票。
- 导航显示 `中文名 + 股票代码`。
- 支持搜索或手动输入 symbol。
- 切换 symbol 时页面状态和数据不混乱。

2. K 线和成交量

- 展示分钟 K 线。
- 同屏展示成交量。
- 移动端 K 线和成交量不能重叠。
- 左上角显示中文名，不只显示代码。
- 显示数据时间。

3. 大额交易表

- 展示 `alerts`。
- 按 timestamp 倒序。
- 去重。
- 不展示非当前 effective day 的旧数据。
- live delta 到来后自动追加，不需要手动刷新网页。

4. Broker Queue

- 固定买/卖两列。
- 支持 `10 / 100 / 1000` 档切换。
- 档位显示原始 `position/gear`。
- 每档显示：
  - side
  - position
  - price
  - total volume
  - broker count
  - broker cells
- broker cell 显示短名和数量。
- 有溢出 broker cells 时支持展开/收起。
- 展开状态建议用 `symbol + side + price` 或 `symbol + side + position` 保存。
- 手机端至少能看买卖各 10 档。

5. Realtime State

- WebSocket 断线重连。
- 重连后自动 request snapshot。
- delta 不应重复插入同一 alert。
- 页面显示 `Live / Warm / Closed / Connecting` 状态 chip。

### Suggested Component Structure

```text
src/
  services/
    marketFeed.ts
  stores/
    marketStore.ts
  components/
    Watchlist.vue
    PriceChart.vue
    VolumeChart.vue
    BigTradeTable.vue
    BrokerQueue.vue
    BrokerQueueRow.vue
    BrokerCell.vue
```

### Acceptance Tests

候选人至少应覆盖：

- `10 / 100 / 1000` 档过滤不重排档位。
- 档内 broker volume 合计正确。
- 展开/收起不改变买卖两列宽度。
- 旧日期 alert 不展示。
- WebSocket reconnect 后 snapshot/delta 不重复污染状态。
- 移动端布局不重叠。

### Frontend Deliverables

```text
frontend-project/
  README.md
  src/
  tests/
```

PR 说明需要包含：

- 如何运行；
- 组件结构；
- 状态管理设计；
- broker queue 过滤逻辑；
- 移动端处理；
- 测试说明；
- 已知限制。

## Backend Project: Market State Engine Lite

### Goal

实现一个轻量实时行情状态引擎，直接使用本仓库的 mock xtquant SDK：

```python
from xtquant import xtdata
```

后端项目需要自己维护 per-symbol snapshot，并通过 WebSocket 输出 `snapshot/delta`。不要求 Redis/Kafka，不接真实 xtquant。

### Required Features

1. Adapter

订阅：

```text
1m
hktransaction
hkbrokerqueueex
```

支持：

```python
xtdata.get_market_data_ex(...)
xtdata.subscribe_quote(...)
xtdata.unsubscribe_quote(...)
```

2. State Engine

每个 symbol 独立维护：

```text
snapshot
minute_bars
alerts
broker_queue
freshness
seq
```

要求：

- `1m` 更新分钟 K 和 quote。
- `hktransaction` 更新 quote，并按阈值生成 big trade alert。
- `hkbrokerqueueex` 覆盖 broker queue。
- snapshot/delta 需要有递增 seq。
- duplicate event 不应重复影响状态。

3. Effective Day

必须处理：

- 启动时可能 hydrate fallback 历史数据。
- live tick 到达后，effective day 可能切到今天。
- 切 effective day 时，旧日期 minute bars 和 alerts 必须清掉。
- historical alerts 只有在 `sourceDate == effectiveTradeDate` 时才能进入当前 snapshot。

4. Dynamic Onboarding

支持动态查询一个不在初始 watchlist 的 symbol。

要求：

- 只 hydrate 新 symbol。
- 不能因为前端切 visible symbols 而重新 hydrate 已经 live 的 symbol。
- onboard 后应尽快输出 snapshot。

5. Gateway

WebSocket 支持：

```text
snapshot_request
visible_set
health_request
```

返回：

```text
hello
heartbeat
ack
snapshot
delta
error
```

### Suggested Architecture

```text
backend-project/
  src/market_state_engine/
    adapters/
      xtquant_adapter.py
    state/
      engine.py
      symbol_actor.py
    gateway/
      websocket.py
    models.py
    app.py
  tests/
```

### Acceptance Tests

候选人至少应覆盖：

- same-day tick 触发 big trade alert。
- previous-day historical alert 不进入 today live snapshot。
- live tick 切 effective day 时清理 fallback alerts。
- broker queue callback 覆盖 fallback queue。
- dynamic onboard 只 hydrate 新 symbol。
- duplicate alert 不重复出现。
- visible_set 不会改变 monitored universe。

### Backend Deliverables

```text
backend-project/
  README.md
  src/
  tests/
```

PR 说明需要包含：

- 如何运行；
- 状态机设计；
- snapshot/delta contract；
- effective day 处理；
- broker queue 覆盖语义；
- 测试说明；
- 已知限制。

## Evaluation Rubric

总分 100。

### Correctness - 40

- 核心功能完整：10
- broker queue 语义正确：10
- effective day / alerts 不串日：10
- WebSocket 刷新和重连正确：10

### Engineering Quality - 25

- 模块边界清晰：8
- 状态管理可解释：7
- 测试覆盖关键坑：7
- 错误处理和空状态合理：3

### Product / API Design - 20

前端：

- 桌面/移动端布局稳定：8
- 信息层级清楚：8
- 数据时间和状态展示清楚：4

后端：

- 状态机简洁：8
- payload contract 稳定：8
- freshness/source evidence 清楚：4

### Communication - 15

- PR 描述清楚：5
- 能解释 tradeoff：5
- 能说明已知限制和下一步：5

## Red Flags

- broker queue 当增量累加。
- 10/100/1000 档重新编号。
- 混入旧日期大额交易。
- 页面必须手动刷新才更新。
- 代码只有临时 patch，没有测试。
- 把真实 token、真实生产路径或机器配置提交进 repo。
