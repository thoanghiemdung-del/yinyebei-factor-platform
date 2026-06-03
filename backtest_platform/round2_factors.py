# New factor batch — different dimensions from round 1
ROUND2 = [
    # === Gap / Overnight ===
    ("-rank(close/preclose-1)", "market_cap", "隔夜收益动量"),
    ("rank(close/preclose-1)", "market_cap", "隔夜收益反转"),
    ("-rank(open/preclose-1)", "market_cap", "开盘跳空动量"),
    ("rank(open/preclose-1)", "market_cap", "开盘跳空反转"),
    ("-rank((close-open)/(open-preclose+0.001))", "market_cap", "盘中vs跳空比：盘中延续跳空方向"),
    ("rank((open-preclose)/preclose)", "market_cap", "跳空反转：高开回落"),

    # === Intraday patterns ===
    ("-rank((close-open)/(high-low+0.001))", "market_cap", "收盘位置：高位收盘=强势"),
    ("rank((close-open)/(high-low+0.001))", "market_cap", "收盘位置反转：高位=回落"),
    ("-rank(close/(high+0.001))", "market_cap", "收盘/最高比：接近最高=强势"),
    ("rank(close/(low+0.001))", "market_cap", "收盘/最低比反转：过度拉高=回落"),

    # === Price extremes ===
    ("-rank(close/ts_max(close,5)-1)", "market_cap", "距5日高点：短期突破信号"),
    ("-rank(close/ts_max(close,10)-1)", "market_cap", "距10日高点"),
    ("-rank(close/ts_max(close,30)-1)", "market_cap", "距30日高点"),
    ("rank(close/ts_min(close,5)-1)", "market_cap", "距5日低点反转"),
    ("rank(close/ts_min(close,10)-1)", "market_cap", "距10日低点反转"),
    ("rank(close/ts_min(close,30)-1)", "market_cap", "距30日低点反转"),

    # === Multi-timescale momentum convergence ===
    ("-rank(ts_delta(close,5)*ts_delta(close,20))", "market_cap", "5日×20日动量共振"),
    ("-rank(ts_delta(close,10)*ts_delta(close,60))", "market_cap", "10日×60日动量共振"),
    ("-rank(ts_delta(close,5)/ts_std(close/open-1,5))", "market_cap", "5日风险调整动量"),
    ("-rank(ts_delta(close,20)/ts_std(close/open-1,20))", "market_cap", "20日风险调整动量"),

    # === Price path smoothness (low variance = stable trend) ===
    ("-rank(ts_std(ts_delta(close,1),5))", "market_cap", "5日收益波动：不稳定=风险"),
    ("-rank(ts_std(ts_delta(close,1),10))", "market_cap", "10日收益波动"),
    ("-rank(ts_std(ts_delta(close,1),20))", "market_cap", "20日收益波动"),

    # === Volume + price divergence ===
    ("-rank(ts_delta(close,5)/ts_mean(volume,5))", "market_cap", "价量效率：单位成交额的价格变动"),
    ("-rank(ts_delta(close,10)/ts_mean(volume,10))", "market_cap", "10日价量效率"),
    ("rank(ts_delta(close,5)*ts_delta(volume,5))", "market_cap", "价量同向：放量下跌=强反转信号"),

    # === Acceleration (trend change) ===
    ("-rank(ts_delta(close,5)-ts_delta(close,20))", "market_cap", "加速度：短期减长期动量"),
    ("-rank(ts_delta(close,10)-ts_delta(close,60))", "market_cap", "10日减60日加速度"),
    ("rank(ts_delta(close,5)-ts_delta(close,20))", "market_cap", "减速反转：急涨后减速=回调"),
    ("rank(ts_delta(close,3)-ts_delta(close,15))", "market_cap", "3日减15日减速反转"),

    # === Cross-sectional rank stability ===
    ("-rank(ts_mean(ts_delta(close,1),5))", "market_cap", "5日均日收益动量"),
    ("-rank(ts_mean(ts_delta(close,1),10))", "market_cap", "10日均日收益动量"),
    ("-rank(ts_mean(ts_delta(close,1),20))", "market_cap", "20日均日收益动量"),

    # === Asymmetric volatility (downside risk premium) ===
    ("-rank(open/ts_max(open,20))", "market_cap", "开盘价/20日最高开盘：相对低位"),
    ("rank(open/ts_min(open,20))", "market_cap", "开盘价/20日最低开盘反转"),
]
