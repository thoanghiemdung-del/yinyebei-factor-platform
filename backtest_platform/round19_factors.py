ROUND19 = [
    # === Midpoint deviation: close vs (high+low)/2 ===
    ("-rank(2*close/(high+low+0.001)-1)", "market_cap", "收盘偏离中点：>0=强势收高"),
    ("rank(2*close/(high+low+0.001)-1)", "market_cap", "中点偏离反转"),

    # === Asymmetric price movement: high vs low momentum ===
    ("-rank(ts_delta(high,10)/ts_delta(low,10))", "market_cap", "高低动量比：>1=高点抬升快于低点"),
    ("rank(ts_delta(high,10)/ts_delta(low,10))", "market_cap", "高低动量比反转"),

    # === Max/min single-day shock in window ===
    ("-rank(ts_max((close-open)/open,10))", "market_cap", "10日最大单日涨幅动量"),
    ("rank(ts_max((close-open)/open,10))", "market_cap", "最大涨幅反转：过度乐观"),
    ("-rank(ts_min((close-open)/open,20))", "market_cap", "20日最大单日跌幅：极端弱势"),
    ("rank(ts_min((close-open)/open,20))", "market_cap", "最大跌幅反转：恐慌底"),

    # === Trend smoothness: momentum consistency ===
    ("-rank(ts_mean((close-open)/open,20)/ts_std((close-open)/open,20))", "market_cap", "趋势平稳度：高均值/低波=稳定趋势"),

    # === Vol spike: current / recent ===
    ("-rank(ts_std((close-open)/open,5)/ts_std((close-open)/open,60))", "market_cap", "波动率突变：短期波/长期波"),

    # === Close position relative to open-high-low center ===
    ("-rank((3*close-high-low-open)/(high-low+0.001))", "market_cap", "收盘在四价中的位置"),

    # === Volume-weighted intraday return ===
    ("-rank(volume*(close-open)/(open+0.001))", "market_cap", "量加权盘中收益"),
    ("rank(volume*(close-open)/(open+0.001))", "market_cap", "量加权盘中反转"),

    # === Price change per unit of volume ===
    ("-rank(ts_delta(close,5)/ts_sum(volume,5))", "market_cap", "单位成交量价格效率"),
    ("rank(ts_delta(close,5)/ts_sum(volume,5))", "market_cap", "量效率反转"),

    # === Gap relative to daily range (gap quality) ===
    ("-rank((open-preclose)/(high-low+0.001))", "market_cap", "跳空/振幅：跳空质量"),

    # === Trend acceleration smoothness ===
    ("-rank(ts_mean(ts_delta(close,1),10)/ts_std(ts_delta(close,1),20))", "market_cap", "动量平滑度：稳动量>跳动量"),

    # === Close relative to weighted price ===
    ("-rank(close/((2*close+high+low)/4+0.001)-1)", "market_cap", "收盘vs加权价：收高=买方主导"),
]
