# Backend Task

实现 `backend-project` 中的 Market State Engine Lite。

后端默认使用 `mock-xtquant`，它模拟 SDK/raw sample 层，不替候选人完成 terminal API 的 effective day 过滤和状态机语义。

## Must Have

- 从 `mock-xtquant` 订阅 `1m/hktransaction/hkbrokerqueueex`。
- 每个 symbol 独立维护 snapshot。
- 支持 `snapshot_request` 和 `visible_set`。
- 生成 `snapshot` 和 `delta`。
- 动态 onboard 新 symbol。
- 大额交易按 daily baseline ratio 生成。
- effective day 对齐。

## State Rules

- `1m` 更新分钟 K。
- `hktransaction` 更新 quote，并可能生成 alert。
- `hkbrokerqueueex` 覆盖 broker queue。
- live tick 切到新的 trade day 时，清理旧日期 minute bars 和 alerts。
- 不要因为前端切 visible symbols 就重新 hydrate 已有 live symbol。

## Suggested Tests

- same-day tick 触发 alert。
- previous-day historical alert 不进入 today live snapshot。
- broker queue callback 覆盖 fallback。
- dynamic onboard 只 hydrate 新 symbol。
- duplicate alert 不重复出现。
