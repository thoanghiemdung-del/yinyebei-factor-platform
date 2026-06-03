ROUND9 = [
    # === Upper shadow: sellers rejected at high ===
    ("rank((high-open)/(high-low+0.001))", "market_cap", "开盘后冲高反转：高位被拒"),
    ("-rank((high-open)/(high-low+0.001))", "market_cap", "开盘后冲高动量：突破阻力"),

    # === Lower shadow: buyers stepped in at low ===
    ("rank((open-low)/(high-low+0.001))", "market_cap", "探底韧性：低位支撑力"),
    ("-rank((open-low)/(high-low+0.001))", "market_cap", "探底弱反弹：继续下跌"),

    # === Gap size normalized by typical range ===
    ("-rank((open-preclose)/ts_mean(high-low,10))", "market_cap", "标准跳空强度：跳空/10日均振幅"),

    # === Price oscillation: close alternation ===
    ("-rank(ts_mean((close-open)/open,5))", "market_cap", "5日平均盘中收益动量"),

    # === Range contraction then expansion ===
    ("-rank(ts_delta(high-low,20)/ts_mean(high-low,20))", "market_cap", "振幅变动率：扩张伴趋势"),

    # === Volume surge relative to own history ===
    ("-rank(volume/ts_mean(volume,5))", "market_cap", "相对5日均量：放量=关注"),
    ("rank(volume/ts_mean(volume,5))", "market_cap", "相对量反转：放量后衰竭"),

    # === Daily return standardized by recent volatility ===
    ("-rank((close-open)/open/ts_std((close-open)/open,20))", "market_cap", "标准日内强度：大偏离=信号"),

    # === Volume surge magnitude (deviation from mean) ===
    ("-rank((volume-ts_mean(volume,20))/ts_std(volume,20))", "market_cap", "量Z分数：异常量伴趋势"),
    ("rank((volume-ts_mean(volume,20))/ts_std(volume,20))", "market_cap", "异常量反转"),

    # === Price range relative to close: risk indicator ===
    ("-rank((high-low)/ts_mean(high-low,20))", "market_cap", "相对20日振幅：高波动日"),
    ("rank((high-low)/ts_mean(high-low,20))", "market_cap", "相对振幅反转"),

    # === Distance from 52-week (250-day) high and low ===
    ("-rank(close/ts_max(close,250)-1)", "market_cap", "距年高距离动量"),

    # === Volume trend strength ===
    ("-rank(ts_mean(volume,10)/ts_mean(volume,30))", "market_cap", "量趋势：10日/30日均量比"),
    ("rank(ts_mean(volume,10)/ts_mean(volume,30))", "market_cap", "量趋势反转"),

    # === Closing strength vs opening ===
    ("-rank(ts_mean((close-open)/(open+0.001),5))", "market_cap", "5日均盘中方向"),

    # === Price path convexity: cumulative vs single-period ===
    ("-rank(ts_delta(close,10)-5*ts_delta(close,2))", "market_cap", "路径凸性：累积vs线性"),
    ("rank(ts_delta(close,10)-5*ts_delta(close,2))", "market_cap", "路径凸性反转"),

    # === Consecutive direction count ===
    ("-rank(ts_sum((close-open)/(open+0.001),3))", "market_cap", "3日方向延续"),

    # === Short-term vs long-term vol ===
    ("rank(ts_std((close-open)/open,5)/ts_std((close-open)/open,30))", "market_cap", "波动率期限结构：短期/长期"),
    ("-rank(ts_std((close-open)/open,5)/ts_std((close-open)/open,30))", "market_cap", "波动率期限结构反转"),

    # === Volume concentration: how much volume in last N days ===
    ("-rank(ts_sum(volume,5)/ts_sum(volume,20))", "market_cap", "5日量集中度"),
    ("rank(ts_sum(volume,5)/ts_sum(volume,20))", "market_cap", "量集中度反转"),

    # === Price velocity change ===
    ("-rank(ts_delta(close,3)/3-ts_delta(close,15)/15)", "market_cap", "速度差：近期速度-远期速度"),
    ("rank(ts_delta(close,3)/3-ts_delta(close,15)/15)", "market_cap", "速度差反转"),
]
