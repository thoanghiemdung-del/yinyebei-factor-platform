# 最终十因子机器可读字典

- 最终因子数：10
- 去重后叶子数：24

## factor_01：大单执行压力

公式：`-0.250000 * z(F6_4_large_trade_ratio) -0.250000 * z(F_COMBO_8_large_trade) -0.250000 * z(N5_log_avg_ticket) +0.250000 * z(N6_large_ticket_amount_ratio)`

经济含义：综合大额成交占比、方向性大单和平均单笔金额，检验机构式大单执行压力。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F6_4_large_trade_ratio` | -0.250000 | `MINUTE_VOLUME` | 大额成交分钟的成交量占比，刻画大额执行集中度。 |
| `F_COMBO_8_large_trade` | -0.250000 | `MINUTE_VOLUME, MINUTE_OPEN, MINUTE_CLOSE` | 大额成交占比与日内方向结合，刻画大单推动。 |
| `N5_log_avg_ticket` | -0.250000 | `MINUTE_AMOUNT, MINUTE_NUMBER` | 全日平均单笔金额的对数，刻画平均订单规模。 |
| `N6_large_ticket_amount_ratio` | 0.250000 | `MINUTE_AMOUNT, MINUTE_NUMBER` | 异常大单时段成交额占比，刻画机构式大单执行。 |

## factor_02：日内反转与成交笔数时序

公式：`-0.166667 * z(F1_1_first30_mom) -0.166667 * z(F1_2_last30_mom) -0.166667 * z(F1_3_intraday_mom) +0.100000 * z(N1_count_weighted_time) -0.100000 * z(N2_open_count_ratio) -0.100000 * z(N3_close_count_ratio) -0.100000 * z(N4_count_hhi) -0.100000 * z(N7_count_price_corr)`

经济含义：将早盘、尾盘和全日日内反转与成交笔数时序结合，检验价格偏离是否得到广泛参与确认。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F1_1_first30_mom` | -0.166667 | `MINUTE_OPEN, MINUTE_CLOSE` | 前30分钟收益，反映隔夜信息进入市场后的早盘价格压力。 |
| `F1_2_last30_mom` | -0.166667 | `MINUTE_OPEN, MINUTE_CLOSE` | 后30分钟收益，反映尾盘调仓和集中执行造成的价格压力。 |
| `F1_3_intraday_mom` | -0.166667 | `MINUTE_OPEN, MINUTE_CLOSE` | 从开盘到收盘的日内收益，刻画当日订单流推动的价格偏离。 |
| `N1_count_weighted_time` | 0.100000 | `MINUTE_NUMBER` | 成交笔数加权平均交易时点，刻画普通交易参与偏早盘还是尾盘。 |
| `N2_open_count_ratio` | -0.100000 | `MINUTE_NUMBER` | 前30分钟成交笔数占比，刻画早盘参与密度。 |
| `N3_close_count_ratio` | -0.100000 | `MINUTE_NUMBER` | 后30分钟成交笔数占比，刻画尾盘参与密度。 |
| `N4_count_hhi` | -0.100000 | `MINUTE_NUMBER` | 分钟成交笔数HHI，刻画交易活跃度在时段上的集中程度。 |
| `N7_count_price_corr` | -0.100000 | `MINUTE_CLOSE, MINUTE_NUMBER` | 分钟收益与成交笔数的日内相关性，刻画参与密度是否与价格变化共振。 |

## factor_03：VWAP执行价格压力

公式：`-0.333333 * z(F4_1_close_vs_vwap) -0.333333 * z(F4_2_vwap_trend) -0.333333 * z(F_COMBO_9_smart_money_vwap)`

经济含义：综合收盘-VWAP偏离、上午-下午VWAP迁移和聪明钱VWAP共振，检验执行价格偏离后的修复。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F4_1_close_vs_vwap` | -0.333333 | `MINUTE_HIGH, MINUTE_LOW, MINUTE_CLOSE, MINUTE_VOLUME` | 收盘价相对全日VWAP偏离，刻画尾盘价格与平均成交成本的距离。 |
| `F4_2_vwap_trend` | -0.333333 | `MINUTE_HIGH, MINUTE_LOW, MINUTE_CLOSE, MINUTE_VOLUME` | 下午VWAP相对上午VWAP变化，刻画日内成本中枢迁移。 |
| `F_COMBO_9_smart_money_vwap` | -0.333333 | `MINUTE_OHLC, MINUTE_VOLUME` | 上涨分钟成交量占比与收盘VWAP偏离相乘，刻画买方订单流与价格偏离共振。 |

## factor_04：成交笔数集中度

公式：`-1.000000 * z(N4_count_hhi)`

经济含义：分钟成交笔数HHI，刻画交易活跃度在时段上的集中程度。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `N4_count_hhi` | -1.000000 | `MINUTE_NUMBER` | 分钟成交笔数HHI，刻画交易活跃度在时段上的集中程度。 |

## factor_05：尾盘压力与成交分布修复

公式：`-0.100000 * z(F1_2_last30_mom) -0.125000 * z(F5_1_volume_hhi) -0.125000 * z(F5_2_open_vol_ratio) -0.225000 * z(F5_3_close_vol_ratio) -0.125000 * z(F_COMBO_7_wat) -0.100000 * z(N3_close_count_ratio) +0.100000 * z(N8_tail_ticket_reversal)`

经济含义：将成交量日内分布、尾盘价格压力、尾盘成交笔数和尾盘单笔规模结合，检验集中调仓后的价格修复。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F1_2_last30_mom` | -0.100000 | `MINUTE_OPEN, MINUTE_CLOSE` | 后30分钟收益，反映尾盘调仓和集中执行造成的价格压力。 |
| `F5_1_volume_hhi` | -0.125000 | `MINUTE_VOLUME` | 分钟成交量HHI，刻画成交是否集中于少数时点。 |
| `F5_2_open_vol_ratio` | -0.125000 | `MINUTE_VOLUME` | 开盘最初6根分钟bar的成交量占比，刻画开盘阶段的信息到达和抢跑交易。 |
| `F5_3_close_vol_ratio` | -0.225000 | `MINUTE_VOLUME` | 后30分钟成交量占比，刻画尾盘调仓和集中执行。 |
| `F_COMBO_7_wat` | -0.125000 | `MINUTE_VOLUME, MINUTE_OPEN, MINUTE_CLOSE` | 成交量加权交易时点与日内方向结合，刻画信息到达时段。 |
| `N3_close_count_ratio` | -0.100000 | `MINUTE_NUMBER` | 后30分钟成交笔数占比，刻画尾盘参与密度。 |
| `N8_tail_ticket_reversal` | 0.100000 | `MINUTE_OHLC, MINUTE_AMOUNT, MINUTE_NUMBER` | 尾盘收益取反并乘尾盘单笔金额相对比例，刻画尾盘大单冲击后的修复。 |

## factor_06：相对分钟Amihud冲击

公式：`1.000000 * z(F_COMBO_4_amihud_hybrid)`

经济含义：分钟Amihud相对20日均值的变化，检验流动性冲击。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F_COMBO_4_amihud_hybrid` | 1.000000 | `MINUTE_CLOSE, MINUTE_AMOUNT` | 分钟Amihud相对20日均值的变化，检验流动性冲击。 |

## factor_07：相对VPIN订单流毒性

公式：`-1.000000 * z(F_COMBO_2_vpin_informed)`

经济含义：VPIN相对20日均值的变化，检验订单流毒性是否异常。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F_COMBO_2_vpin_informed` | -1.000000 | `MINUTE_CLOSE, MINUTE_VOLUME` | VPIN相对20日均值的变化，检验订单流毒性是否异常。 |

## factor_08：日内与五日趋势确认

公式：`-1.000000 * z(G2_1_intraday_ret5d)`

经济含义：日内方向与5日收益同向时保留交互，刻画短期趋势确认。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `G2_1_intraday_ret5d` | -1.000000 | `MINUTE_OPEN, MINUTE_CLOSE, DAILY_CLOSE` | 日内方向与五日收益同向时保留交互，刻画短期趋势确认。 |

## factor_09：分钟Amihud价格冲击

公式：`1.000000 * z(F6_2_amihud_min)`

经济含义：分钟收益绝对值相对分钟成交额的均值，刻画单位资金推动价格的能力。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F6_2_amihud_min` | 1.000000 | `MINUTE_CLOSE, MINUTE_AMOUNT` | 分钟收益绝对值相对分钟成交额的均值，刻画单位资金推动价格的能力。 |

## factor_10：成交量-成交笔数集中度差

公式：`0.500000 * z(F5_1_volume_hhi) -0.500000 * z(N4_count_hhi)`

经济含义：成交量HHI减去成交笔数HHI，刻画成交金额集中但交易笔数不集中时的单笔规模变化。

| 子因子 | 权重 | 原始字段 | 子因子经济含义 |
|---|---:|---|---|
| `F5_1_volume_hhi` | 0.500000 | `MINUTE_VOLUME` | 分钟成交量HHI，刻画成交是否集中于少数时点。 |
| `N4_count_hhi` | -0.500000 | `MINUTE_NUMBER` | 分钟成交笔数HHI，刻画交易活跃度在时段上的集中程度。 |
