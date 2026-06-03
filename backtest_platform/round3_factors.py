# Round 3 — more economic dimensions
ROUND3 = [
    # === Open-Close relationship (intraday direction strength) ===
    ("-rank((close-open)/(high-low+0.001))", "market_cap", "盘中方向强度"),
    ("rank((open-close)/(high-low+0.001))", "market_cap", "盘中方向反转"),

    # === Gap + intraday interaction ===
    ("-rank((close-preclose)/preclose+(close-open)/open)", "market_cap", "隔夜+盘中同向"),
    ("rank((close-preclose)/preclose+(close-open)/open)", "market_cap", "隔夜+盘中综合反转"),

    # === High-low range (volatility signal) ===
    ("-rank((high-low)/close)", "market_cap", "日振幅：高波动=风险"),
    ("rank((high-low)/close)", "market_cap", "日振幅反转：低波动溢价"),
    ("-rank(ts_mean((high-low)/close,5))", "market_cap", "5日均振幅"),
    ("-rank(ts_mean((high-low)/close,20))", "market_cap", "20日均振幅"),

    # === Turnover / volume ratio (money flow) ===
    ("-rank(ts_mean(volume,5)/ts_mean(volume,10))", "market_cap", "5日/10日量比加速"),
    ("-rank(ts_mean(volume,10)/ts_mean(volume,30))", "market_cap", "10日/30日量比"),
    ("rank(ts_mean(volume,3)/ts_mean(volume,60))", "market_cap", "短期/长期量比反转"),

    # === Price position in range ===
    ("-rank((close-ts_min(close,20))/(ts_max(close,20)-ts_min(close,20)+0.001))", "market_cap", "20日区间位置：高位=强势"),
    ("rank((close-ts_min(close,20))/(ts_max(close,20)-ts_min(close,20)+0.001))", "market_cap", "20日区间位置反转"),
    ("-rank((close-ts_min(close,10))/(ts_max(close,10)-ts_min(close,10)+0.001))", "market_cap", "10日区间位置"),
    ("-rank((close-ts_min(close,60))/(ts_max(close,60)-ts_min(close,60)+0.001))", "market_cap", "60日区间位置"),

    # === Consecutive direction (trend persistence) ===
    ("-rank(ts_sum(close/open-1,3))", "market_cap", "3日方向延续"),
    ("-rank(ts_sum(close/open-1,15))", "market_cap", "15日方向延续"),
    ("rank(ts_sum(close/open-1,3))", "market_cap", "3日方向反转"),

    # === Non-linear momentum (signed power variants) ===
    ("-rank(signed_power(ts_delta(close,10),2))", "market_cap", "10日动量平方"),
    ("-rank(signed_power(ts_delta(close,3),3))", "market_cap", "3日动量立方"),
    ("-rank(signed_power(ts_delta(close,60),1.5))", "market_cap", "60日动量1.5次方"),

    # === Momentum smoothed (ts_mean of momentum) ===
    ("-rank(ts_mean(ts_delta(close,1),3))", "market_cap", "3日均日动量"),
    ("-rank(ts_mean(ts_delta(close,1),15))", "market_cap", "15日均日动量"),

    # === Skew-like (up/down asymmetry proxy) ===
    ("-rank(ts_mean(close/open-1,5)/ts_mean((high-close)/(high-low+0.001),5))", "market_cap", "收益/上影比"),

    # === Price vs volume decoupling ===
    ("-rank(ts_delta(close,20))", "market_cap", "20日动量"),
    ("-rank(ts_delta(close,40))", "market_cap", "40日动量"),
    ("-rank(ts_delta(close,80))", "market_cap", "80日动量"),

    # === Volatility trend (vol of vol) ===
    ("rank(ts_std(close/open-1,10)/ts_std(close/open-1,60))", "market_cap", "波动率爆发比"),

    # === Close vs open gap accumulation ===
    ("-rank(ts_sum((close-open)/open,3))", "market_cap", "3日盘中累积动量"),
    ("-rank(ts_sum((close-open)/open,8))", "market_cap", "8日盘中累积动量"),

    # === Mean reversion speed (fast reversal) ===
    ("rank(ts_delta(close/open-1,1))", "market_cap", "日收益一阶差分反转"),
    ("rank(ts_delta(close/open-1,2))", "market_cap", "2日日收益差分反转"),
]
