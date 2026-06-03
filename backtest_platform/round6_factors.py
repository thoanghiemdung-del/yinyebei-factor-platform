ROUND6 = [
    # === More momentum gaps ===
    ("-rank(ts_delta(close,18))", "market_cap", "18日动量"),
    ("-rank(ts_delta(close,22))", "market_cap", "22日动量"),
    ("-rank(ts_delta(close,28))", "market_cap", "28日动量"),
    ("-rank(ts_delta(close,32))", "market_cap", "32日动量"),
    ("-rank(ts_delta(close,75))", "market_cap", "75日动量"),
    ("-rank(ts_delta(close,130))", "market_cap", "130日动量"),
    ("-rank(ts_delta(close,180))", "market_cap", "180日动量"),

    # === More reversals ===
    ("rank(ts_delta(close,11))", "market_cap", "11日反转"),
    ("rank(ts_delta(close,13))", "market_cap", "13日反转"),
    ("rank(ts_delta(close,14))", "market_cap", "14日反转"),

    # === MA reversals (more windows) ===
    ("rank(close/ts_mean(close,3)-1)", "market_cap", "3日均线反转"),
    ("rank(close/ts_mean(close,7)-1)", "market_cap", "7日均线反转"),
    ("rank(close/ts_mean(close,12)-1)", "market_cap", "12日均线反转"),
    ("rank(close/ts_mean(close,25)-1)", "market_cap", "25日均线反转"),
    ("rank(close/ts_mean(close,50)-1)", "market_cap", "50日均线反转"),
    ("rank(close/ts_mean(close,90)-1)", "market_cap", "90日均线反转"),

    # === MA momentum (more windows) ===
    ("-rank(close/ts_mean(close,3)-1)", "market_cap", "3日均线动量"),
    ("-rank(close/ts_mean(close,7)-1)", "market_cap", "7日均线动量"),
    ("-rank(close/ts_mean(close,12)-1)", "market_cap", "12日均线动量"),
    ("-rank(close/ts_mean(close,25)-1)", "market_cap", "25日均线动量"),
    ("-rank(close/ts_mean(close,50)-1)", "market_cap", "50日均线动量"),
    ("-rank(close/ts_mean(close,90)-1)", "market_cap", "90日均线动量"),

    # === Cumulative returns short windows ===
    ("-rank(ts_sum(close/open-1,4))", "market_cap", "4日累积动量"),
    ("-rank(ts_sum(close/open-1,6))", "market_cap", "6日累积动量"),
    ("-rank(ts_sum(close/open-1,9))", "market_cap", "9日累积动量"),
    ("rank(ts_sum(close/open-1,4))", "market_cap", "4日累积反转"),
    ("rank(ts_sum(close/open-1,6))", "market_cap", "6日累积反转"),
    ("rank(ts_sum(close/open-1,9))", "market_cap", "9日累积反转"),
]
