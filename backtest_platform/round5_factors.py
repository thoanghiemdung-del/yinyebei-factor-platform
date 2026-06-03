ROUND5 = [
    # === More momentum windows (filling gaps) ===
    ("-rank(ts_delta(close,25))", "market_cap", "25日动量"),
    ("-rank(ts_delta(close,35))", "market_cap", "35日动量"),
    ("-rank(ts_delta(close,45))", "market_cap", "45日动量"),
    ("-rank(ts_delta(close,55))", "market_cap", "55日动量"),
    ("-rank(ts_delta(close,70))", "market_cap", "70日动量"),
    ("-rank(ts_delta(close,200))", "market_cap", "200日动量"),

    # === More reversal windows ===
    ("rank(ts_delta(close,4))", "market_cap", "4日反转"),
    ("rank(ts_delta(close,6))", "market_cap", "6日反转"),
    ("rank(ts_delta(close,8))", "market_cap", "8日反转"),
    ("rank(ts_delta(close,9))", "market_cap", "9日反转"),
    ("rank(ts_delta(close,12))", "market_cap", "12日反转"),

    # === Cumulative returns ===
    ("-rank(ts_sum(close/open-1,8))", "market_cap", "8日累积动量"),
    ("-rank(ts_sum(close/open-1,12))", "market_cap", "12日累积动量"),
    ("rank(ts_sum(close/open-1,8))", "market_cap", "8日累积反转"),
    ("rank(ts_sum(close/open-1,12))", "market_cap", "12日累积反转"),

    # === Volatility windows ===
    ("-rank(ts_std(close/open-1,8))", "market_cap", "8日波动率反转"),
    ("-rank(ts_std(close/open-1,15))", "market_cap", "15日波动率反转"),
    ("-rank(ts_std(close/open-1,45))", "market_cap", "45日波动率反转"),
    ("rank(ts_std(close/open-1,8)/ts_std(close/open-1,30))", "market_cap", "8日/30日波动率比"),
    ("rank(ts_std(close/open-1,15)/ts_std(close/open-1,60))", "market_cap", "15日/60日波动率比"),

    # === Decay linear windows ===
    ("-rank(ts_decay_linear(close/open-1,8))", "market_cap", "8日衰减动量"),
    ("-rank(ts_decay_linear(close/open-1,12))", "market_cap", "12日衰减动量"),

    # === Mean reversion to MA ===
    ("rank(close/ts_mean(close,8)-1)", "market_cap", "8日均线偏离反转"),
    ("rank(close/ts_mean(close,15)-1)", "market_cap", "15日均线偏离反转"),
    ("rank(close/ts_mean(close,30)-1)", "market_cap", "30日均线偏离反转"),
    ("rank(close/ts_mean(close,120)-1)", "market_cap", "120日均线偏离反转"),

    # === Momentum + MA combo ===
    ("-rank(close/ts_mean(close,8)-1)", "market_cap", "8日均线偏离动量"),
    ("-rank(close/ts_mean(close,15)-1)", "market_cap", "15日均线偏离动量"),
    ("-rank(close/ts_mean(close,30)-1)", "market_cap", "30日均线偏离动量"),
    ("-rank(close/ts_mean(close,120)-1)", "market_cap", "120日均线偏离动量"),
]
