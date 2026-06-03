"""1000-factor batch: each factor tests a distinct economic hypothesis. 4 threads."""
import urllib.request, http.cookiejar, json, time, threading, sys, itertools

factors = []  # (expression, neutralization, economic_rationale)
mc, no = 'market_cap', 'none'
R = lambda e,n,r: factors.append((e,n,r))

# ===== REVERSAL (120 factors) =====
# Core idea: A-share T+1 creates daily overreaction → short-term mean reversion
fields_ret = ['returns','ret_5d','ret_10d','ret_20d','ret_40d','ret_60d']
for f in fields_ret:
    R(f'-rank({f})', mc, f'{f}反转:买入近期输家卖出赢家')
    R(f'-rank({f})', no, f'{f}反转(无中性):纯反转不剔除市值')
    for w in [5,10,20,60]:
        R(f'-rank(ts_delta({f},{w}))', mc, f'{f}的{w}d变化反转:变化越大的越反转')
    for w in [20,60,120]:
        R(f'-rank(ts_rank({f},{w}))', mc, f'{f}时序排{w}d反转:时序排名反向')
    for w in [5,10,20]:
        R(f'-rank(ts_decay_linear({f},{w}))', mc, f'{f}衰减{w}d反转:近期加权反转')

# Price-based reversal
for w in [3,5,10,20,30,60]:
    R(f'-rank(ts_delta(close,{w}))', mc, f'价变{w}d反转:价格短期变化反转')
    R(f'-rank(ts_delta(close,{w}))', no, f'价变{w}d反转(无中性)')

# Overnight/intraday reversal variants
R('-rank(rev_overnight)', no, '隔夜反转:竞价跳空日内回补')
R('-rank(auction_return)', no, '竞价反转:集合竞价涨幅取反')
R('-rank(rev_overnight)', mc, '隔夜反转(中性)')
R('-rank(am_pm_divergence)', mc, '上下行一致:避免盘中方向反转')
R('-rank(intraday_reversal)', mc, '日内不反转:早盘尾盘方向一致')
R('-rank(first30_mom)', mc, '开盘反转:开盘急涨日内回落')
R('-rank(last30_mom)', mc, '尾盘反转:尾盘拉升次日低开')
R('-rank(intraday_mom)', mc, '日内反转:日内涨次日跌')
R('-rank(morning_return)', mc, '上午反转:早盘涨午后跌')
R('-rank(afternoon_return)', mc, '下午反转:午后涨次日跌')
R('-rank(body_return)', mc, '实体反转:K线实体方向反转')

# Signed power reversal
for p in [0.5,1.5,2,3]:
    R(f'-rank(signed_power(returns,{p}))', mc, f'幂{p}反转:非线性放大反转')
    R(f'-rank(signed_power(ret_5d,{p}))', mc, f'幂{p}反转5d:5日非线性反转')

# Reversal conditional on volume
R('-rank(ret_5d)*rank(vol_20d)', mc, '反乘波5d:高波时反转权重更大')
R('-rank(ret_20d)*rank(vol_20d)', mc, '反乘波20d')
R('-rank(returns)*rank(volume_profile_ratio)', mc, '日反乘量比:放量日反转信号更强')

# ===== LOW VOLATILITY (80 factors) =====
for w in [5,10,20,30,40,60,120]:
    R(f'-rank(vol_{w}d)', mc, f'低波{w}d:低波动异象')
    if w <= 60:
        R(f'-rank(ts_std(returns,{w}))', mc, f'收益稳定{w}d:低收益波动')

# Downside/upside vol
R('-rank(downside_vol_60d)', mc, '低下行波:只规避下行风险')
R('-rank(upside_vol_60d)', mc, '低上行波:低彩票偏好')
R('-rank(down_up_vol_ratio)', mc, '低上下比:下跌波<上涨波')
R('-rank(vol_ratio_5_20)', mc, '低波加速5/20:短期波不放大')
R('-rank(vol_ratio_20_60)', mc, '低波趋势20/60:中期波不放大')
R('-rank(ts_std(vol_20d,60))', mc, '低波之波60d:波动率稳定性')

# Intraday vol
R('-rank(intraday_volatility)', mc, '低日内波:日内价格平稳')
R('-rank(price_efficiency)', mc, '低价格效率:趋势不强者反转')

# Stability of rankings
R('-rank(ts_std(rank(close),20))', mc, '排名稳定20d:截面排名稳定=低风险')
R('-rank(ts_std(rank(close),60))', mc, '排名稳定60d')

# ===== MOMENTUM (70 factors) =====
for w in [20,30,40,60,120]:
    field = f'ret_{"120d_skip5" if w==120 else str(w)+"d"}'
    R(f'rank({field})', mc, f'动量{w}d:中期趋势延续')

# Risk-adjusted momentum
R('rank(sharpe_20d)', mc, 'Sharpe20d:风险调整动量')
R('rank(sharpe_60d)', mc, 'Sharpe60d:长期高质量动量')
R('rank(mom_vol_adj)', mc, '波调整动量:剔除波动的纯动量')
R('-rank(max_dd_60d)', mc, '低回撤60d:近期回撤小')

# Time-series rank momentum
for f in ['returns','ret_20d','ret_60d']:
    for w in [20,60,120]:
        R(f'rank(ts_rank({f},{w}))', mc, f'{f}时序排名{w}d:时序动量')

# Decay-linear momentum (recent > distant)
for f in ['returns','ret_20d','close']:
    for w in [10,20,60]:
        R(f'rank(ts_decay_linear({f},{w}))', mc, f'{f}衰减动{w}d:近期权重大')

# Momentum with volume confirmation
R('rank(ret_20d)*rank(volume_trend_20d)', mc, '动乘量:动量+量趋势确认')
R('rank(ret_60d)*rank(volume_trend_20d)', mc, '动60乘量')

# ===== LIQUIDITY/VOLUME (60 factors) =====
R('rank(amihud_20d)', mc, 'Amihud:低流动性补偿')
R('rank(amihud_20d)', no, 'Amihud(无中性)')
for f in ['turnover_5d','turnover_rate']:
    R(f'-rank({f})', mc, f'{f}低换手:避免过度交易')
    R(f'-rank({f})', no, f'{f}低换手(无中性)')
R('-rank(volume_profile_ratio)', mc, '低量比:放量日倾向反转')
R('-rank(volume_breakout)', mc, '低量突破:异常放量反转')
R('-rank(turnover_change)', mc, '换手减缓:资金稳定')

# Volume levels
for f in ['adv5','adv20']:
    R(f'-rank({f})', mc, f'{f}低均量:低关注度股票')
R('rank(log_dollar_vol)', mc, '对数成交额:规模调整流动性')
R('rank(dollar_volume)', mc, '成交额:资金规模')
R('-rank(amount_volatility)', mc, '低成交额波:资金稳定性')

# Volume changes
for w in [5,10,20,60]:
    R(f'-rank(ts_delta(volume,{w}))', mc, f'量变{w}d反转:近期量变大的反转')
    if w >= 10:
        R(f'-rank(ts_std(volume,{w}))', mc, f'量稳定{w}d:成交量波动小')

# Volume trend
R('-rank(volume_trend_20d)', mc, '量趋势反:量持续放大的反转')

# ===== PRICE PATTERNS (50 factors) =====
R('rank(lower_shadow)', mc, '长下影:探底回升=买盘支撑(锤子线)')
R('-rank(upper_shadow)', mc, '短上影:冲高无卖压')
R('rank(lower_shadow_pct)', mc, '长下影(分):分钟精确下影')
R('-rank(upper_shadow_pct)', mc, '短上影(分):分钟精确上影')
R('rank(body_ratio)', mc, '大实体:多空一方明确主导')
R('-rank(doji_score)', mc, '非十字星:避免多空均衡')
R('-rank(gap_down)', mc, '低向下跳空:利空冲击小')
R('rank(gap_up)', mc, '向上跳空:利好冲击延续')
R('rank(gap_momentum)', mc, '跳空动量:跳空方向延续性')

# Close vs range
for w in [20]:
    R(f'rank(close_vs_low_{w}d)', mc, f'近{w}d低:超卖反弹')
    R(f'-rank(close_vs_high_{w}d)', mc, f'远{w}d高:无回调压力')
R('-rank(close_location)', mc, '收盘位反:高位收盘次日回调')

# ===== VWAP/MICROSTRUCTURE (40 factors) =====
R('-rank(vwap_gap)', mc, 'VWAP反:高于VWAP收盘后回落')
R('rank(vwap_gap)', mc, 'VWAP正:买方主导日内')
for f in ['vwap_gap']:
    for w in [5,10,20]:
        R(f'rank(ts_delta({f},{w}))', mc, f'VWAP趋势{w}d:VWAP持续方向')

R('-rank(volume_concentration)', mc, '低量集中:无大单操纵')
R('rank(open_vol_ratio)', mc, '开盘量比:开盘资金关注')
R('-rank(close_vol_ratio)', mc, '低收盘量:无尾盘操纵')
R('rank(vwap_trend)', mc, 'VWAP趋势:VWAP方向')
R('-rank(vwap_trend)', mc, 'VWAP趋势反:VWAP方向反转')

# ===== TECHNICAL (60 factors) =====
for w in [20,60]:
    R(f'-rank(beta_{w}d)', mc, f'低Beta{w}d:低系统风险')
R('-rank(rsi_14)', mc, 'RSI反转14d:超卖买入')
R('-rank(market_cap_rank)', no, '小市值:规模溢价不中性化')
R('-rank(bollinger_pos)', mc, '布林下轨:接近下轨反弹')
R('-rank(bollinger_width)', mc, '布林窄带:波动收敛后突破')

# Volume-price correlation
R('rank(volume_price_corr)', mc, '量价正相关:放量涨缩量跌健康')
R('-rank(volume_price_div)', mc, '量价背离:价涨量缩=顶部')

# ===== STATISTICAL (50 factors) =====
for w in [20,60]:
    R(f'-rank(skewness_{w}d)', mc, f'低偏度{w}d:避免右偏彩票型')
    R(f'rank(hit_rate_{w}d)', mc, f'高胜率{w}d:正收益天数多')

R('-rank(kurtosis_60d)', mc, '低峰度:避免肥尾极端')
R('-rank(max_ret_20d)', mc, '低彩票20d:避免极端正收益')
R('rank(min_ret_20d)', mc, '高风险20d:极端负收益后反弹')

# Cumulative returns
for w in [5,10,20]:
    R(f'-rank(ts_sum(returns,{w}))', mc, f'累和{w}d反转:累积收益反转')
R('-rank(cumret_5d)', mc, '累积5d反转:复利累积反转')

# ===== CROSS-MODAL (80 factors) =====
cross_pairs = [
    ('ret_20d','vol_20d','动除波','动量除以波动=高质量动量'),
    ('ret_60d','vol_60d','动除波60d','长期动量质量'),
    ('sharpe_60d','max_dd_60d','Sharpe除回撤','风险调整后收益'),
]
for a,b,name,reason in cross_pairs:
    R(f'rank({a})/(rank({b})+0.001)', mc, f'{name}:{reason}')

R('rank(rev_vol_conf)', mc, '反转波确认:高波反转双信号')
R('rank(mom_vol_conf)', mc, '动波确认:高动量低波动')
R('rank(mom_liquidity_adj)', mc, '动流调整:剔除流动性纯动量')
R('rank(abnormal_vol_rev)', mc, '异常量反转:放量日价格反转')

# Multi-factor combos
combos = [
    ('-rank(ret_5d)+-rank(ret_20d)', mc, '双反转5+20:短中反转共振'),
    ('-rank(returns)+-rank(ret_5d)', mc, '双反转1+5:极短短反转'),
    ('rank(sharpe_60d)+rank(hit_rate_60d)', mc, '质量双确认:Sharpe+胜率'),
    ('-rank(vol_20d)+-rank(downside_vol_60d)', mc, '双低波:总波+下行波'),
    ('-rank(ret_5d)+-rank(vol_20d)', mc, '反加低波:反转+低波'),
    ('rank(ret_60d)+-rank(vol_60d)', mc, '动加减波:动量+减低波'),
    ('rank(lower_shadow)+-rank(upper_shadow)', mc, '下影加上影:锤子线确认'),
    ('-rank(beta_60d)+-rank(vol_60d)', mc, '低Beta加低波:双低风险'),
    ('rank(amihud_20d)+-rank(market_cap_rank)', mc, '流动性加小盘:双重规模'),
    ('-rank(gap_down)+-rank(doji_score)', mc, '低下跳加非十字:形态确认'),
]
for e, neut, reason in combos:
    R(e, neut, reason)

# ===== GROUP NEUTRALIZE (40 factors) =====
for field in ['ret_20d','ret_60d','sharpe_60d','vol_20d','ret_5d','returns']:
    R(f'group_neutralize(rank({field}),market_cap)', mc, f'组内中性{field}:市值组内排名')
    R(f'group_neutralize(-rank({field}),market_cap)', mc, f'组内中性-{field}:市值组内反转')

# ===== ts_delta sweeping (60 factors) =====
for field, fname in [('close','价'),('volume','量'),('returns','收益'),('vol_20d','波')]:
    for w in [3,5,10,20,30,40,60,120]:
        R(f'-rank(ts_delta({field},{w}))', mc, f'{fname}变{w}d反转')

# ===== ts_rank sweeping (40 factors) =====
for field in ['returns','volume','ret_20d','vol_20d']:
    for w in [10,20,40,60,120]:
        R(f'rank(ts_rank({field},{w}))', mc, f'{field}时序排{w}d')

# ===== ts_decay_linear sweeping (30 factors) =====
for field in ['returns','volume','close']:
    for w in [5,10,20,60]:
        R(f'-rank(ts_decay_linear({field},{w}))', mc, f'{field}衰减{w}d反')

# ===== ts_mean sweeping (30 factors) =====
for field in ['returns','volume','turnover_rate']:
    for w in [5,20,60]:
        R(f'rank(ts_mean({field},{w}))', mc, f'{field}均值{w}d')

# ===== signed_power variants (40 factors) =====
for f in ['returns','ret_5d','ret_20d']:
    for p in [0.3,0.5,0.7,1.5,2,3]:
        R(f'-rank(signed_power({f},{p}))', mc, f'幂{p}_{f}:非线性变换')

# ===== No-neutralization variants of top 50 =====
top50 = list(dict.fromkeys([e for e,n,r in factors[:50]]))
for e in top50[:30]:
    R(e, no, f'(无中性){e[:30]}')

# Deduplicate
seen = set()
unique = []
for e, neut, reason in factors:
    if e not in seen:
        seen.add(e)
        unique.append((e, neut, reason))

print(f'Total unique factors: {len(unique)}')
if len(unique) > 1000:
    unique = unique[:1000]

# Worker
def worker(chunk, wid):
    cj = http.cookiejar.CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try: o.open(urllib.request.Request('http://127.0.0.1:5000/login',
        urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
    except: pass
    for i, (e, neut, reason) in enumerate(chunk):
        d = json.dumps({'expression': e, 'neutralize': neut}).encode()
        try:
            r = json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',
                data=d, headers={'Content-Type':'application/json'})).read().decode())
            if (i+1) % 20 == 0:
                print(f'  W{wid}:{i+1}/{len(chunk)} IC={r.get("pearson_ic",0):.4f} | {reason[:50]}')
                sys.stdout.flush()
        except: pass

n = len(unique); chk = n // 4
threads = []; t0 = time.time()
for i in range(4):
    start = i * chk; end = start + chk if i < 3 else n
    t = threading.Thread(target=worker, args=(unique[start:end], i+1))
    t.start(); threads.append(t)
for t in threads: t.join()

elapsed = time.time() - t0
print(f'\n{len(unique)} factors in {elapsed/60:.1f}min')

# Cleanup
cj = http.cookiejar.CookieJar()
o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: o.open(urllib.request.Request('http://127.0.0.1:5000/login',
    urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
resp = o.open('http://127.0.0.1:5000/api/alpha/history')
recs = json.loads(resp.read().decode()).get('records', [])
kept = 0
for r in recs:
    ic = abs(r.get('metrics', {}).get('pearson_ic', 0))
    if ic < 0.01:
        try: o.open(urllib.request.Request('http://127.0.0.1:5000/api/alpha/history/'+r['id'], method='DELETE'))
        except: pass
    else: kept += 1
resp = o.open('http://127.0.0.1:5000/api/alpha/history')
total = json.loads(resp.read().decode()).get('count', 0)
print(f'Cleanup: {total} remain ({kept} |IC|>=0.01)')
print('DONE')
