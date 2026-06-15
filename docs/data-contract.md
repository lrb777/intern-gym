# Data Contract

样本数据位于：

```text
sample-data/
```

默认包含 5 支股票：

```text
02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK
```

## Tables

| table | format | 用途 |
| --- | --- | --- |
| `silver_minute_bars_v1/part-00000.parquet` | parquet | 分钟 K 线 |
| `silver_trade_ticks_v1/part-00000.parquet` | parquet | 逐笔成交，用于大额交易 |
| `silver_broker_queue_v1/part-00000.parquet` | parquet | broker queue 历史快照/回放 |
| `silver_ccass_holdings_v1/part-00000.parquet` | parquet | CCASS 持仓，可作为 bonus |
| `silver_daily_bars_v1.csv` | csv | daily baseline |
| `silver_instruments_v1.csv` | csv | 股票中文名 |
| `silver_broker_mapping_v1.csv` | csv | broker code 到券商名映射 |
| `manifest.json` | json | 数据包说明 |

## Regenerate

```bash
make build-data SILVER_ROOT=/path/to/full/silver-root
```

或：

```bash
python scripts/build_sample_data.py \
  --source-silver-root /path/to/full/silver-root \
  --output-root sample-data \
  --symbols 02723.HK,02675.HK,00100.HK,02513.HK,06082.HK
```

## Important Semantics

- 样本数据可能包含不同 source date，这是故意保留的测试点。
- `mock-xtquant` 暴露接近原始样本的数据，可能返回不同 source date；后端候选人需要自己产出符合 API contract 的业务视图。
- `mock-feed` 作为前端数据源会输出 contract-compliant snapshot/delta：分钟线和 alerts 不跨 effective day，旧 broker queue fallback 会显式标记。
- `mock-research-api` 使用 `research-data`，只提供策略方向所需的日线数据和成本模型，不提供 IPO 基本面或暗盘数据。
- 前端和后端都不能把旧日期 alerts 混进当前 effective day。
- broker queue 的价格档可能稀疏；不要假设档位连续。
- broker queue 是快照，不是增量。

## Research Data

策略方向数据位于：

```text
research-data/
```

表：

| table | format | 用途 |
| --- | --- | --- |
| `ipo_universe.parquet` | parquet | IPO universe coverage，非官方 IPO 基本资料 |
| `daily_bars.parquet` | parquet | 日线 OHLCV |
| `cost_model.json` | json | 回测成本模型 |
| `metadata.json` | json | 数据包覆盖信息 |

当前内置数据包包含 65 个 2026 港股 IPO 普通股标的、3,673 行日线，覆盖到 `20260615`。候选人仍应在策略项目中重新生成 `coverage_summary.json`，并报告实际下载结果。

`ipo_universe` 字段：

```text
symbol
name
coverage_start
coverage_end
daily_rows
```

`daily_bars` 字段：

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
