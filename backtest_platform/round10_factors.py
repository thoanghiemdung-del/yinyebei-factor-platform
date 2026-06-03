ROUND10 = [
    # === Gap + intraday interaction ===
    ("-rank((close-preclose)/(high-low+0.001))", "market_cap", "隔夜收益/日振幅：跳空有效性"),

    # === Open weakness vs close strength ===
    ("-rank((close-open)/(open-preclose+0.001))", "market_cap", "盘中/跳空比：盘中纠正"),

    # === Volume efficiency: how much return per volume ===
    ("-rank(ts_delta(close,5)/ts_sum(volume,5))", "market_cap", "单位成交量价格变动"),

    # === Volatility compression → expansion signal ===
    ("-rank(ts_std((close-open)/open,5)/ts_std((close-open)/open,60))", "market_cap", "短期/长期波比：波动爆发前兆"),

    # === Return concentration: skew proxy ===
    ("-rank(ts_mean((close-open)/open,5)/ts_std((close-open)/open,5))", "market_cap", "5日收益效率（均值/波）"),

    # === Price stability: consecutive days w/ similar close ===
    ("-rank(ts_sum((close-open)/(open+0.001),3)/3)", "market_cap", "3日方向持续性"),

    # === Daily price amplitude ratio ===
    ("rank(ts_std(close,5)/ts_mean(high-low,5))", "market_cap", "收盘波动/日内振幅：过度日内波动"),

    # === Momentum decay: how momentum changes over time ===
    ("-rank(ts_delta(close,5)/5-ts_delta(close,20)/20)", "market_cap", "动量衰减率：近期>远期"),

    # === Range breakout proximity ===
    ("-rank(close/ts_max(high,5)-1)", "market_cap", "距5日最高价距离"),
    ("rank(close/ts_min(low,5)-1)", "market_cap", "距5日最低价反转"),

    # === Dollar volume (volume×close) as liquidity proxy ===
    ("-rank(ts_delta(volume*close,5))", "market_cap", "成交额动量：大额资金流入"),
    ("rank(ts_delta(volume*close,5))", "market_cap", "成交额反转：超额资金流出"),

    # === Trend strength (momentum return relative to volatility) ===
    ("-rank(ts_mean((close-open)/open,10)/ts_std((close-open)/open,30))", "market_cap", "趋势强度：10日收益/30日波"),

    # === Volume persistence ===
    ("-rank(ts_mean(volume,5))", "market_cap", "5日均量：持续关注"),
    ("rank(ts_mean(volume,5))", "market_cap", "均量反转"),

    # === Price closeness to recent high (pullback) ===
    ("rank(ts_max(close,5)/close-1)", "market_cap", "5日高点回落幅度反转"),

    # === High-low convergence/divergence ===
    ("-rank(ts_delta(high-close,5)-ts_delta(close-low,5))", "market_cap", "卖压-买盘差：方向信号"),

    # === Mean daily range normalized momentum ===
    ("-rank(ts_delta(close,10)/ts_mean(high-low,10))", "market_cap", "振幅标准化动量"),

    # === Volume oscillator: fast minus slow ===
    ("-rank(ts_mean(volume,3)-ts_mean(volume,10))", "market_cap", "量震荡：短>长=放量"),
    ("rank(ts_mean(volume,3)-ts_mean(volume,10))", "market_cap", "量震荡反转"),

    # === Gap up persistence ===
    ("-rank(ts_sum((open-preclose)/(preclose+0.001),5))", "market_cap", "5日跳空累积动量"),

    # === Price level relative to Bollinger-like bands ===
    ("-rank((close-ts_mean(close,20))/ts_std(close,20))", "market_cap", "布林带位置动量"),
    ("rank((close-ts_mean(close,20))/ts_std(close,20))", "market_cap", "布林带位置反转"),

    # === Returns smoothness (low variance of daily returns) ===
    ("-rank(ts_std((close-open)/(open+0.001),20))", "market_cap", "20日收益波：平稳=趋势"),
]
