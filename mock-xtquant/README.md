# mock-xtquant

这是一个最小可用的 `xtquant.xtdata` import-compatible mock SDK。

使用：

```bash
PYTHONPATH=mock-xtquant/src \
XTMOCK_SILVER_ROOT=sample-data \
python examples/read_xtdata.py
```

后端项目应直接使用：

```python
from xtquant import xtdata
```

支持本 lab 需要的接口：

- `get_market_data_ex(period="1m")`
- `get_market_data_ex(period="hktransaction")`
- `get_market_data_ex(period="hkbrokerqueueex")`
- `subscribe_quote(period="1m")`
- `subscribe_quote(period="hktransaction")`
- `subscribe_quote(period="hkbrokerqueueex")`
- `download_history_data`
- `get_full_tick`

限制：

- 不是完整 xtquant 实现；
- 不连接真实行情；
- 不包含真实 token；
- 只用于练习和测试。
- 输出接近 raw sample/SDK 语义，可能包含不同 source date；后端候选人需要自己产出符合 API contract 的业务 snapshot/delta。
