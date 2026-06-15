# Grading Rubric

## Frontend / Backend

总分 100。

### Correctness - 40

- 数据能跑通，核心功能完整：10
- broker queue 档位语义正确：10
- effective day / alerts 不串日：10
- WebSocket snapshot/delta/reconnect 正确：10

### Engineering Quality - 25

- 组件/模块边界清晰：8
- 状态管理可解释：7
- 测试覆盖关键坑：7
- 错误处理和空状态合理：3

### UI/UX 或 API Design - 20

前端：

- 桌面/移动端布局稳定：8
- K 线、成交量、队列、alerts 信息层级清楚：8
- 数据时间和状态展示清楚：4

后端：

- 状态机设计简洁：8
- payload contract 稳定：8
- freshness/source evidence 清楚：4

### Communication - 15

- PR 描述清楚：5
- 能解释 tradeoff：5
- 能说明已知限制和下一步：5

### Red Flags

- 把 broker queue 当增量累加。
- 10/100/1000 档重新编号。
- 混入旧日期大额交易。
- 页面必须手动刷新才更新。
- 大量临时 patch，没有测试说明。

## Strategy

总分 100。

### Data Work - 30

- 能从 `mock-research-api` 下载并缓存数据：8
- `coverage_summary.json` 清楚：6
- 处理缺失、停牌、无成交、重复 key：6
- IPO / 暗盘外部调研来源记录：6
- 外部数据覆盖率和可靠性说明：4

### Backtest Correctness - 30

- 无未来函数：8
- 成本和滑点正确：6
- entry/exit 执行价格合理：5
- trade log 完整：4
- 可复现：4
- 停牌/缺失处理合理：3

### Strategy Reasoning - 20

- baseline 规则清楚：5
- 改进假设明确：5
- 对照实验合理：5
- 能解释收益和亏损来源：5

### Engineering Quality - 10

- 代码结构清楚：3
- 参数配置合理：2
- 测试覆盖关键函数：3
- README 可运行：2

### Communication - 10

- 报告清楚：4
- 图表/表格有解释：3
- 能说明限制和下一步：3

### Red Flags

- 使用未来数据。
- 忽略交易成本。
- 外部 IPO / 暗盘数据没有来源。
- 缺失值随意填 0。
- 只调参数不解释假设。
- 没有 trade log。
- 只报收益，不报回撤、交易次数和成本敏感性。
