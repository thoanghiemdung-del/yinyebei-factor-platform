ROUND8 = [
    # === Intraday conviction: close position as % of day's range ===
    # Higher close position = buying conviction, likely to continue
    ("-rank((close-low)/(high-low+0.001))", "market_cap", "收盘位置：盘中买入信念"),
    # Low close position = selling pressure exhausted, reversal likely
    ("rank((close-low)/(high-low+0.001))", "market_cap", "收盘位置反转：低位=衰竭反弹"),

    # === Overnight gap persistence ===
    ("-rank((open-preclose)/preclose)", "market_cap", "开盘跳空动量：隔夜信息延续"),
    ("rank((open-preclose)/preclose)", "market_cap", "开盘跳空反转：过度反应回补"),

    # === Gap fill: how much of overnight gap was reversed intraday ===
    ("-rank((close-open)/(open-preclose+0.001))", "market_cap", "跳空填补方向：顺势填补=强趋势"),
    ("rank((close-open)/(open-preclose+0.001))", "market_cap", "跳空填补反转：盘中回补过度"),

    # === Price efficiency: close relative to VWAP proxy (open+high+low+close)/4 ===
    ("-rank(4*close/(open+high+low+close+0.001)-1)", "market_cap", "收盘vs均价：高于均价=买盘主导"),
    ("rank(4*close/(open+high+low+close+0.001)-1)", "market_cap", "收盘vs均价反转：过高=回落"),

    # === Real body ratio: conviction in daily direction ===
    ("-rank((close-open)/(open+0.001))", "market_cap", "日方向强度：大实体=高确信趋势"),

    # === Upper/lower shadow: rejection signals ===
    ("rank((high-close)/(high-low+0.001))", "market_cap", "上影反转：冲高回落=卖压"),
    ("-rank((close-low)/(high-low+0.001))", "market_cap", "下影支撑：探底回升=买盘"),

    # === Range expansion/contraction ===
    ("-rank(ts_delta(high-low,5))", "market_cap", "振幅扩张：波动加剧伴趋势"),
    ("rank(ts_delta(high-low,5))", "market_cap", "振幅收缩反转：平静后爆发"),

    # === Volume-weighted momentum: volume confirms price move ===
    ("-rank(ts_delta(close,5)*ts_delta(volume,5))", "market_cap", "价量同向放大：高确信趋势"),

    # === Price level relative to N-day typical price ===
    ("-rank(close/ts_mean((high+low+close)/3,10)-1)", "market_cap", "vs 10日均典型价趋势"),
    ("rank(close/ts_mean((high+low+close)/3,10)-1)", "market_cap", "vs 10日均典型价反转"),

    # === Directional consistency: % of days in N that closed positive ===
    ("-rank(ts_sum((close>open).astype(float),10)/10)", "market_cap", "10日阳线率：持续高阳线=强势"),
    ("rank(ts_sum((close>open).astype(float),10)/10)", "market_cap", "阳线率反转：过度乐观=回调"),

    # === Asymmetric volatility: upside vol vs downside vol proxy ===
    # high-low captures full range regardless of direction
    ("-rank(ts_std(high-close,10)/ts_std(close-low,10))", "market_cap", "上影波动/下影波动：卖方力量>买方"),
    ("rank(ts_std(high-close,10)/ts_std(close-low,10))", "market_cap", "上/下影波动比反转"),

    # === Close vs open cumulative: total intraday drift ===
    ("-rank(ts_sum((close-open)/open,5))", "market_cap", "5日盘中累积漂移"),

    # === Daily range normalized by close: VIX-like ===
    ("rank((high-low)/close)", "market_cap", "相对振幅反转：高波后低波"),
    ("-rank((high-low)/close)", "market_cap", "相对振幅动量"),

    # === Volume trend acceleration ===
    ("-rank(ts_delta(ts_delta(volume,5),5))", "market_cap", "量加速度：放量加速=持续"),
    ("rank(ts_delta(ts_delta(volume,5),5))", "market_cap", "量加速度反转"),

    # === Price-volatility ratio: reward per unit risk ===
    ("-rank(ts_delta(close,10)/(high-low)/close*100)", "market_cap", "经振幅调整的动量"),

    # === Consecutive vs reversal pattern ===
    ("-rank(ts_delta(close,2)*ts_delta(close,1))", "market_cap", "2日×1日持续信号"),
]
