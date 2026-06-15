# Backend Project: Market State Engine Lite

目标：用 `mock-xtquant` 实现一个轻量实时行情状态引擎，并通过 WebSocket 输出 `snapshot/delta`。

候选人应直接使用：

```python
from xtquant import xtdata
```

不要接入真实 xtquant、Redis、Kafka 或生产服务。

`mock-xtquant` 模拟的是 SDK/raw sample 语义，不保证已经是 terminal API 业务视图。后端实现需要负责：

- effective day 对齐；
- old-date alerts 清理；
- broker queue snapshot 覆盖；
- 输出符合 `docs/api-contract.md` 的 snapshot/delta。

## Required Features

- 订阅 5 支股票：
  - `1m`
  - `hktransaction`
  - `hkbrokerqueueex`
- 维护每个 symbol 的内存 snapshot。
- `1m` 更新分钟 K 和 quote。
- `hktransaction` 生成大额交易 alert。
- `hkbrokerqueueex` 作为完整 broker queue 快照覆盖。
- WebSocket 支持：
  - `snapshot_request`
  - `visible_set`
  - `snapshot`
  - `delta`
- 动态 onboard 一个新 symbol。
- effective day 对齐：
  - 旧日期 historical alerts 不能混入今天 live 视图；
  - live tick 切到今天时，需要清掉 fallback alerts。

## Suggested Architecture

```text
adapters/xtquant_adapter.py  # 只负责从 xtdata 取数和订阅
state/engine.py              # 每个 symbol 的状态机
gateway/ws.py                # WebSocket 协议
models.py                    # payload 类型
```

## Run

```bash
PYTHONPATH=../mock-xtquant/src:src \
XTMOCK_SILVER_ROOT=../sample-data \
python -m market_state_engine.app
```

启动后默认监听：

```text
ws://127.0.0.1:9031/ws
```

## Big Trade Definition

默认阈值：

```text
tick.volume >= max(1, previous_or_current_daily_volume * 0.0005)
```

如果没有 daily baseline，可使用保守 fallback，但必须在代码和返回 payload 中说明。

## Submit

PR 里说明：

- 状态机设计；
- snapshot/delta 协议；
- effective day 怎么处理；
- broker queue 为什么是覆盖而不是累加；
- 测试覆盖了哪些坑。
