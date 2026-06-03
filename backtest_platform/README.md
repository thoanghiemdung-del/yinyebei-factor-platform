# 量化回测平台使用说明

启动 `python app.py`，浏览器访问 `http://localhost:5000`。

默认账号: `admin` / `quant2026`，访客: `guest` / `backtest`。

表达式语法（WQ 风格）：

基础字段: `close open high low volume amount preclose`

时序算子:
- `ts_delta(x, d)` — x[t] - x[t-d]
- `ts_mean(x, d)` — d日滚动均值
- `ts_std(x, d)` — d日滚动标准差
- `ts_rank(x, d)` — d日滚动排名百分位
- `ts_max(x, d)` / `ts_min(x, d)` / `ts_sum(x, d)`
- `ts_corr(x, y, d)` — x和y的d日滚动相关系数

截面算子:
- `rank(x)` — 截面排名百分位 [0,1]
- `zscore(x)` — 截面z-score标准化
- `demean(x)` — 截面去均值
- `signed_power(x, e)` — sign(x)*|x|^e

组合:
- `group_neutralize(x, market_cap)` — 市值分组中性化
- `trade_when(cond, alpha, fallback)` — 条件因子
- 算术: `+ - * / ^`

10个示例:
1. `rank(ts_delta(close, 20))` — 20日动量
2. `-rank(ts_sum(close/open-1, 5))` — 5日反转
3. `rank(ts_mean(volume, 5) / ts_mean(volume, 20))` — 量比
4. `-signed_power(close/open-1, 2) * rank(volume)` — 异常量反转
5. `rank(ts_std(close/open-1, 20))` — 波动率
6. `ts_delta(close, 20) / (ts_std(close/open-1, 60) + 0.001)` — 夏普比
7. `close / open - 1` — 日内收益
8. `rank(ts_corr(close/open-1, volume, 20))` — 量价相关性
9. `group_neutralize(rank(ts_delta(close, 5)), market_cap)` — 市值中性动量
10. `trade_when(volume > ts_mean(volume, 20), rank(ts_delta(close, 10)), -1)` — 放量时做动量

指标含义:
- Sharpe: Top10%多头超额年化收益/年化波动
- 年化超额收益: Top 10%组合年化收益 - 全市场等权平均年化收益（比赛指标1）
- Pearson IC: 因子值与未来收益的截面相关系数（比赛指标2）
- ICIR: Rank IC均值/标准差
- 最大回撤: 累积收益曲线上最大峰谷跌幅

常见错误:
- 除零: 分母加 eps (如 `/ (ts_std(x, 20) + 0.001)`)
- 括号: 表达式必须合法嵌套
- 字段不存在: 确认使用基础字段名
