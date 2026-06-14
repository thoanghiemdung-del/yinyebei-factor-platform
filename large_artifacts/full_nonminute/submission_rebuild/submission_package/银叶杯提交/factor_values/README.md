# 标准化因子值文件
文件：`standardized_factor_values_2020_2023.npz`

## 格式

- `dates`：长度 970，日期范围 `2020-01-02` 至 `2023-12-29`
- `stock_codes`：长度 5515
- `factor_01` 至 `factor_10`：每个矩阵形状 `970 x 5515`，行是日期，列是股票
- 数值：横截面 1%/99% 缩尾后 z-score 标准化的 `float32`
- 非股票池或无法计算的位置：`NaN`

## 读取示例

```python
import numpy as np

data = np.load("standardized_factor_values_2020_2023.npz")
dates = data["dates"]
stock_codes = data["stock_codes"]
factor_01 = data["factor_01"]
```

因子键、名称、公式和指标见上级目录 `final_factor_metrics.csv`。
