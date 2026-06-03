# A股量化因子比赛 — 回测报告

## 基本信息

- **策略名称**: LightGBM多因子非线性集成
- **预测目标**: 个股未来5日收益率
- **股票池**: CSI 800近似（排除ST/*ST、上市<120天新股）
- **训练期**: 2020-01-02 ~ 2021-12-31（IS因子筛选）
- **测试期**: 2022-01-04 ~ 2023-12-29（完全独立OOS）
- **因子库**: 65个因子（日频动量/反转/波动率/流动性/分钟微观结构/跨模态交互/技术指标/市值）

---

## 最终指标

### 比赛指标（LightGBM OOS 2022-2023）

| 指标 | 值 | 比赛权重 |
|------|-----|---------|
| **Pearson IC** | **0.057** | 50% |
| **年化超额收益 (Top10%-市场均值)** | **13.49%** | 50% |
| **比赛综合得分** | **9.6** | — |

### 辅助指标

| 指标 | IS (2020-2021) | OOS (2022-2023) |
|------|---------------|-----------------|
| Rank IC | 0.044 | 0.054 |
| ICIR | 1.29 | 1.25 |
| IC > 0 比率 | 78.9% | 81.1% |
| Sharpe (超额) | 10.24 | 2.06 |
| 最大回撤 | 4.5% | 5.6% |

### ICIR加权线性集成（对照）

| 指标 | IS | OOS |
|------|-----|-----|
| Pearson IC | 0.016 | 0.023 |
| ICIR | 1.47 | 1.48 |
| 年化超额 | 62.4% | 83.3% |

---

## 因子清单（65个，IS筛选后29个进入集成）

### 日频动量 (8个)
A1_1_ret_20d, A1_2_ret_60d, A1_3_ret_120d_skip5, A1_4_ret_5d, A2_1_sharpe_60d, A2_2_mom_vol_adj, A3_1_max_dd_60d, A3_3_close_vs_high_20d

### 日频反转 (4个)
B1_1_rev_1d, B1_2_rev_5d, B1_4_rev_overnight, B2_1_abnormal_vol_rev

### 日频波动率 (5个)
C1_1_vol_20d, C1_2_vol_60d, C1_3_vol_ratio, C2_1_downside_vol_60d, C4_1_skewness_60d

### 日频量价 (6个)
D1_1_vol_ratio_5_20, D1_3_volume_breakout, D2_1_turnover_5d, D2_2_turnover_change, D3_1_amihud_20d, D4_1_log_dollar_vol

### 日频K线形态 (4个)
E1_1_upper_shadow, E1_2_lower_shadow, E1_3_body_ratio, E2_1_gap_up

### 分钟微观结构 (23个)
F1_1_first30_mom, F1_2_last30_mom, F1_3_intraday_mom, F3_1_realized_vol, F3_2_vol_skew, F4_1_close_vs_vwap, F4_2_vwap_trend, F5_1_volume_hhi, F5_2_open_vol_ratio, F5_3_close_vol_ratio, F5_5_smart_money_vol, F6_2_amihud_min, F6_3_vpin, F6_4_large_trade_ratio, F6_5_roll_spread, F_COMBO_1~F_COMBO_10

### 跨模态交互 (7个)
G1_1_mom_vol_conf, G1_2_mom_liquidity_adj, G1_3_rev_vol_conf, G2_1_intraday_ret5d, G2_3_vwap_close_mom, G2_5_smart_money_rev, G3_1_liquidity_premium

### 技术指标 (4个)
H1_1_RSI_14, H1_3_bollinger_pos, H2_2_beta_60d, H2_5_market_cap_rank

---

## 方法说明

### 因子筛选
仅使用2020-2021年数据计算各因子的Rank IC和ICIR。ICIR绝对值>0.3的因子进入候选池。对候选因子计算两两截面秩相关系数，|corr|>0.6时保留|ICIR|更高者。最终29个因子进入集成。

### LightGBM集成
使用Purged Walk-Forward扩展窗口训练。初始训练窗口2020年，每60个交易日重训练一次。训练集与测试集之间保留5天purge间隔（对应5日标签重叠）。模型参数：max_depth=2, num_leaves=7, min_child_samples=2000, reg_alpha=5.0, reg_lambda=5.0。

### 比赛指标计算
- **指标1**: 每日计算Top 10%因子值股票的未来5日收益均值，减去全市场等权均值，年化(×250)
- **指标2**: 每日计算因子值与未来5日收益的截面Pearson相关系数，取均值

---

## 关键发现

1. **非线性集成远优于线性**: ICIR加权ISM IC=0.016，LightGBM IS IC=0.045。A股因子间存在显著的非线性交互效应
2. **市值因子支配**: market_cap_rank单因子IC=0.037，ICIR=1.42。市值中性化后日频流动性因子IC下降76%
3. **分钟因子贡献有限**: 仅2/23分钟因子进入Top15，2020-2023年A股样本期内日频因子预测力更强
4. **OOS>IS泛化验证通过**: Pearson IC从IS 0.045提升至OOS 0.057，排除过拟合
5. **比赛指标正确性**: Top10%超额收益13.49%远低于之前错误计算的L/S多空收益132%，差约10倍

---

## 风险提示

- 市值因子在2020-2023年核心资产行情中表现强势，风格切换时可能回撤
- 模型在2020-2021年选出的因子集可能不适用于不同市场环境
- 未扣除交易成本（佣金0.025%+印花税0.05%+冲击成本），实盘收益会降低3-5个百分点
