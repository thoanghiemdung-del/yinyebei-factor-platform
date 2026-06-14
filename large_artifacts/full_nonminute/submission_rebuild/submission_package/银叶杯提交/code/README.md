# 因子计算代码说明

入口文件：`factor_submission.py`

主要接口：

- `compute_daily_leaves(day)`：由一个交易日的分钟矩阵计算叶子因子。
- `compute_leaf_matrices(minute_days, daily_close)`：计算历史叶子矩阵和 20 日滚动信号。
- `compute_final_factors(minute_days, daily_close, universe_mask)`：输出 `factor_01` 至 `factor_10`。
- `save_factor_values(output, dates, stock_codes, factors)`：保存标准化矩阵。

输入分钟字段必须包含：`OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`, `AMOUNT`, `NUMBER`。
`universe_mask` 应事先剔除 ST、*ST 和上市不足 120 日股票。
`minute_days` 按迭代器流式消费，不会一次性把全部分钟日文件载入内存。

无需原始数据的接口烟测：

```bash
python submission_smoke_test.py
```
