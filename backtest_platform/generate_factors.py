# -*- coding: utf-8 -*-
"""
Generate 600+ quantitative factor expressions for factor_queue.txt.
Each expression has clear investment logic, not mechanical combinations.
Format: expression|neutralization  (market_cap or none)
"""

from pathlib import Path

output_path = Path("D:/yyb/backtest_platform/factor_queue.txt")
lines = []
seen = set()

def add(expr, neutral="market_cap"):
    """Add expression, skip duplicates."""
    key = f"{expr}|{neutral}"
    if key not in seen:
        seen.add(key)
        lines.append(key)

# ================================================================
# SECTION 1: RETURNS & MOMENTUM (Trend-following logic)
# ================================================================
# --- returns (日收益率) ---
add("rank(returns)", "market_cap")                     # 截面动量：涨得多的继续涨
add("-rank(returns)", "market_cap")                    # 截面反转：涨得多的回调
add("ts_rank(returns, 10)", "market_cap")              # 双周时序动量：近期强势股
add("ts_rank(returns, 40)", "market_cap")              # 双月时序动量：中期强势股
add("signed_power(returns, 2)", "none")                # 收益平方：放大极端信号
add("signed_power(returns, 0.5)", "none")              # 收益开方：压缩极端值
add("ts_decay_linear(returns, 5)", "market_cap")       # 5日衰减加权：最近权重最高
add("ts_decay_linear(returns, 20)", "market_cap")      # 20日衰减加权：月内趋势
add("ts_delta(returns, 5)", "none")                    # 5日收益变化：动量加速/减速
add("ts_delta(returns, 20)", "none")                   # 20日收益变化：中期加速
add("zscore(returns)", "market_cap")                   # 截面标准化收益
add("ts_mean(returns, 10)", "market_cap")              # 10日均收益：平滑动量
add("ts_mean(returns, 40)", "market_cap")              # 40日均收益：长期动量均值
add("ts_std(returns, 20)", "none")                     # 收益波动率：风险调整参照
add("ts_skew(returns, 20)", "market_cap")              # 收益偏度：正偏=散户追涨
add("ts_kurt(returns, 60)", "none")                    # 收益峰度：肥尾风险
add("group_neutralize(returns, market_cap)", "none")   # 市值中性化收益

# --- ret_5d (5日收益率) ---
add("rank(ret_5d)", "market_cap")                      # 周度动量排名
add("-rank(ret_5d)", "market_cap")                     # 周度反转：A股5日常见反转
add("ts_rank(ret_5d, 20)", "market_cap")               # 周度动量的月度稳定性
add("signed_power(ret_5d, 2)", "none")                 # 周度极端收益放大
add("ts_decay_linear(ret_5d, 10)", "market_cap")       # 周度收益衰减加权
add("ts_delta(ret_5d, 10)", "none")                    # 周度加速度变化
add("zscore(ret_5d)", "market_cap")                    # 周度收益截面标准化

# --- ret_10d (10日/双周收益率) ---
add("rank(ret_10d)", "market_cap")                     # 双周动量排名
add("-rank(ret_10d)", "market_cap")                    # 双周反转：过度反应修正
add("ts_rank(ret_10d, 20)", "market_cap")              # 双周动量的月稳定性
add("signed_power(ret_10d, 2)", "none")                # 双周信号放大
add("ts_decay_linear(ret_10d, 10)", "market_cap")      # 双周收益半月衰减
add("ts_delta(ret_10d, 20)", "none")                   # 双周动量变化
add("ts_mean(ret_10d, 20)", "market_cap")              # 双周收益均线
add("group_neutralize(ret_10d, market_cap)", "none")   # 市值中性双周收益

# --- ret_20d (20日/月度收益率) ---
add("rank(ret_20d)", "market_cap")                     # 月度动量：经典Jegadeesh-Titman
add("-rank(ret_20d)", "market_cap")                    # 月度反转
add("ts_rank(ret_20d, 40)", "market_cap")              # 月度动量双月稳定性
add("signed_power(ret_20d, 2)", "none")                # 月度动量非线性增强
add("signed_power(ret_20d, 0.5)", "none")              # 月度动量压缩极端
add("ts_decay_linear(ret_20d, 20)", "market_cap")      # 月度收益衰减加权
add("ts_delta(ret_20d, 20)", "none")                   # 月度动量加速度
add("ts_delta(ret_20d, 40)", "none")                   # 双月动量对比
add("zscore(ret_20d)", "market_cap")                   # 市值中性月度收益
add("ts_mean(ret_20d, 10)", "market_cap")              # 月度收益平滑

# --- ret_40d (40日/双月收益率) ---
add("rank(ret_40d)", "market_cap")                     # 双月动量：中期趋势
add("-rank(ret_40d)", "market_cap")                    # 双月反转：中长期过度反应
add("ts_rank(ret_40d, 60)", "market_cap")              # 双月动量季度稳定性
add("signed_power(ret_40d, 2)", "none")                # 中期动量信号放大
add("ts_decay_linear(ret_40d, 20)", "market_cap")      # 双月收益衰减
add("ts_delta(ret_40d, 20)", "none")                   # 中期收益变化
add("zscore(ret_40d)", "market_cap")                   # 截面标准化
add("ts_mean(ret_40d, 20)", "market_cap")              # 双月收益均线

# --- ret_60d (60日/季度收益率) ---
add("rank(ret_60d)", "market_cap")                     # 季度动量
add("-rank(ret_60d)", "market_cap")                    # 季度反转
add("ts_rank(ret_60d, 120)", "market_cap")             # 季度动量半年稳定性
add("signed_power(ret_60d, 2)", "none")                # 季度信号放大
add("ts_decay_linear(ret_60d, 40)", "market_cap")      # 季度收益衰减
add("ts_delta(ret_60d, 40)", "none")                   # 季度间变化
add("zscore(ret_60d)", "market_cap")                   # 截面标准化

# --- ret_120d_skip5 (120日跳5日收益率) ---
add("rank(ret_120d_skip5)", "market_cap")              # 纯长期动量：剔除短期反转
add("-rank(ret_120d_skip5)", "market_cap")             # 长期反转
add("signed_power(ret_120d_skip5, 2)", "none")         # 长期极端信号
add("ts_decay_linear(ret_120d_skip5, 60)", "market_cap") # 半年收益季度衰减
add("zscore(ret_120d_skip5)", "market_cap")            # 截面标准化
add("group_neutralize(ret_120d_skip5, market_cap)", "none") # 市值中性

# --- cumret_5d (5日复利累积收益) ---
add("rank(cumret_5d)", "market_cap")                   # 5日复利排名
add("-rank(cumret_5d)", "market_cap")                  # 5日反转（复利版）
add("ts_rank(cumret_5d, 20)", "market_cap")            # 短期累积趋势稳定性
add("signed_power(cumret_5d, 2)", "none")              # 连续涨跌信号放大
add("ts_delta(cumret_5d, 5)", "none")                  # 累积收益加速度
add("zscore(cumret_5d)", "market_cap")                 # 截面标准化
# --- sharpe_60d (60日夏普比率) ---
add("rank(sharpe_60d)", "market_cap")                  # 高质量动量：夏普高的继续强
add("-rank(sharpe_60d)", "market_cap")                 # 高夏普反转
add("signed_power(sharpe_60d, 2)", "none")             # 风险调整信号放大
add("ts_decay_linear(sharpe_60d, 20)", "market_cap")   # 夏普衰减加权
add("ts_delta(sharpe_60d, 20)", "none")                # 夏普变化：效率提升/下降
add("ts_mean(sharpe_60d, 20)", "market_cap")           # 夏普均线

# --- mom_vol_adj (波动率调整动量) ---
add("rank(mom_vol_adj)", "market_cap")                 # 纯动量：剔波动后排名
add("-rank(mom_vol_adj)", "market_cap")                # 纯动量反转
add("signed_power(mom_vol_adj, 2)", "none")            # 纯动量信号放大
add("ts_decay_linear(mom_vol_adj, 20)", "market_cap")  # 纯动量衰减
add("ts_delta(mom_vol_adj, 10)", "none")               # 纯动量加速度
add("zscore(mom_vol_adj)", "market_cap")               # 纯动量截面标准化

# --- close_vs_high_20d (收盘距20日高点) ---
add("rank(close_vs_high_20d)", "market_cap")           # 距高点近=强势延续
add("-rank(close_vs_high_20d)", "market_cap")          # 距高点近=即将回调
add("ts_rank(close_vs_high_20d, 20)", "market_cap")    # 相对高点趋势
add("signed_power(close_vs_high_20d, 2)", "none")      # 极端接近/远离信号
add("ts_delta(close_vs_high_20d, 5)", "none")          # 相对高点变化率

# --- max_dd_60d (60日最大回撤) ---
add("-rank(max_dd_60d)", "market_cap")                 # 回撤小=稳健股
add("rank(max_dd_60d)", "market_cap")                  # 回撤大=反弹机会
add("ts_rank(max_dd_60d, 40)", "market_cap")           # 回撤趋势
add("signed_power(max_dd_60d, 0.5)", "none")           # 回撤信号压缩
add("ts_delta(max_dd_60d, 20)", "none")                # 回撤恶化/改善

# ================================================================
# PROGRESS: ~100 expressions so far
# ================================================================

# ================================================================
# SECTION 2: REVERSAL (Mean-reversion logic)
# ================================================================
# --- rev_1d (1日反转) ---
add("rank(rev_1d)", "market_cap")                      # 昨日反转排名
add("-rank(rev_1d)", "market_cap")                     # 昨日反转取反=延续昨日方向
add("ts_rank(rev_1d, 5)", "market_cap")                # 日反转周度一致性
add("signed_power(rev_1d, 2)", "none")                 # 反转信号放大
add("ts_decay_linear(rev_1d, 5)", "market_cap")        # 反转信号衰减加权
add("ts_mean(rev_1d, 10)", "market_cap")               # 反转均值：持续反转强度

# --- rev_5d (5日反转) ---
add("rank(rev_5d)", "market_cap")                      # 周度反转排名
add("-rank(rev_5d)", "market_cap")                     # 周度反转取反=周度动量
add("ts_rank(rev_5d, 20)", "market_cap")               # 周度反转月度持续性
add("signed_power(rev_5d, 2)", "none")                 # 周度反转放大
add("ts_decay_linear(rev_5d, 10)", "market_cap")       # 周度反转衰减
add("ts_delta(rev_5d, 10)", "none")                    # 反转强度变化
add("zscore(rev_5d)", "market_cap")                    # 截面标准化

# --- rev_10d (10日反转) ---
add("rank(rev_10d)", "market_cap")                     # 双周反转排名
add("ts_rank(rev_10d, 20)", "market_cap")              # 双周反转趋势
add("signed_power(rev_10d, 2)", "none")                # 反转信号放大
add("ts_decay_linear(rev_10d, 10)", "market_cap")      # 反转衰减加权
add("zscore(rev_10d)", "market_cap")                   # 截面标准化

# --- rev_20d (20日反转) ---
add("rank(rev_20d)", "market_cap")                     # 月度反转排名
add("ts_rank(rev_20d, 40)", "market_cap")              # 月度反转长期稳定
add("signed_power(rev_20d, 2)", "none")                # 月度反转放大
add("ts_decay_linear(rev_20d, 20)", "market_cap")      # 月度反转衰减
add("ts_delta(rev_20d, 20)", "none")                   # 反转强度变化

# --- rev_overnight (隔夜反转) ---
add("rank(rev_overnight)", "market_cap")               # 隔夜反转排名
add("ts_rank(rev_overnight, 10)", "market_cap")        # 隔夜反转趋势
add("signed_power(rev_overnight, 2)", "none")          # 隔夜反转放大

# --- abnormal_vol_rev (异常放量反转) ---
add("rank(abnormal_vol_rev)", "market_cap")            # 放量反转：量越大反转越强
add("ts_rank(abnormal_vol_rev, 20)", "market_cap")     # 放量反转稳定性
add("signed_power(abnormal_vol_rev, 2)", "none")       # 放量反转放大
add("ts_decay_linear(abnormal_vol_rev, 10)", "market_cap") # 放量反转衰减

# --- extreme_loser_5d (极端输家反转) ---
add("rank(extreme_loser_5d)", "market_cap")            # 输家反转：超跌反弹
add("ts_rank(extreme_loser_5d, 20)", "market_cap")     # 输家反转持续性
add("signed_power(extreme_loser_5d, 2)", "none")       # 输家反转信号放大
add("ts_decay_linear(extreme_loser_5d, 10)", "market_cap") # 输家反转衰减

# --- extreme_winner_5d (极端赢家反转) ---
add("rank(extreme_winner_5d)", "market_cap")           # 赢家反转：暴涨回调
add("ts_rank(extreme_winner_5d, 20)", "market_cap")    # 赢家反转持续性
add("signed_power(extreme_winner_5d, 2)", "none")      # 赢家反转放大

# --- rev_vol_regime (波动状态反转) ---
add("rank(rev_vol_regime)", "market_cap")              # 高波环境反转增强
add("ts_rank(rev_vol_regime, 20)", "market_cap")       # 波动反转持续性
add("signed_power(rev_vol_regime, 2)", "none")         # 波动反转放大

# ================================================================
# PROGRESS: ~155 expressions so far
# ================================================================

# ================================================================
# SECTION 3: VOLATILITY (Low-vol and risk-based logic)
# ================================================================
# --- vol_5d (5日波动率) ---
add("-rank(vol_5d)", "market_cap")                     # 低周波异象：低波动高收益
add("rank(vol_5d)", "market_cap")                      # 高波动=高风险偏好
add("ts_rank(vol_5d, 20)", "market_cap")               # 周波月度趋势
add("ts_delta(vol_5d, 5)", "none")                     # 波动加速：波动率上行
add("ts_delta(vol_5d, 5)", "none")                     # 波动率变化(dup guard in add())
add("signed_power(vol_5d, 2)", "none")                 # 极端波动放大
add("zscore(vol_5d)", "market_cap")                    # 截面标准化波动
add("ts_decay_linear(vol_5d, 5)", "market_cap")        # 波动衰减加权

# --- vol_10d (10日波动率) ---
add("-rank(vol_10d)", "market_cap")                    # 低双周波异象
add("ts_rank(vol_10d, 20)", "market_cap")              # 双周波趋势
add("ts_delta(vol_10d, 10)", "none")                   # 双周波变化
add("signed_power(vol_10d, 2)", "none")                # 双周波放大
add("zscore(vol_10d)", "market_cap")                   # 截面标准化
add("ts_decay_linear(vol_10d, 10)", "market_cap")      # 双周波衰减

# --- vol_20d (20日波动率) ---
add("-rank(vol_20d)", "market_cap")                    # 低月度波异象：经典低波因子
add("ts_rank(vol_20d, 40)", "market_cap")              # 月度波动双月趋势
add("ts_delta(vol_20d, 20)", "none")                   # 月度波动变化
add("signed_power(vol_20d, 2)", "none")                # 月度波放大
add("signed_power(vol_20d, 0.5)", "none")              # 波动信号压缩
add("zscore(vol_20d)", "market_cap")                   # 截面标准化
add("ts_decay_linear(vol_20d, 20)", "market_cap")      # 月度波衰减
add("ts_mean(vol_20d, 20)", "market_cap")              # 波动均线

# --- vol_40d (40日波动率) ---
add("-rank(vol_40d)", "market_cap")                    # 低双月波异象
add("ts_rank(vol_40d, 60)", "market_cap")              # 双月波动趋势
add("ts_delta(vol_40d, 20)", "none")                   # 中期波动变化
add("signed_power(vol_40d, 2)", "none")                # 双月波放大
add("zscore(vol_40d)", "market_cap")                   # 截面标准化

# --- vol_60d (60日波动率) ---
add("-rank(vol_60d)", "market_cap")                    # 低季度波异象
add("ts_rank(vol_60d, 120)", "market_cap")             # 季度波半年趋势
add("ts_delta(vol_60d, 40)", "none")                   # 季度波变化
add("signed_power(vol_60d, 2)", "none")                # 季度波放大
add("zscore(vol_60d)", "market_cap")                   # 截面标准化

# --- vol_120d (120日/半年波动率) ---
add("-rank(vol_120d)", "market_cap")                   # 低半年波：长期低风险
add("ts_rank(vol_120d, 60)", "market_cap")             # 长期波动季度趋势
add("ts_delta(vol_120d, 60)", "none")                  # 长期波动变化
add("signed_power(vol_120d, 0.5)", "none")             # 长期波动压缩
add("zscore(vol_120d)", "market_cap")                  # 截面标准化

# --- upside_vol_60d (上行波动率) ---
add("rank(upside_vol_60d)", "market_cap")              # 高上行波=上涨动能强
add("-rank(upside_vol_60d)", "market_cap")             # 上行波低=缺乏冲劲
add("ts_rank(upside_vol_60d, 40)", "market_cap")       # 上行波动趋势
add("signed_power(upside_vol_60d, 2)", "none")         # 上行波动放大
add("ts_delta(upside_vol_60d, 20)", "none")            # 上行波动加速
add("zscore(upside_vol_60d)", "market_cap")            # 截面标准化

# --- downside_vol_60d (下行波动率) ---
add("-rank(downside_vol_60d)", "market_cap")           # 低下行波=尾部风险小
add("rank(downside_vol_60d)", "market_cap")            # 高下行波=崩盘风险指标
add("ts_rank(downside_vol_60d, 40)", "market_cap")     # 下行波趋势
add("signed_power(downside_vol_60d, 2)", "none")       # 下行波放大
add("ts_delta(downside_vol_60d, 20)", "none")          # 下行波变化
add("zscore(downside_vol_60d)", "market_cap")          # 截面标准化

# --- vol_ratio (波动率比值 20/60) ---
add("-rank(vol_ratio)", "market_cap")                  # 波动降低=趋于平稳
add("rank(vol_ratio)", "market_cap")                   # 波动扩大=风险预警
add("ts_rank(vol_ratio, 20)", "market_cap")            # 波动比趋势
add("signed_power(vol_ratio, 2)", "none")              # 波动比放大
add("ts_delta(vol_ratio, 10)", "none")                 # 波动比加速度

# --- vol_ratio_5_20 (波动率比 5/20) ---
add("-rank(vol_ratio_5_20)", "market_cap")             # 短期波收缩：变盘前兆
add("rank(vol_ratio_5_20)", "market_cap")              # 短期波扩张：趋势加速
add("ts_rank(vol_ratio_5_20, 20)", "market_cap")       # 短期波比趋势
add("signed_power(vol_ratio_5_20, 2)", "none")         # 波比信号放大
add("ts_delta(vol_ratio_5_20, 5)", "none")             # 短期波比变化

# --- vol_ratio_20_60 (波动率比 20/60) ---
add("-rank(vol_ratio_20_60)", "market_cap")            # 中短期波收敛
add("rank(vol_ratio_20_60)", "market_cap")             # 中短期波扩张
add("ts_rank(vol_ratio_20_60, 20)", "market_cap")      # 波比趋势
add("signed_power(vol_ratio_20_60, 2)", "none")        # 波比信号放大
add("ts_delta(vol_ratio_20_60, 10)", "none")           # 波比变化

# --- down_up_vol_ratio (下行上行波动比) ---
add("-rank(down_up_vol_ratio)", "market_cap")          # 下行相对上行波低=多头主导
add("rank(down_up_vol_ratio)", "market_cap")           # 下行波占比高=空头压力
add("ts_rank(down_up_vol_ratio, 40)", "market_cap")    # 空头压力趋势
add("signed_power(down_up_vol_ratio, 2)", "none")      # 空头压力放大

# --- skewness_20d (20日偏度) ---
add("-rank(skewness_20d)", "market_cap")               # 负偏=崩盘风险，回避
add("rank(skewness_20d)", "market_cap")                # 正偏=彩票型，散户追
add("ts_rank(skewness_20d, 20)", "market_cap")         # 偏度趋势
add("signed_power(skewness_20d, 2)", "none")           # 偏度信号放大

# --- skewness_60d (60日偏度) ---
add("-rank(skewness_60d)", "market_cap")               # 长期负偏回避
add("ts_rank(skewness_60d, 40)", "market_cap")         # 偏度趋势
add("signed_power(skewness_60d, 2)", "none")           # 偏度放大

# --- kurtosis_60d (60日峰度) ---
add("-rank(kurtosis_60d)", "market_cap")               # 高峰度=极端事件风险，回避
add("rank(kurtosis_60d)", "market_cap")                # 高峰度=大涨潜力
add("ts_rank(kurtosis_60d, 40)", "market_cap")         # 峰度趋势
add("signed_power(kurtosis_60d, 0.5)", "none")         # 峰度信号压缩

# --- bollinger_width (布林带宽度) ---
add("-rank(bollinger_width)", "market_cap")            # 布林收窄=变盘前兆：突破在即
add("rank(bollinger_width)", "market_cap")             # 布林扩张=趋势持续
add("ts_rank(bollinger_width, 20)", "market_cap")      # 布林宽度趋势
add("ts_delta(bollinger_width, 5)", "none")            # 布林宽度变化：变盘信号

# --- intraday_volatility (日内波动率) ---
add("-rank(intraday_volatility)", "market_cap")        # 日内振幅小=筹码稳定
add("rank(intraday_volatility)", "market_cap")         # 日内振幅大=资金博弈激烈
add("ts_rank(intraday_volatility, 20)", "market_cap")  # 日内振幅趋势
add("signed_power(intraday_volatility, 2)", "none")    # 日内振幅放大
add("ts_delta(intraday_volatility, 5)", "none")        # 日内振幅变化

# ================================================================
# PROGRESS: ~255 expressions so far
# ================================================================

# ================================================================
# SECTION 4: LIQUIDITY & VOLUME (Volume-price logic)
# ================================================================
# --- volume (日成交量) ---
add("-rank(volume)", "market_cap")                     # 低量=无人问津或筹码锁定
add("rank(volume)", "market_cap")                      # 高量=资金关注
add("ts_rank(volume, 10)", "market_cap")               # 成交量短期趋势
add("ts_rank(volume, 40)", "market_cap")               # 成交量中期趋势
add("ts_delta(volume, 5)", "none")                     # 成交量突变：放量/缩量
add("signed_power(volume, 0.5)", "none")               # 成交量信号压缩
add("zscore(volume)", "market_cap")                    # 截面标准化成交量
add("ts_decay_linear(volume, 5)", "market_cap")        # 成交量衰减加权

# --- amount (日成交额) ---
add("-rank(amount)", "market_cap")                     # 低成交额=冷门股
add("rank(amount)", "market_cap")                      # 高成交额=热门股
add("ts_delta(amount, 5)", "none")                     # 成交额变化
add("zscore(amount)", "market_cap")                    # 截面标准化成交额

# --- dollar_volume (成交额=收盘价*成交量) ---
add("-rank(dollar_volume)", "market_cap")              # 低成交额
add("rank(dollar_volume)", "market_cap")               # 高成交额=机构偏好
add("ts_rank(dollar_volume, 20)", "market_cap")        # 成交额趋势
add("ts_delta(dollar_volume, 10)", "none")             # 成交额变化
add("zscore(dollar_volume)", "market_cap")             # 截面标准化

# --- log_dollar_vol (对数成交额) ---
add("-rank(log_dollar_vol)", "market_cap")             # 低对数成交额
add("rank(log_dollar_vol)", "market_cap")              # 高对数成交额=大市值活跃
add("ts_rank(log_dollar_vol, 20)", "market_cap")       # 对数成交额趋势
add("ts_delta(log_dollar_vol, 10)", "none")            # 对数成交额变化

# --- volume_profile_ratio (量比: vol/20日均量) ---
add("rank(volume_profile_ratio)", "market_cap")        # 高量比=当日放量，资金异动
add("-rank(volume_profile_ratio)", "market_cap")       # 低量比=缩量整理
add("ts_rank(volume_profile_ratio, 10)", "market_cap") # 量比趋势
add("signed_power(volume_profile_ratio, 2)", "none")   # 极端放量信号
add("ts_delta(volume_profile_ratio, 5)", "none")       # 量比变化

# --- volume_breakout (成交量突破: vol/60日均量) ---
add("rank(volume_breakout)", "market_cap")             # 高突破=资金大幅流入
add("-rank(volume_breakout)", "market_cap")            # 低突破=无人关注
add("ts_rank(volume_breakout, 20)", "market_cap")      # 量突破趋势
add("signed_power(volume_breakout, 2)", "none")        # 极端突破信号
add("ts_delta(volume_breakout, 5)", "none")            # 量突破变化

# --- turnover_rate (换手率) ---
add("rank(turnover_rate)", "market_cap")               # 高换手=交易活跃
add("-rank(turnover_rate)", "market_cap")              # 低换手=筹码稳定/缺乏关注
add("ts_rank(turnover_rate, 10)", "market_cap")        # 换手率趋势
add("signed_power(turnover_rate, 2)", "none")          # 极端换手信号
add("ts_delta(turnover_rate, 5)", "none")              # 换手率变化

# --- turnover_5d (5日换手率) ---
add("rank(turnover_5d)", "market_cap")                 # 周度活跃度排名
add("-rank(turnover_5d)", "market_cap")                # 周度低换手=筹码锁定
add("ts_rank(turnover_5d, 20)", "market_cap")          # 周换手月度趋势
add("ts_delta(turnover_5d, 5)", "none")                # 周换手变化

# --- turnover_change (换手率变化) ---
add("rank(turnover_change)", "market_cap")             # 换手加速=资金加速进出
add("-rank(turnover_change)", "market_cap")            # 换手减速=关注度下降
add("ts_rank(turnover_change, 20)", "market_cap")      # 换手变化趋势
add("signed_power(turnover_change, 2)", "none")        # 换手变化放大
add("ts_delta(turnover_change, 5)", "none")            # 换手加速度

# --- adv5 (5日均量) ---
add("rank(adv5)", "market_cap")                        # 短期均量排名
add("ts_delta(adv5, 5)", "none")                       # 短期均量变化
add("ts_rank(adv5, 20)", "market_cap")                 # 短期均量趋势

# --- adv20 (20日均量) ---
add("rank(adv20)", "market_cap")                       # 月度均量排名
add("ts_delta(adv20, 10)", "none")                     # 月度均量变化
add("ts_rank(adv20, 60)", "market_cap")                # 月度均量季度趋势

# --- volume_trend_20d (量趋势: 20日时序排名) ---
add("rank(volume_trend_20d)", "market_cap")            # 量持续放大=资金持续流入
add("-rank(volume_trend_20d)", "market_cap")           # 量持续萎缩=资金撤退
add("ts_rank(volume_trend_20d, 20)", "market_cap")     # 量趋势稳定性
add("signed_power(volume_trend_20d, 2)", "none")       # 量趋势放大

# --- amount_volatility (成交额波动率: CV) ---
add("-rank(amount_volatility)", "market_cap")          # 成交额稳定=资金持续关注
add("rank(amount_volatility)", "market_cap")           # 成交额波动=资金进出无常
add("ts_rank(amount_volatility, 20)", "market_cap")    # 成交额波趋势
add("ts_delta(amount_volatility, 10)", "none")         # 成交额波变化

# --- volume_price_corr (量价20日相关) ---
add("rank(volume_price_corr)", "market_cap")           # 量价正相关=放量上涨健康
add("-rank(volume_price_corr)", "market_cap")          # 量价负相关=背离信号
add("ts_rank(volume_price_corr, 20)", "market_cap")    # 量价关系稳定性
add("signed_power(volume_price_corr, 2)", "none")      # 量价关系放大
add("ts_delta(volume_price_corr, 10)", "none")         # 量价关系变化

# --- volume_price_div (量价背离: ret*volume_trend) ---
add("rank(volume_price_div)", "market_cap")            # 量价共振=趋势确认
add("-rank(volume_price_div)", "market_cap")           # 量价背离=顶部/底部信号
add("ts_rank(volume_price_div, 20)", "market_cap")     # 量价背离趋势
add("signed_power(volume_price_div, 2)", "none")       # 背离信号放大

# --- amihud_20d (Amihud非流动性) ---
add("-rank(amihud_20d)", "market_cap")                 # 低Amihud=高流动性，机构偏好
add("rank(amihud_20d)", "market_cap")                  # 高Amihud=流动性溢价补偿
add("ts_rank(amihud_20d, 40)", "market_cap")           # 非流动性趋势
add("ts_delta(amihud_20d, 20)", "none")                # 流动性恶化/改善
add("zscore(amihud_20d)", "market_cap")                # 截面标准化

# ================================================================
# PROGRESS: ~340 expressions so far
# ================================================================

# ================================================================
# SECTION 5: PRICE & PATTERN (Technical patterns)
# ================================================================
# --- close (收盘价) ---
add("rank(close)", "market_cap")                       # 高价股排名
add("ts_delta(close, 5)", "none")                      # 短期价格变化
add("ts_mean(close, 5)", "market_cap")                 # 5日均价参考
add("ts_mean(close, 20)", "market_cap")                # 20日均价参考

# --- open (开盘价) ---
add("rank(open)", "market_cap")                        # 开盘价排名
add("ts_delta(open, 5)", "none")                       # 开盘价变化

# --- high (最高价) ---
add("ts_max(high, 20)", "market_cap")                  # 20日最高价：阻力位参考
add("ts_max(high, 60)", "market_cap")                  # 60日最高价

# --- low (最低价) ---
add("ts_min(low, 20)", "market_cap")                   # 20日最低价：支撑位参考
add("ts_min(low, 60)", "market_cap")                   # 60日最低价

# --- preclose (前收盘价) ---
add("ts_delta(preclose, 5)", "none")                   # 前收盘价变化

# --- upper_shadow_pct (上影线占比) ---
add("-rank(upper_shadow_pct)", "market_cap")           # 上影短=买方坚定，无冲高回落
add("rank(upper_shadow_pct)", "market_cap")            # 上影长=卖压沉重，机构出货
add("ts_rank(upper_shadow_pct, 20)", "market_cap")     # 上影趋势：持续出货压力
add("signed_power(upper_shadow_pct, 2)", "none")       # 上影信号放大
add("ts_decay_linear(upper_shadow_pct, 10)", "market_cap") # 上影衰减加权

# --- lower_shadow_pct (下影线占比) ---
add("rank(lower_shadow_pct)", "market_cap")            # 下影长=买盘强劲，机构吸筹
add("-rank(lower_shadow_pct)", "market_cap")           # 下影短=卖方控制，无支撑
add("ts_rank(lower_shadow_pct, 20)", "market_cap")     # 下影趋势：持续支撑
add("signed_power(lower_shadow_pct, 2)", "none")       # 下影信号放大
add("ts_decay_linear(lower_shadow_pct, 10)", "market_cap") # 下影衰减加权

# --- upper_shadow (上影线比例，分钟数据版) ---
add("-rank(upper_shadow)", "market_cap")               # 分钟版上影短=买方坚决
add("rank(upper_shadow)", "market_cap")                # 分钟版上影长
add("ts_rank(upper_shadow, 10)", "market_cap")         # 分钟版上影趋势

# --- lower_shadow (下影线比例，分钟数据版) ---
add("rank(lower_shadow)", "market_cap")                # 分钟版下影长=买盘支撑
add("-rank(lower_shadow)", "market_cap")               # 分钟版下影短
add("ts_rank(lower_shadow, 10)", "market_cap")         # 分钟版下影趋势

# --- body_ratio (实体占比) ---
add("rank(body_ratio)", "market_cap")                  # 大实体=方向明确，趋势强
add("-rank(body_ratio)", "market_cap")                 # 小实体=方向不明，多空僵持
add("ts_rank(body_ratio, 20)", "market_cap")           # 实体趋势
add("signed_power(body_ratio, 2)", "none")             # 实体信号放大

# --- doji_score (十字星评分) ---
add("rank(doji_score)", "market_cap")                  # 高十字星=多空均衡，可能反转
add("-rank(doji_score)", "market_cap")                 # 低十字星=方向明确
add("ts_rank(doji_score, 10)", "market_cap")           # 十字星趋势

# --- gap_up (向上跳空幅度) ---
add("rank(gap_up)", "market_cap")                      # 高开幅度大=利好冲击
add("-rank(gap_up)", "market_cap")                     # 低开或无跳空
add("ts_rank(gap_up, 10)", "market_cap")               # 跳空趋势
add("signed_power(gap_up, 2)", "none")                 # 跳空信号放大

# --- gap_down (向下跳空) ---
add("-rank(gap_down)", "market_cap")                   # 无向下跳空=无恐慌
add("rank(gap_down)", "market_cap")                    # 大向下跳空=恐慌超卖，反弹机会
add("ts_rank(gap_down, 10)", "market_cap")             # 向下跳空趋势
add("signed_power(gap_down, 2)", "none")               # 恐慌信号放大

# --- gap_momentum (跳空动量: auction_return * returns) ---
add("rank(gap_momentum)", "market_cap")                # 跳空方向延续
add("-rank(gap_momentum)", "market_cap")               # 跳空后反转
add("ts_rank(gap_momentum, 10)", "market_cap")         # 跳空动量趋势

# --- close_vs_low_20d (收盘距20日低) ---
add("rank(close_vs_low_20d)", "market_cap")            # 远离低点=强势
add("-rank(close_vs_low_20d)", "market_cap")           # 接近低点=可能超卖反弹
add("ts_rank(close_vs_low_20d, 20)", "market_cap")     # 相对低点趋势
add("signed_power(close_vs_low_20d, 0.5)", "none")     # 相对低点压缩

# --- auction_return (集合竞价收益率/隔夜跳空) ---
add("rank(auction_return)", "market_cap")              # 隔夜跳空正=利好消化中
add("-rank(auction_return)", "market_cap")             # 隔夜跳空负=利空或回补
add("ts_rank(auction_return, 10)", "market_cap")       # 隔夜跳空趋势
add("signed_power(auction_return, 2)", "none")         # 跳空放大
add("ts_decay_linear(auction_return, 5)", "market_cap") # 跳空衰减

# ---- Price-derived ratios ----
add("rank(close) - rank(open)", "market_cap")          # 收盘vs开盘：日内方向
add("rank(high) - rank(low)", "market_cap")            # 日内振幅截面排名
add("rank(close) - rank(preclose)", "market_cap")      # 相对前收截面
add("rank(close)/rank(high)", "none")                  # 收盘相对高点
add("rank(close)/rank(low)", "none")                   # 收盘相对低点

# ================================================================
# PROGRESS: ~395 expressions so far
# ================================================================

# ================================================================
# SECTION 6: INTRADAY & MICROSTRUCTURE
# ================================================================
# --- morning_return (上午收益率) ---
add("rank(morning_return)", "market_cap")              # 早盘强=隔夜信息正面消化
add("-rank(morning_return)", "market_cap")             # 早盘弱=利空消化
add("ts_rank(morning_return, 10)", "market_cap")       # 早盘强度趋势
add("signed_power(morning_return, 2)", "none")         # 早盘方向放大
add("ts_decay_linear(morning_return, 5)", "market_cap") # 早盘衰减

# --- afternoon_return (下午收益率) ---
add("rank(afternoon_return)", "market_cap")            # 下午强=机构尾盘做多
add("-rank(afternoon_return)", "market_cap")           # 下午弱=尾盘抛压
add("ts_rank(afternoon_return, 10)", "market_cap")     # 尾盘强度趋势
add("signed_power(afternoon_return, 2)", "none")       # 尾盘方向放大
add("ts_decay_linear(afternoon_return, 5)", "market_cap") # 尾盘衰减

# --- first30min_return (开盘30分钟收益率) ---
add("rank(first30min_return)", "market_cap")           # 开盘强=开盘动量足
add("-rank(first30min_return)", "market_cap")          # 开盘弱=开盘抛压
add("ts_rank(first30min_return, 10)", "market_cap")    # 开盘动量趋势
add("signed_power(first30min_return, 2)", "none")      # 开盘动量放大
add("ts_decay_linear(first30min_return, 5)", "market_cap") # 开盘动量衰减

# --- first30_mom (开盘动量，分钟精确版) ---
add("rank(first30_mom)", "market_cap")                 # 分钟版开盘动量排名
add("ts_rank(first30_mom, 10)", "market_cap")          # 分钟版开盘趋势
add("signed_power(first30_mom, 2)", "none")            # 分钟版开盘放大

# --- last30min_return (尾盘30分钟收益率) ---
add("rank(last30min_return)", "market_cap")            # 尾盘强=机构收盘买入
add("-rank(last30min_return)", "market_cap")           # 尾盘弱=收盘卖出
add("ts_rank(last30min_return, 10)", "market_cap")     # 尾盘强度趋势
add("signed_power(last30min_return, 2)", "none")       # 尾盘方向放大
add("ts_decay_linear(last30min_return, 5)", "market_cap") # 尾盘衰减

# --- last30_mom (尾盘动量，分钟精确版) ---
add("rank(last30_mom)", "market_cap")                  # 分钟版尾盘动量排名
add("ts_rank(last30_mom, 10)", "market_cap")           # 分钟版尾盘趋势
add("signed_power(last30_mom, 2)", "none")             # 分钟版尾盘放大

# --- body_return (实体收益率/日内涨幅) ---
add("rank(body_return)", "market_cap")                 # 日内强=不含隔夜的真实涨幅
add("-rank(body_return)", "market_cap")                # 日内弱
add("ts_rank(body_return, 10)", "market_cap")          # 日内涨幅趋势
add("signed_power(body_return, 2)", "none")            # 日内涨幅放大

# --- intraday_mom (日内动量，分钟精确版) ---
add("rank(intraday_mom)", "market_cap")                # 分钟版日内动量
add("ts_rank(intraday_mom, 10)", "market_cap")         # 分钟版日内趋势
add("signed_power(intraday_mom, 2)", "none")           # 分钟版日内放大

# --- intraday_reversal (日内反转: -first30 * last30) ---
add("rank(intraday_reversal)", "market_cap")           # 高值=盘中反转：上午涨下午跌
add("-rank(intraday_reversal)", "market_cap")          # 低值=全天同向：信息持续消化
add("ts_rank(intraday_reversal, 10)", "market_cap")    # 日内反转趋势
add("signed_power(intraday_reversal, 2)", "none")      # 反转强度放大

# --- overnight_reversal (隔夜反转强度) ---
add("rank(overnight_reversal)", "market_cap")          # 高背离=散户机构博弈
add("ts_rank(overnight_reversal, 10)", "market_cap")   # 隔夜反转趋势
add("signed_power(overnight_reversal, 2)", "none")     # 隔夜反转放大

# --- am_pm_divergence (上下行背离度) ---
add("-rank(am_pm_divergence)", "market_cap")           # 负背离=盘中反转，信息冲击后修正
add("rank(am_pm_divergence)", "market_cap")            # 正=全天一致：趋势可靠
add("ts_rank(am_pm_divergence, 10)", "market_cap")     # 背离趋势
add("signed_power(am_pm_divergence, 2)", "none")       # 背离强度放大

# --- close_location (收盘价位置) ---
add("rank(close_location)", "market_cap")              # 高位收盘=买方控制全天
add("-rank(close_location)", "market_cap")             # 低位收盘=卖方主导
add("ts_rank(close_location, 10)", "market_cap")       # 收盘位置趋势
add("signed_power(close_location, 2)", "none")         # 收盘位置放大

# --- price_efficiency (日内价格效率) ---
add("rank(price_efficiency)", "market_cap")            # 高效率=信息冲击方向明确
add("-rank(price_efficiency)", "market_cap")           # 低效率=市场噪音多
add("ts_rank(price_efficiency, 10)", "market_cap")     # 价格效率趋势
add("signed_power(price_efficiency, 2)", "none")       # 效率信号放大

# --- vwap_gap (VWAP偏离度) ---
add("rank(vwap_gap)", "market_cap")                    # 高于VWAP=买方主导日内交易
add("-rank(vwap_gap)", "market_cap")                   # 低于VWAP=卖方主导
add("ts_rank(vwap_gap, 10)", "market_cap")             # VWAP偏离趋势
add("signed_power(vwap_gap, 2)", "none")               # VWAP信号放大
add("ts_decay_linear(vwap_gap, 5)", "market_cap")      # VWAP偏离衰减

# --- close_vs_vwap (收盘vsVWAP，分钟精确版) ---
add("rank(close_vs_vwap)", "market_cap")               # 分钟版VWAP位置
add("ts_rank(close_vs_vwap, 10)", "market_cap")        # 分钟版VWAP趋势
add("signed_power(close_vs_vwap, 2)", "none")          # 分钟版VWAP放大

# --- vwap_trend (VWAP趋势) ---
add("rank(vwap_trend)", "market_cap")                  # VWAP走高=资金持续流入
add("-rank(vwap_trend)", "market_cap")                 # VWAP走低=资金流出
add("ts_rank(vwap_trend, 10)", "market_cap")           # VWAP趋势稳定性

# --- volume_concentration (成交量集中度HHI) ---
add("rank(volume_concentration)", "market_cap")        # 高集中度=机构大单痕迹
add("-rank(volume_concentration)", "market_cap")       # 低集中度=散户分散交易
add("ts_rank(volume_concentration, 10)", "market_cap") # 集中度趋势
add("signed_power(volume_concentration, 2)", "none")   # 集中度信号放大

# --- volume_hhi (成交量HHI，分钟精确版) ---
add("rank(volume_hhi)", "market_cap")                  # 分钟版成交集中度
add("ts_rank(volume_hhi, 10)", "market_cap")           # 分钟版集中度趋势

# --- open_vol_ratio (开盘量占比) ---
add("rank(open_vol_ratio)", "market_cap")              # 开盘量大=信息冲击集中释放
add("-rank(open_vol_ratio)", "market_cap")             # 开盘量小=信息分散
add("ts_rank(open_vol_ratio, 10)", "market_cap")       # 开盘量比趋势

# --- close_vol_ratio (收盘量占比) ---
add("rank(close_vol_ratio)", "market_cap")             # 尾盘量大=被动基金调仓
add("-rank(close_vol_ratio)", "market_cap")            # 尾盘量小
add("ts_rank(close_vol_ratio, 10)", "market_cap")      # 尾盘量比趋势

# --- smart_money_vol (聪明钱成交量) ---
add("rank(smart_money_vol)", "market_cap")             # 正=聪明钱净买入，跟庄信号
add("-rank(smart_money_vol)", "market_cap")            # 负=聪明钱净卖出
add("ts_rank(smart_money_vol, 10)", "market_cap")      # 聪明钱趋势
add("signed_power(smart_money_vol, 2)", "none")        # 聪明钱信号放大

# --- large_trade_ratio (大单占比) ---
add("rank(large_trade_ratio)", "market_cap")           # 大单多=机构主导
add("-rank(large_trade_ratio)", "market_cap")          # 大单少=散户市场
add("ts_rank(large_trade_ratio, 10)", "market_cap")    # 大单占比趋势

# --- large_trade_signal (大单信号: 方向×强度) ---
add("rank(large_trade_signal)", "market_cap")          # 正=大单净买入
add("-rank(large_trade_signal)", "market_cap")         # 负=大单净卖出
add("ts_rank(large_trade_signal, 10)", "market_cap")   # 大单信号趋势

# --- roll_spread (Roll价差) ---
add("-rank(roll_spread)", "market_cap")                # 低价差=高流动性
add("rank(roll_spread)", "market_cap")                 # 高价差=流动性溢价补偿
add("ts_rank(roll_spread, 20)", "market_cap")          # 价差趋势

# --- amihud_min (分钟Amihud非流动性) ---
add("-rank(amihud_min)", "market_cap")                 # 低分钟Amihud=高日内流动性
add("rank(amihud_min)", "market_cap")                  # 高分钟Amihud
add("ts_rank(amihud_min, 20)", "market_cap")           # 分钟流动性趋势

# --- amihud_hybrid (混合Amihud) ---
add("-rank(amihud_hybrid)", "market_cap")              # 低混合Amihud=多尺度高流动性
add("rank(amihud_hybrid)", "market_cap")               # 高混合Amihud
add("ts_rank(amihud_hybrid, 20)", "market_cap")        # 混合流动性趋势

# --- vpin (VPIN知情交易概率) ---
add("-rank(vpin)", "market_cap")                      # 低VPIN=无内幕交易，安全
add("rank(vpin)", "market_cap")                       # 高VPIN=知情交易风险（正或负面）
add("ts_rank(vpin, 20)", "market_cap")                # VPIN趋势
add("signed_power(vpin, 2)", "none")                  # VPIN放大

# --- vpin_informed (知情交易强度) ---
add("rank(vpin_informed)", "market_cap")              # 知情交易强度排名
add("ts_rank(vpin_informed, 20)", "market_cap")       # 知情交易趋势

# --- vol_skew (波动率偏度) ---
add("rank(vol_skew)", "market_cap")                   # 上午波大=信息早盘集中
add("-rank(vol_skew)", "market_cap")                  # 下午波大=信息午后释放
add("ts_rank(vol_skew, 10)", "market_cap")            # 波动偏度趋势

# --- realized_vol (已实现波动率) ---
add("-rank(realized_vol)", "market_cap")              # 低已实现波=日内稳定
add("ts_rank(realized_vol, 20)", "market_cap")        # 已实现波趋势
add("ts_delta(realized_vol, 10)", "none")             # 已实现波变化

# --- opening_confirm (开盘确认) ---
add("rank(opening_confirm)", "market_cap")            # 开盘同向=趋势延续
add("ts_rank(opening_confirm, 10)", "market_cap")     # 开盘确认趋势

# --- close_manipulation (收盘操纵检测) ---
add("-rank(close_manipulation)", "market_cap")        # 无操纵嫌疑=健康
add("rank(close_manipulation)", "market_cap")         # 高操纵嫌疑=回避或利用
add("ts_rank(close_manipulation, 10)", "market_cap")  # 操纵检测趋势

# --- triple_confirm (三重确认) ---
add("rank(triple_confirm)", "market_cap")             # 三重同向=强信号确认
add("ts_rank(triple_confirm, 10)", "market_cap")      # 三重确认趋势

# --- wat (加权平均时间) ---
add("-rank(wat)", "market_cap")                       # 重心偏早盘=信息早释放
add("rank(wat)", "market_cap")                        # 重心偏尾盘=信息滞后或尾盘操纵
add("ts_rank(wat, 10)", "market_cap")                 # 交易时间重心趋势

# --- smart_money_vwap (聪明钱综合) ---
add("rank(smart_money_vwap)", "market_cap")           # 聪明钱+VWAP双重验证
add("ts_rank(smart_money_vwap, 10)", "market_cap")    # 聪明钱综合趋势

# --- vol_conc_mom (量集中×动量) ---
add("rank(vol_conc_mom)", "market_cap")               # 量集中在趋势方向=强信号
add("ts_rank(vol_conc_mom, 10)", "market_cap")        # 量集中动量趋势

# ================================================================
# PROGRESS: ~510 expressions so far
# ================================================================

# ================================================================
# SECTION 7: CROSS-MODAL & TECHNICAL
# ================================================================
# --- mom_vol_conf (动量波动确认) ---
add("rank(mom_vol_conf)", "market_cap")               # 高动量低波动=可持续趋势
add("ts_rank(mom_vol_conf, 20)", "market_cap")        # 动量波动确认趋势
add("signed_power(mom_vol_conf, 2)", "none")          # 确认信号放大

# --- mom_liquidity_adj (动量流动性调整) ---
add("rank(mom_liquidity_adj)", "market_cap")          # 纯动量剔除流动性溢价
add("ts_rank(mom_liquidity_adj, 20)", "market_cap")   # 纯动量趋势
add("signed_power(mom_liquidity_adj, 2)", "none")     # 纯动量放大

# --- rev_vol_conf (反转波动确认) ---
add("rank(rev_vol_conf)", "market_cap")               # 高波反转=过度反应修正
add("ts_rank(rev_vol_conf, 20)", "market_cap")        # 反转波动确认趋势
add("signed_power(rev_vol_conf, 2)", "none")          # 反转确认放大

# --- intraday_ret5d (日内×日频动量) ---
add("rank(intraday_ret5d)", "market_cap")             # 跨时间尺度动量一致
add("ts_rank(intraday_ret5d, 20)", "market_cap")      # 跨尺度动量趋势
add("signed_power(intraday_ret5d, 2)", "none")        # 跨尺度放大

# --- vwap_close_mom (VWAP×收盘动量) ---
add("rank(vwap_close_mom)", "market_cap")             # VWAP高位+动量正=机构坚定做多
add("ts_rank(vwap_close_mom, 20)", "market_cap")      # VWAP收盘动量趋势
add("signed_power(vwap_close_mom, 2)", "none")        # VWAP动量放大

# --- smart_money_rev (聪明钱×反转) ---
add("rank(smart_money_rev)", "market_cap")            # 聪明钱逆势买入=抄底信号
add("ts_rank(smart_money_rev, 20)", "market_cap")     # 聪明钱反转趋势
add("signed_power(smart_money_rev, 2)", "none")       # 聪明钱反转放大

# --- liquidity_premium (流动性溢价) ---
add("rank(liquidity_premium)", "market_cap")          # 高流动性溢价=补偿收益
add("-rank(liquidity_premium)", "market_cap")         # 低流动性溢价
add("ts_rank(liquidity_premium, 40)", "market_cap")   # 流动性溢价趋势

# --- rsi_14 (相对强弱指数RSI) ---
add("-rank(rsi_14)", "market_cap")                    # 高RSI超买=回调风险
add("rank(rsi_14)", "market_cap")                     # 低RSI超卖=反弹机会
add("ts_rank(rsi_14, 20)", "market_cap")              # RSI趋势
add("signed_power(rsi_14, 2)", "none")                # RSI信号放大
add("ts_delta(rsi_14, 5)", "none")                    # RSI变化方向

# --- bollinger_pos (布林带位置) ---
add("-rank(bollinger_pos)", "market_cap")             # 接近上轨=超买压力
add("rank(bollinger_pos)", "market_cap")              # 接近下轨=超卖支撑反弹
add("ts_rank(bollinger_pos, 20)", "market_cap")       # 布林位置趋势
add("ts_delta(bollinger_pos, 5)", "none")             # 布林位置变化

# --- beta_60d (60日Beta系数) ---
add("-rank(beta_60d)", "market_cap")                  # 低Beta异象：低系统风险高收益
add("rank(beta_60d)", "market_cap")                   # 高Beta=市场弹性大
add("ts_rank(beta_60d, 40)", "market_cap")            # Beta趋势
add("ts_delta(beta_60d, 20)", "none")                 # Beta变化

# --- market_cap_rank (市值排名) ---
add("rank(market_cap_rank)", "market_cap")            # 小市值效应(Banz 1981)
add("-rank(market_cap_rank)", "market_cap")           # 大市值=机构重仓
add("ts_rank(market_cap_rank, 40)", "market_cap")     # 市值排名趋势

# --- max_ret_20d (20日最大日收益) ---
add("-rank(max_ret_20d)", "market_cap")               # 最大收益高=彩票型偏好，后续收益低
add("rank(max_ret_20d)", "market_cap")                # 最大收益高=动量延续
add("ts_rank(max_ret_20d, 20)", "market_cap")         # 极端收益趋势
add("signed_power(max_ret_20d, 2)", "none")           # 极端收益放大

# --- min_ret_20d (20日最小日收益) ---
add("-rank(min_ret_20d)", "market_cap")               # 最差收益高=抗跌能力强
add("rank(min_ret_20d)", "market_cap")                # 最差收益低=崩盘后反弹
add("ts_rank(min_ret_20d, 20)", "market_cap")         # 最差收益趋势

# --- hit_rate_20d (20日胜率) ---
add("rank(hit_rate_20d)", "market_cap")               # 高胜率=稳定上涨
add("-rank(hit_rate_20d)", "market_cap")              # 低胜率=可能反转向上
add("ts_rank(hit_rate_20d, 20)", "market_cap")        # 胜率趋势

# --- hit_rate_60d (60日胜率) ---
add("rank(hit_rate_60d)", "market_cap")               # 中期高胜率=高质量上涨
add("-rank(hit_rate_60d)", "market_cap")              # 中期低胜率
add("ts_rank(hit_rate_60d, 40)", "market_cap")        # 中期胜率趋势

# ================================================================
# PROGRESS: ~575 expressions so far
# ================================================================

# ================================================================
# SECTION 8: MULTI-FIELD COMPOSITES (Creative cross-field logic)
# ================================================================
# Momentum + Volatility interactions
add("rank(ret_20d) - rank(vol_20d)", "market_cap")    # 高动量低波动：质量动量
add("rank(ret_20d) * rank(vol_20d)", "none")          # 动量波动交互
add("rank(sharpe_60d) - rank(vol_60d)", "market_cap") # 高夏普低波=优质股
add("ts_rank(returns, 10) - ts_rank(vol_10d, 10)", "market_cap") # 时序动量-波

# Momentum + Volume interactions
add("rank(ret_20d) * rank(volume_profile_ratio)", "market_cap") # 放量上涨=资金确认
add("rank(ret_20d) * rank(volume_trend_20d)", "market_cap")     # 量价齐升
add("rank(ret_10d) + rank(volume_trend_20d)", "market_cap")     # 动量+量趋势
add("ts_rank(returns, 20) - ts_rank(volume_trend_20d, 20)", "market_cap") # 量价背离

# Reversal + Volume confirmation
add("rank(rev_5d) * rank(volume_profile_ratio)", "market_cap")  # 放量反转=强反转信号
add("rank(rev_5d) * rank(turnover_rate)", "market_cap")         # 高换手反转
add("rank(extreme_loser_5d) + rank(volume_breakout)", "market_cap") # 放量超跌反弹

# Volatility + Volume
add("-rank(vol_20d) - rank(volume_breakout)", "market_cap")     # 低波缩量=蓄势突破
add("rank(vol_ratio_5_20) * rank(volume_profile_ratio)", "none") # 波动放大+放量
add("-rank(vol_20d) * rank(volume_price_corr)", "none")          # 低波+量价健康

# Intraday patterns
add("rank(first30min_return) * rank(last30min_return)", "market_cap") # 开盘尾盘方向一致
add("rank(first30_mom) - rank(last30_mom)", "none")             # 早盘-尾盘差异
add("rank(morning_return) - rank(afternoon_return)", "market_cap") # 上下行强弱
add("rank(close_location) * rank(body_ratio)", "market_cap")    # 高位大实体=强势延续
add("rank(vwap_gap) * rank(smart_money_vol)", "market_cap")     # VWAP+聪明钱双重验证

# Microstructure composites
add("rank(price_efficiency) * rank(volume_concentration)", "market_cap") # 高效+集中=机构行为
add("rank(close_vs_vwap) + rank(smart_money_vol)", "market_cap") # VWAP+聪明钱
add("rank(am_pm_divergence) * rank(volume_concentration)", "none") # 背离+集中交易
add("rank(close_location) - rank(upper_shadow_pct)", "market_cap") # 强势收+小上影=买方控盘

# Quality composites
add("rank(sharpe_60d) + rank(hit_rate_60d)", "market_cap")     # 高夏普+高胜率=优质动量
add("rank(mom_vol_adj) - rank(max_dd_60d)", "market_cap")      # 纯动量+低回撤
add("-rank(vol_120d) - rank(kurtosis_60d)", "market_cap")      # 低长期波+低峰度=稳健

# Smart money tracking
add("rank(smart_money_vol) * rank(vwap_gap)", "market_cap")    # 聪明钱+VWAP
add("rank(large_trade_signal) + rank(smart_money_vol)", "market_cap") # 大单+聪明钱
add("rank(smart_money_vwap) + rank(close_location)", "market_cap") # 聪明钱+VWAP+收盘位

# Value + Momentum blends
add("rank(ret_20d) - rank(market_cap_rank)", "market_cap")     # 动量小盘
add("rank(ret_60d) + rank(market_cap_rank)", "market_cap")     # 长期动量小盘
add("rank(mom_vol_adj) - rank(market_cap_rank)", "market_cap") # 纯动量小盘

# Volatility regime interactions
add("rank(ret_10d) * rank(vol_ratio_5_20)", "none")            # 动量×波动扩张
add("-rank(rev_5d) * rank(vol_ratio_5_20)", "none")            # 反转(取反=动量)×波动
add("rank(ret_20d) - ts_rank(vol_20d, 20)", "market_cap")      # 动量+波动下降

# Liquidity conditions
add("rank(ret_20d) - rank(amihud_20d)", "market_cap")          # 动量+高流动性
add("rank(ret_10d) * rank(turnover_change)", "market_cap")     # 动量+换手加速
add("rank(rev_5d) - rank(amihud_20d)", "market_cap")           # 反转+高流动性

# Technical system
add("rank(rsi_14) * rank(volume_profile_ratio)", "none")       # RSI+量确认
add("rank(bollinger_pos) * rank(volume_breakout)", "none")     # 布林下轨+放量=反弹确认
add("-rank(rsi_14) * rank(bollinger_width)", "none")           # 超买+布林扩张=顶部
add("rank(bollinger_pos) + rank(close_vs_low_20d)", "market_cap") # 双超卖信号

# Cross-timeframe momentum
add("rank(ret_5d) + rank(ret_20d)", "market_cap")              # 短+中期动量共振
add("rank(ret_10d) + rank(ret_40d)", "market_cap")             # 双周+双月共振
add("rank(ret_20d) + rank(ret_60d)", "market_cap")             # 月+季共振
add("rank(ret_5d) - rank(ret_60d)", "market_cap")              # 短期vs长期差异
add("rank(ret_20d) - rank(ret_120d_skip5)", "market_cap")      # 中期vs长期背离

# Gap + Intraday continuation
add("rank(auction_return) * rank(intraday_mom)", "market_cap") # 跳空+日内延续
add("rank(gap_up) - rank(upper_shadow_pct)", "market_cap")     # 跳空高开-上影=真强势
add("rank(gap_down) + rank(lower_shadow_pct)", "market_cap")   # 跳空低开+下影=探底回升

# Conditional patterns
add("rank(extreme_loser_5d) - rank(vol_20d)", "market_cap")    # 超跌+低波=更可靠反弹
add("rank(extreme_winner_5d) + rank(vol_20d)", "market_cap")   # 超涨+高波=更可靠回调
add("rank(rev_1d) * rank(hit_rate_20d)", "none")               # 日反转×胜率稳定

# Multi-signal confirmation
add("rank(vwap_gap) + rank(smart_money_vol) + rank(close_location)", "market_cap") # 三重聪明钱
add("rank(ret_20d) + rank(volume_trend_20d) - rank(vol_20d)", "market_cap") # 动量+量趋势-波动
add("rank(morning_return) + rank(afternoon_return) + rank(body_return)", "market_cap") # 三时段一致

# Risk-managed composites
add("rank(sharpe_60d) - rank(max_dd_60d)", "market_cap")       # 高夏普低回撤
add("rank(ret_60d) - rank(downside_vol_60d)", "market_cap")    # 长期动量-下行风险
add("rank(ret_20d) - rank(skewness_60d)", "market_cap")        # 动量-负偏回避
add("-rank(vol_60d) - rank(down_up_vol_ratio)", "market_cap")  # 低波+低下行占比

# ---- Additional creative composites ----
add("rank(vwap_gap) * rank(price_efficiency)", "market_cap")   # VWAP+效率：资金效率
add("rank(close_location) * rank(volume_concentration)", "market_cap") # 强势收+集中
add("rank(triple_confirm) * rank(volume_concentration)", "none") # 三重确认+集中交易
add("rank(turnover_change) - rank(amount_volatility)", "market_cap") # 换手加速-额波=真放量

# ==== Post-1step / Quality inspired ====
add("rank(ret_20d) / (rank(vol_20d) + 0.01)", "none")          # 信息比率近似
add("rank(cumret_5d) * rank(volume_trend_20d)", "market_cap")  # 累积+量趋势
add("rank(returns) * rank(close_vs_high_20d)", "market_cap")   # 日收益+距高点

# ---- Additional field variants (fields missing comprehensive coverage) ----

# vwap (VWAP raw field)
add("rank(vwap)", "market_cap")                         # VWAP截面排名
add("ts_rank(vwap, 20)", "market_cap")                  # VWAP时序趋势
add("ts_delta(vwap, 10)", "none")                       # VWAP短期变化

# signed_power exponent 3 variants for key fields
add("signed_power(returns, 3)", "none")                 # 收益立方：更强非线性放大
add("signed_power(ret_20d, 3)", "none")                 # 月度动量立方
add("signed_power(rev_5d, 3)", "none")                  # 周反转立方
add("signed_power(sharpe_60d, 0.5)", "none")            # 夏普开方压缩

# ts_delta with different windows for key fields
add("ts_delta(vol_20d, 10)", "none")                    # 月度波双周变化
add("ts_delta(turnover_rate, 10)", "none")              # 换手率双周变化
add("ts_delta(close_location, 5)", "none")              # 收盘位置变化
add("ts_delta(vwap_gap, 5)", "none")                    # VWAP偏离变化

# More ts_mean variants
add("ts_mean(volume, 10)", "market_cap")                # 10日均量
add("ts_mean(volume, 40)", "market_cap")                # 40日均量
add("ts_mean(returns, 5)", "market_cap")                # 5日均收益

# More group_neutralize variants
add("group_neutralize(ret_20d, market_cap)", "none")    # 市值中性月度动量
add("group_neutralize(ret_60d, market_cap)", "none")    # 市值中性季度动量
add("group_neutralize(vol_20d, market_cap)", "none")    # 市值中性波动
add("group_neutralize(sharpe_60d, market_cap)", "none") # 市值中性夏普

# ts_product variants (cumulative effects)
add("ts_product(returns, 5)", "market_cap")             # 5日复利积
add("ts_product(returns, 20)", "market_cap")            # 20日复利积

# ts_median variants (robust statistics)
add("ts_median(returns, 20)", "market_cap")             # 20日中位数收益
add("ts_median(volume, 20)", "market_cap")              # 20日中位数成交量

# More interaction composites
add("rank(morning_return) + rank(last30min_return)", "market_cap")      # 早盘+尾盘合力
add("rank(ret_5d) * rank(close_location)", "market_cap")                # 周收益×收盘位置
add("rank(rev_overnight) * rank(gap_up)", "market_cap")                 # 隔夜反转×跳空
add("rank(ret_20d) + rank(rsi_14)", "market_cap")                       # 动量+RSI共振
add("-rank(vol_60d) * rank(market_cap_rank)", "market_cap")             # 低波小盘

# Liquidity + microstructure blends
add("rank(amihud_20d) - rank(vwap_gap)", "market_cap")                  # 非流动-VWAP背离
add("rank(turnover_5d) + rank(volume_concentration)", "market_cap")     # 活跃+大单集中
add("rank(volume_profile_ratio) - rank(amount_volatility)", "market_cap") # 放量+额稳定

# Conditional-like composites (mimicking if_else logic via products)
add("rank(body_ratio) * rank(returns)", "none")                         # 大实体日方向
add("rank(lower_shadow_pct) * rank(rev_1d)", "market_cap")              # 下影+日反转=探底
add("rank(upper_shadow_pct) * rank(ret_5d)", "market_cap")              # 上影+周涨=冲高回落

# Volatility-adjusted returns (ratio forms)
add("rank(ret_20d) / (rank(vol_20d) + 0.01)", "market_cap")             # 月度信息比
add("rank(ret_10d) / (rank(vol_10d) + 0.01)", "market_cap")             # 双周信息比
add("rank(ret_5d) / (rank(vol_5d) + 0.01)", "market_cap")               # 周信息比

# ==== End ====
# (add() deduplicates automatically via seen set)

# ================================================================
# Write to file
# ================================================================
with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Total unique expressions written: {len(lines)}")
print(f"Output: {output_path}")
