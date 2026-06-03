ROUND7 = [
    # === Reversal mid windows ===
    ("rank(ts_delta(close,16))", "market_cap", "16日反转"),
    ("rank(ts_delta(close,17))", "market_cap", "17日反转"),
    ("rank(ts_delta(close,18))", "market_cap", "18日反转"),
    ("rank(ts_delta(close,19))", "market_cap", "19日反转"),
    ("rank(ts_delta(close,21))", "market_cap", "21日反转"),
    ("rank(ts_delta(close,22))", "market_cap", "22日反转"),
    ("rank(ts_delta(close,23))", "market_cap", "23日反转"),
    ("rank(ts_delta(close,24))", "market_cap", "24日反转"),

    # === Momentum mid windows ===
    ("-rank(ts_delta(close,26))", "market_cap", "26日动量"),
    ("-rank(ts_delta(close,27))", "market_cap", "27日动量"),
    ("-rank(ts_delta(close,29))", "market_cap", "29日动量"),
    ("-rank(ts_delta(close,33))", "market_cap", "33日动量"),
    ("-rank(ts_delta(close,34))", "market_cap", "34日动量"),
    ("-rank(ts_delta(close,36))", "market_cap", "36日动量"),
    ("-rank(ts_delta(close,38))", "market_cap", "38日动量"),
    ("-rank(ts_delta(close,42))", "market_cap", "42日动量"),
    ("-rank(ts_delta(close,48))", "market_cap", "48日动量"),
    ("-rank(ts_delta(close,52))", "market_cap", "52日动量"),
    ("-rank(ts_delta(close,58))", "market_cap", "58日动量"),
    ("-rank(ts_delta(close,85))", "market_cap", "85日动量"),
    ("-rank(ts_delta(close,95))", "market_cap", "95日动量"),
    ("-rank(ts_delta(close,110))", "market_cap", "110日动量"),
    ("-rank(ts_delta(close,140))", "market_cap", "140日动量"),
    ("-rank(ts_delta(close,160))", "market_cap", "160日动量"),
    ("-rank(ts_delta(close,220))", "market_cap", "220日动量"),

    # === Cumulative returns ===
    ("-rank(ts_sum(close/open-1,7))", "market_cap", "7日累积动量"),
    ("rank(ts_sum(close/open-1,7))", "market_cap", "7日累积反转"),
    ("-rank(ts_sum(close/open-1,11))", "market_cap", "11日累积动量"),
    ("rank(ts_sum(close/open-1,11))", "market_cap", "11日累积反转"),
]
