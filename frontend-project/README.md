# Frontend Project: Market Terminal Lite

目标：基于 `mock-feed` 实现一个轻量行情终端页面。

默认数据源：

```text
ws://127.0.0.1:9021/ws
```

## Required Features

- 5 支股票 watchlist。
- 支持搜索/切换 symbol。
- 展示分钟 K 线和成交量。
- 展示大额交易表。
- 展示买卖 broker queue。
- broker queue 支持 `10 / 100 / 1000` 档切换。
- 档位序号必须保留原始 `position/gear`，不能重新归一化。
- 10/100/1000 只过滤原始档位范围，不改变每档内聚合逻辑。
- 桌面和手机都至少能看买卖各 10 档。
- 页面显示数据时间和 `Live/Warm/Closed` 状态 chip。
- WebSocket 断线后自动重连，不能重复刷屏。

## Important Edge Cases

- broker queue 是完整快照覆盖，不是增量累加。
- 某些档位可能稀疏，例如 `1, 3, 5, 11`。
- 大额交易不能混入非当前 effective day 的旧数据。
- UI 展开状态建议按 `symbol + side + price` 或 `symbol + side + position` 保存。

## Run

需要 Node.js `>=20.19.0`。

先在仓库根目录启动浏览器 mock feed：

```bash
make serve
```

再启动前端：

```bash
npm install
npm run dev
```

`mock-feed` 会保证 `minute_bars` 和 `alerts` 只包含当前 effective day。若 broker queue 使用旧日期样本作为 fallback，payload 会带 `broker_queue.fallback/historical/sourceDate`。

## Submit

PR 里说明：

- 组件结构；
- WebSocket 状态处理；
- broker queue 档位过滤逻辑；
- 移动端如何保证不溢出；
- 你写了哪些测试。
