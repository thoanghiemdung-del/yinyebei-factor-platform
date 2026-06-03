ROUND11 = [
    # === Close strength: where close is in day's range ===
    ("-rank((2*close-high-low)/(high-low+0.001))", "market_cap", "收盘平衡点：+1=收高,-1=收低"),

    # === Intraday reversal potential ===
    ("-rank((open-low)/(high-low+0.001))", "market_cap", "开盘位置：低开=买入机会"),
    ("rank((open-low)/(high-low+0.001))", "market_cap", "开盘位置反转"),

    # === Volume at extremes ===
    ("-rank(volume/(ts_max(volume,20)+0.001))", "market_cap", "量创新高：20日最高量=爆发"),

    # === Gap and volume confirmation ===
    ("-rank((open-preclose)/preclose*volume/ts_mean(volume,10))", "market_cap", "跳空×量确认"),

    # === Close consistency ===
    ("-rank(ts_mean((close-open)/(open+0.001),8))", "market_cap", "8日均盘中收益"),
    ("-rank(ts_mean((close-open)/(open+0.001),12))", "market_cap", "12日均盘中收益"),
    ("-rank(ts_mean((close-open)/(open+0.001),18))", "market_cap", "18日均盘中收益"),
    ("-rank(ts_mean((close-open)/(open+0.001),25))", "market_cap", "25日均盘中收益"),

    # === Volatility regime change ===
    ("-rank(ts_std((close-open)/open,20)/ts_std((close-open)/open,120))", "market_cap", "中期/长期波比"),
    ("-rank(ts_std((close-open)/open,10)/ts_std((close-open)/open,40))", "market_cap", "短期/中期波比"),

    # === Liquidity: turnover proxy (volume relative to price) ===
    ("-rank(volume/(close+0.001))", "market_cap", "换手率代理：高换手=关注"),
    ("rank(volume/(close+0.001))", "market_cap", "换手率反转"),

    # === Price path momentum: acceleration sign ===
    ("-rank(ts_delta(close,5)*ts_delta(close,10))", "market_cap", "5×10日动量和：同向共振"),

    # === Amplitude normalized by price level ===
    ("-rank((high-low)/close)", "market_cap", "相对振幅：高波=高风险"),

    # === Trending vs choppy: high-low range trend ===
    ("-rank(ts_mean(high-low,10)/ts_mean(high-low,30))", "market_cap", "振幅趋势：扩张=趋势市场"),
    ("rank(ts_mean(high-low,10)/ts_mean(high-low,30))", "market_cap", "振幅趋势反转"),

    # === Range position in historical context ===
    ("-rank((high-low)/ts_max(high-low,20))", "market_cap", "振幅创新高：极端波动"),
    ("rank((high-low)/ts_max(high-low,20))", "market_cap", "振幅极值反转"),

    # === Overnight vs intraday performance split ===
    ("-rank((close-open)/open-(open-preclose)/preclose)", "market_cap", "盘中-隔夜差：驱动切换"),
    ("rank((close-open)/open-(open-preclose)/preclose)", "market_cap", "驱动切换反转"),

    # === Momentum per unit of daily range ===
    ("-rank(ts_delta(close,5)/ts_sum(high-low,5))", "market_cap", "单位振幅动量：效率比"),

    # === Volume variability ===
    ("rank(ts_std(volume,10)/ts_mean(volume,10))", "market_cap", "量变系数反转：量不稳=风险"),
]
