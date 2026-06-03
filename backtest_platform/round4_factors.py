# Round 4 — more factor dimensions
ROUND4 = [
    # === Momentum with gap-adjusted open ===
    ("-rank(ts_delta(close,15))", "market_cap", "15日动量"),
    ("-rank(ts_delta(close,50))", "market_cap", "50日动量"),
    ("-rank(ts_delta(close,100))", "market_cap", "100日动量"),
    ("-rank(ts_delta(close,150))", "market_cap", "150日动量"),

    # === Very short-term patterns ===
    ("rank(ts_delta(close/open-1,1))", "market_cap", "日收益一阶差分"),
    ("-rank(ts_delta(close/open-1,3))", "market_cap", "3日收益动量"),
    ("-rank(ts_delta(close/open-1,7))", "market_cap", "7日收益动量"),
    ("-rank(ts_delta(close/open-1,15))", "market_cap", "15日收益动量"),

    # === Reversal variants ===
    ("rank(ts_delta(close,3))", "market_cap", "3日反转"),
    ("rank(ts_delta(close,7))", "market_cap", "7日反转"),
    ("rank(ts_delta(close,15))", "market_cap", "15日反转"),

    # === Volatility adjusted returns ===
    ("-rank(ts_mean(close/open-1,3)/ts_std(close/open-1,15))", "market_cap", "3日收益/15日波"),
    ("-rank(ts_mean(close/open-1,7)/ts_std(close/open-1,30))", "market_cap", "7日收益/30日波"),
    ("-rank(ts_mean(close/open-1,15)/ts_std(close/open-1,60))", "market_cap", "15日收益/60日波"),

    # === Volume momentum ===
    ("-rank(ts_delta(volume,10))", "market_cap", "10日量增"),
    ("-rank(ts_delta(volume,20))", "market_cap", "20日量增"),
    ("rank(ts_delta(volume,15))", "market_cap", "15日量反转"),

    # === Price acceleration (second derivative) ===
    ("-rank(ts_delta(ts_delta(close,5),5))", "market_cap", "动量加速度"),
    ("rank(ts_delta(ts_delta(close,5),5))", "market_cap", "动量加速度反转"),

    # === Symmetric range position (close in daily range) ===
    ("-rank((close-ts_min(low,5))/(ts_max(high,5)-ts_min(low,5)+0.001))", "market_cap", "5日区间内收盘位置"),

    # === Decay linear variants ===
    ("-rank(ts_decay_linear(close/open-1,3))", "market_cap", "3日衰减动量"),
    ("-rank(ts_decay_linear(close/open-1,7))", "market_cap", "7日衰减动量"),
    ("-rank(ts_decay_linear(close/open-1,15))", "market_cap", "15日衰减动量"),
]
