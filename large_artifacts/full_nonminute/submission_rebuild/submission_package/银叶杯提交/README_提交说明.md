# 银叶杯因子比赛提交包

本目录为可直接审核的最终提交包。研究严格使用赛题允许的分钟 OHLC、成交量、成交额、成交笔数，以及允许使用的基础日收盘价。

## 官方要求对应关系

| 官方要求 | 提交文件 |
|---|---|
| Python 因子函数，输出标准化因子值 | `code/factor_submission.py` |
| 输出因子值 | `factor_values/standardized_factor_values_2020_2023.npz` |
| 回测报告与因子逻辑文档 | `paper/银叶杯因子研究报告.pdf` |
| 因子相关性低于 50% | `results/final_factor_value_correlation.csv` |

逐条官方口径映射见 `官方赛题要求核对表.md`。

## 因子值格式

- `dates`：970 个交易日，2020-01-02 至 2023-12-29
- `stock_codes`：5515 个股票代码
- `factor_01` 至 `factor_10`：十个 `970 x 5515` 的标准化 `float32` 矩阵
- 无效股票池位置或无法计算的位置：`NaN`

## 快速读取

```python
import numpy as np

data = np.load("factor_values/standardized_factor_values_2020_2023.npz")
dates = data["dates"]
stock_codes = data["stock_codes"]
factor_01 = data["factor_01"]
```

## 复核顺序

1. 阅读 `十因子速览.md` 和 `paper/银叶杯因子研究报告.pdf`。
2. 查看 `results/final_factor_metrics_zh.csv` 与 `results/final_factor_value_correlation.csv`。
3. 查看 `results/final_factor_dictionary.md`，逐项阅读叶子权重、原始字段和子因子含义。
4. 查看 `code/factor_submission.py` 中的 `FINAL_SPECS` 和 `compute_final_factors()`。
5. 运行 `python code/submission_smoke_test.py`，无需原始数据即可验证接口。
6. 查看 `results/submission_code_realdata_validation.json`，核对独立代码与冻结矩阵的真实分钟复算结果。
7. 运行 `python verify_exported_package.py`，复核解压后的提交包。
8. 如需追溯研究过程，查看 `experiments/` 下的对照实验 CSV 和 `research_scripts/` 下的研究脚本。

`MANIFEST_SHA256.txt` 保存包内逐文件校验值，独立验证器会自动核对。

最终十因子均为原子信号或一次显式线性组合，不存在递归套娃、缓存 UUID 或外部 Alpha。
