# Market Terminal Internship Lab

这是一个独立的招聘/实习生练习仓库骨架，用来拆分三个项目：

- `frontend-project`: Market Terminal Lite 前端。
- `backend-project`: Market State Engine Lite 后端。
- `strategy-project`: IPO / New Listing Daily Strategy Research 策略研究。

仓库内置一个 import-compatible `mock xtquant`、浏览器实时 `mock-feed`、策略日线 `mock-research-api` 和裁剪样本数据。目标不是复刻完整生产系统，而是让候选人在可控范围内处理我们真实遇到过的问题：实时数据刷新、券商队列语义、effective day 对齐、旧数据恢复、移动端展示，以及日线策略研究流程。

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
make install
make smoke
make serve
```

`make smoke` 会回放一小段 mock subscription，并打印 callback 计数；看到 `callback_count` 即表示 mock xtquant 数据路径可用。

启动后：

```text
ws://127.0.0.1:9021/ws
```

Docker 方式：

```bash
docker compose up --build
```

`sample-data` 已随仓库提供。维护者需要重新裁剪数据包时再运行：

```bash
make build-data SILVER_ROOT=/path/to/full/silver-root
```

## What Is Included

```text
mock-xtquant/       xtquant.xtdata 兼容 mock SDK
mock-feed/          浏览器可连接的 WebSocket mock feed
mock-research-api/  策略实习项目使用的日线历史 HTTP API
research-data/      策略 HTTP API 使用的日线-only 数据包
sample-data/        5 支股票的裁剪样本数据
frontend-project/   前端任务说明和骨架
backend-project/    后端任务说明和骨架
strategy-project/   策略研究项目可运行 scaffold
docs/               总览、任务说明、接口契约、数据说明、评分标准
scripts/            维护者样本数据裁剪脚本
examples/           mock xtdata smoke 示例
```

前后端默认样本股票：

```text
02723.HK, 02675.HK, 00100.HK, 02513.HK, 06082.HK
```

## Candidate Workflow

1. Fork 或新建分支。
2. 按 `frontend-project/README.md`、`backend-project/README.md` 或 `strategy-project/README.md` 完成一个项目。
3. 提交 PR。
4. PR 需要说明：
   - 实现了什么；
   - 如何运行；
   - 如何验证；
   - 已知限制。

## Boundaries

不要在练习中接入真实 xtquant、Redis、Kafka 或生产 token。前后端练习的数据源固定为 `mock-xtquant + sample-data`；策略练习的数据源固定为 `mock-research-api + research-data`。

分层责任：

- `mock-xtquant` 模拟 SDK，暴露接近原始样本的数据语义，候选后端需要自己处理 effective day、状态机和 contract 输出。
- `mock-feed` 是给前端候选人使用的浏览器 WebSocket，输出 contract-compliant snapshot/delta；如果 broker queue 只能使用旧日期 fallback，会在 payload 中显式标记。
- `mock-research-api` 是给策略候选人使用的日线历史 HTTP API，只提供 IPO universe coverage、daily bars 和 cost model；IPO / 暗盘资料由候选人自行调研。
- `backend-project` 是候选后端实现入口，不应依赖真实生产服务。

文档索引见 [docs/README.md](docs/README.md)，评分标准见 [docs/grading-rubric.md](docs/grading-rubric.md)。

常见问题见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。
