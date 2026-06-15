# Strategy Internship Project

项目名称：

```text
IPO / New Listing Daily Strategy Research
```

目标是让策略实习生从 HTTP mock API 下载日线数据开始，独立完成一个可复现的研究闭环：

1. 下载 2026 IPO universe 的日线行情。
2. 校验 coverage、缺失值、重复 key、停牌/无成交。
3. 复现一个日线 baseline 策略。
4. 加入手续费、滑点、最小费用。
5. 完成回测、trade log、metrics 和结果分析。
6. 自主调研 IPO / 暗盘公开信息，作为改进特征或分层分析。
7. 输出研究报告。

我们只提供日线行情和成本模型；不提供 IPO 发行价、超购倍数、保荐人、行业、暗盘涨跌幅等资料。候选人需要自行调研这些公开数据，并记录来源。

## Research Question

港股新股上市初期可能存在动量、反转和流动性冲击。候选人需要研究：

```text
上市后首个交易日的日线表现，能否预测后续数日收益？
加入交易成本后是否仍有可交易性？
候选人自行调研的 IPO / 暗盘信息能否改善过滤效果？
```

## Provided API

策略项目使用 `mock-research-api`，不是前端实时 `mock-feed`，也不是后端 `mock-xtquant`。

默认地址：

```text
http://127.0.0.1:9041
```

接口：

```text
GET /health
GET /api/metadata
GET /api/cost-model
GET /api/symbols/ipo-universe?start=2026-01-01&end=2026-06-15
GET /api/daily?symbol=02723.HK&start=2026-01-01&end=2026-06-15
```

### IPO Universe

字段：

```text
symbol
name
coverage_start
coverage_end
daily_rows
```

`coverage_start` 是我们提供的日线数据覆盖起点，不等同于官方上市日期。候选人如果需要官方 listing date，应自行调研。

### Daily Bars

字段：

```text
symbol
trade_date
open
high
low
close
volume
turnover
previous_close
suspend_flag
```

日期统一为：

```text
YYYYMMDD
```

### Cost Model

字段：

```json
{
  "currency": "HKD",
  "buy_cost_bps": 12.0,
  "sell_cost_bps": 22.0,
  "slippage_bps": 10.0,
  "min_fee": 5.0
}
```

候选人需要在报告里说明买入成本、卖出成本、滑点、最小费用，以及费用按成交额还是订单计。

## Candidate External Data

候选人应自行调研 IPO / 暗盘公开数据。仓库只提供空模板：

```text
strategy-project/data/external/ipo_info_template.csv
strategy-project/data/external/grey_market_template.csv
```

建议 `ipo_info` 字段：

```text
symbol
listing_date
ipo_price
offer_price_low
offer_price_high
sponsor
industry
public_subscription_multiple
one_lot_success_rate
source_url
source_note
collected_at
```

建议 `grey_market` 字段：

```text
symbol
grey_market_date
grey_close
grey_change_pct
premium_to_ipo_price
source_url
source_note
collected_at
```

要求：

- 必须记录来源 URL 或来源说明。
- 缺失值不能随意填 0。
- 报告要说明覆盖率和数据可靠性。

## Baseline Strategy

Baseline:

```text
First-Trading-Day Daily Momentum
```

规则：

1. 每个 symbol 使用 API 返回的第一条 daily bar 作为 day 1。
2. 计算 `first_day_return = day_1.close / day_1.open - 1`。
3. 如果 `first_day_return > threshold`，例如 5%，生成做多信号。
4. 入场价使用 day 2 open。
5. 持有 K 个交易日，例如 3 或 5 日。
6. 可加入止损和止盈。
7. 所有交易必须扣除手续费、滑点、最小费用。
8. 每只股票最多一笔 baseline trade。

候选人也可以增加一个 reversal baseline，但必须保留 momentum baseline 作为对照。

禁止：

- 用 day 2 之后的数据决定是否入场。
- 用完整未来价格路径筛选信号。
- 忽略停牌、无 open、无成交、缺失 daily bar。
- 只报 gross return。

## Required Improvement

候选人需要在 baseline 之外实现一个改进版本。方向可以任选一个：

1. Volume / Turnover Confirmation

首日成交额或成交量高于样本分位数才入场。

2. Gap Filter

day 2 open 相对 day 1 close gap 过大则不追。

3. IPO Feature Filter

使用自行调研的发行价、超购倍数、中签率、保荐人、行业等特征过滤。

4. Grey Market Filter

使用自行调研的暗盘涨跌幅或暗盘溢价过滤。

5. Risk Management

动态止损、最大持仓天数、成本约束或仓位调整。

要求：

- 必须说明假设。
- 必须和 baseline 做对照。
- 不鼓励只堆参数或过拟合。

## Required Outputs

下载后应生成：

```text
data/raw/ipo_universe.parquet
data/raw/daily_bars.parquet
data/raw/cost_model.json
data/raw/coverage_summary.json
```

特征：

```text
data/processed/features.parquet
```

报告输出：

```text
reports/trades.csv
reports/metrics.json
reports/research_report.md
```

Trade log 字段：

```text
symbol
coverage_start
entry_date
entry_price
exit_date
exit_price
shares
gross_pnl
fees
slippage
net_pnl
return
exit_reason
holding_days
strategy_version
```

Metrics：

```text
trade_count
win_rate
average_return
average_win
average_loss
profit_factor
total_return
max_drawdown
turnover
average_holding_days
```

## Expected Workflow

启动 API：

```bash
make serve-research
```

策略项目：

```bash
cd strategy-project
python src/download_data.py --base-url http://127.0.0.1:9041 --start 2026-01-01
python src/build_features.py
python src/backtest.py
```

## Evaluation Rubric

总分 100。

### Data Work - 30

- 能从 API 下载并缓存数据：8
- coverage summary 清楚：6
- 处理缺失、停牌、无成交、重复 key：6
- IPO / 暗盘调研来源记录：6
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

## Red Flags

- 使用未来数据。
- 忽略交易成本。
- 外部 IPO / 暗盘数据没有来源。
- 缺失值随意填 0。
- 只调参数不解释假设。
- 没有 trade log。
- 只报收益，不报回撤、交易次数和成本敏感性。
