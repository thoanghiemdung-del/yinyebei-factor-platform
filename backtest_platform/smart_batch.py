"""Smart batch: each factor has clear economic rationale. 200 factors, 4 threads."""
import urllib.request, http.cookiejar, json, time, threading, sys

def backtest_one(o, expr, neut):
    d = json.dumps({'expression': expr, 'neutralize': neut}).encode()
    r = json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',
        data=d, headers={'Content-Type':'application/json'})).read().decode())
    return r

# Each factor: (expression, neutralization, economic_rationale)
factors = []

# ===== SHORT-TERM REVERSAL (A-share strongest) =====
# Reason: T+1制度下散户追涨杀跌 → 短期过度反应 → 均值回复
for w, label in [(1,'1日'),(3,'3日'),(5,'5日'),(10,'10日'),(20,'20日')]:
    factors.append((f'-rank(returns)' if w==1 else f'-rank(ret_{w}d)',
        'market_cap', f'{label}反转: 买近期跌最多的,卖涨最多的'))

# Overnight reversal: 隔夜跳空后日内回补
factors.append(('-rank(rev_overnight)', 'none', '隔夜反转: 竞价跳空日内回补'))
factors.append(('-rank(auction_return)', 'market_cap', '竞价反转: 集合竞价涨幅取反'))

# Reversal enhanced by volatility: 高波动时过度反应更严重
factors.append(('-rank(rev_vol_regime)', 'market_cap', '高波反转: 波动大时反转信号更强'))
factors.append(('-rank(ret_5d)*rank(vol_20d)', 'market_cap', '反乘波: 反转信号用波动率加权'))

# ===== LOW VOLATILITY ANOMALY =====
# Reason: 低波动股票长期收益高于高波动 (Ang et al. 2006, Fama-French)
for w in [5,10,20,40,60,120]:
    factors.append((f'-rank(vol_{w}d)', 'market_cap', f'低波{w}d: 买波动最小的股票'))

# Downside-only risk: 上行波动是好事,只规避下行波动
factors.append(('-rank(downside_vol_60d)', 'market_cap', '低下行波: 只规避下跌波动率'))
factors.append(('-rank(down_up_vol_ratio)', 'market_cap', '低上下比: 下跌波<上涨波的股票'))

# Stability: 收益稳定性=质量信号
for w in [20,60]:
    factors.append((f'-rank(ts_std(returns,{w}))', 'market_cap', f'收益稳定{w}d: 收益波动小的股票'))

# ===== LIQUIDITY PREMIUM =====
# Reason: 流动性差的股票需补偿更高收益 (Amihud 2002)
factors.append(('rank(amihud_20d)', 'market_cap', 'Amihud: 低流动性→高补偿'))
factors.append(('-rank(turnover_5d)', 'market_cap', '低换手5d: 过度交易=散户=低收益'))
factors.append(('-rank(turnover_rate)', 'market_cap', '低换手率: 散户参与度低=机构主导'))
factors.append(('-rank(volume_breakout)', 'market_cap', '低量突破: 异常放量后倾向反转'))

# ===== MID-TERM MOMENTUM =====
# Reason: 机构资金中期趋势跟踪 (Jegadeesh-Titman 1993)
for w in [40,60,120]:
    label = '跳5' if w==120 else f'{w}d'
    factors.append((f'rank(ret_{"120d_skip5" if w==120 else str(w)+"d"})',
        'market_cap', f'动量{label}: 中期趋势延续'))

# Risk-adjusted momentum: 高质量上涨
factors.append(('rank(sharpe_20d)', 'market_cap', 'Sharpe20d: 风险调整动量'))
factors.append(('rank(sharpe_60d)', 'market_cap', 'Sharpe60d: 长期高质量动量'))
factors.append(('rank(mom_vol_adj)', 'market_cap', '波调整动量: 扣掉波动的纯动量'))

# ===== SIZE EFFECT =====
factors.append(('-rank(market_cap_rank)', 'none', '小市值: 小盘溢价 (Banz 1981)'))

# ===== VOLUME-PRICE INTERACTION =====
# Reason: 量价关系反映资金流向
factors.append(('rank(volume_price_corr)', 'market_cap', '量价正相关: 放量涨缩量跌=机构健康'))
factors.append(('-rank(volume_price_div)', 'market_cap', '量价背离: 价涨量缩=顶部信号'))
factors.append(('-rank(volume_profile_ratio)', 'market_cap', '低量比: 放量日收益倾向反转'))

# Volume trend
for w in [20,60]:
    factors.append((f'-rank(volume_trend_20d)' if w==20 else f'rank(ts_delta(volume,{w}))',
        'market_cap', f'量变化{w}d: 量能趋势'))

# ===== PRICE PATTERNS (K线形态) =====
# Long lower shadow = bullish reversal (hammer)
factors.append(('rank(lower_shadow)', 'market_cap', '长下影: 探底回升=买盘支撑'))
factors.append(('-rank(upper_shadow)', 'market_cap', '短上影: 冲高无卖压'))
factors.append(('rank(body_ratio)', 'market_cap', '大实体: 多空一方明确主导'))
factors.append(('-rank(doji_score)', 'market_cap', '非十字星: 避免方向不明'))

# Gap analysis
factors.append(('-rank(gap_down)', 'market_cap', '低向下跳空: 利空冲击小'))
factors.append(('rank(gap_momentum)', 'market_cap', '跳空动量: 跳空后方向延续'))

# Close position vs range
for w in [20]:
    factors.append((f'rank(close_vs_low_{w}d)', 'market_cap', f'近{w}d低: 接近近期低点=反弹概率大'))
    factors.append((f'-rank(close_vs_high_{w}d)', 'market_cap', f'远{w}d高: 远离高点=回调压力小'))

# ===== INTRADAY MICROSTRUCTURE =====
# Opening/Closing power
factors.append(('-rank(first30_mom)', 'market_cap', '开盘反转: 开盘急涨后日内回落'))
factors.append(('-rank(last30_mom)', 'market_cap', '尾盘反转: 尾盘拉升次日低开'))
factors.append(('-rank(intraday_mom)', 'market_cap', '日内反转: 全天涨次日跌'))
factors.append(('-rank(am_pm_divergence)', 'market_cap', '上下行一致: 避免盘中反转'))
factors.append(('-rank(morning_return)', 'market_cap', '上午反转: 早盘涨午后跌'))
factors.append(('-rank(afternoon_return)', 'market_cap', '下午反转: 午后涨次日跌'))

# VWAP
factors.append(('-rank(vwap_gap)', 'market_cap', 'VWAP反转: 高于VWAP收盘后回落'))
factors.append(('-rank(close_location)', 'market_cap', '收盘位置反转: 高位收盘=次日回调'))

# Intraday quality
factors.append(('-rank(intraday_volatility)', 'market_cap', '低日内波: 日内平稳'))
factors.append(('-rank(price_efficiency)', 'market_cap', '低价格效率: 趋势不强者反转'))
factors.append(('-rank(volume_concentration)', 'market_cap', '低量集中: 无大单操纵'))

# ===== STATISTICAL MOMENTS =====
# Skewness: negative skew = crash risk (Harvey & Siddique 2000)
for w in [20,60]:
    factors.append((f'-rank(skewness_{w}d)', 'market_cap', f'低偏度{w}d: 避免右偏彩票型'))
factors.append(('-rank(kurtosis_60d)', 'market_cap', '低峰度: 避免肥尾极端事件'))

# Win rate
for w in [20,60]:
    factors.append((f'rank(hit_rate_{w}d)', 'market_cap', f'高胜率{w}d: 正收益天数多'))

# Max drawdown
factors.append(('-rank(max_dd_60d)', 'market_cap', '低回撤: 避免近期大跌股票'))

# ===== TECHNICAL INDICATORS =====
# RSI: A股超卖反弹强于超买回调
for w in [14]:
    factors.append((f'-rank(rsi_{w})', 'market_cap', f'RSI反转: 超卖买入'))

# Beta: low beta anomaly (Frazzini & Pedersen 2014)
for w in [20,60]:
    factors.append((f'-rank(beta_{w}d)', 'market_cap', f'低Beta{w}d: 低系统风险'))

# Bollinger
factors.append(('-rank(bollinger_pos)', 'market_cap', '布林下轨: 接近下轨反弹'))
factors.append(('-rank(bollinger_width)', 'market_cap', '布林窄带: 波动收敛后突破'))

# ===== CROSS-MODAL =====
factors.append(('rank(rev_vol_conf)', 'market_cap', '反转波确认: 高波+反转双重信号'))
factors.append(('rank(mom_liquidity_adj)', 'market_cap', '动流调整: 剔除流动性的纯动量'))

# ===== ts_delta variants =====
for field, fname, w in [('close','价',10),('close','价',30),('close','价',60),
                         ('volume','量',10),('volume','量',20),('volume','量',60)]:
    factors.append((f'-rank(ts_delta({field},{w}))', 'market_cap', f'{fname}变{w}d反转: 近期变化大的反转'))

# ===== ts_decay_linear =====
for field, fname, w in [('returns','收益',10),('returns','收益',20),
                         ('volume','量',10),('volume','量',20)]:
    factors.append((f'-rank(ts_decay_linear({field},{w}))', 'market_cap',
        f'衰减{fname}{w}d反转: 近期加权变化反转'))

# ===== signed_power for non-linear effects =====
for p, pname in [(0.5,'根号'),(2,'平方'),(3,'立方')]:
    factors.append((f'-rank(signed_power(returns,{p}))', 'market_cap', f'{pname}反转: 非线性放大反转信号'))

# ===== Multi-factor combinations (only meaningful ones) =====
factors.append(('-rank(ret_5d)+-rank(ret_20d)', 'market_cap', '双反转: 短+中反转共振'))
factors.append(('-rank(returns)+-rank(ret_5d)', 'market_cap', '极短+短反转'))
factors.append(('rank(sharpe_60d)+rank(hit_rate_60d)', 'market_cap', '质量双确认: Sharpe+胜率'))
factors.append(('-rank(vol_20d)+-rank(downside_vol_60d)', 'market_cap', '双低波: 总波+下行波'))
factors.append(('-rank(ret_5d)*rank(vol_20d)', 'market_cap', '反乘波: 高波时反转权重更大'))

# Deduplicate
seen = set()
unique = []
for e, neut, reason in factors:
    if e not in seen:
        seen.add(e)
        unique.append((e, neut, reason))

print(f'Total thoughtful factors: {len(unique)}')

# Worker
def worker(chunk, wid):
    cj = http.cookiejar.CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try: o.open(urllib.request.Request('http://127.0.0.1:5000/login',
        urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
    except: pass
    for i, (e, neut, reason) in enumerate(chunk):
        try:
            r = backtest_one(o, e, neut)
            ic = r.get('pearson_ic', 0)
            if i % 15 == 0:
                print(f'  W{wid}: {i+1}/{len(chunk)} IC={ic:.4f} | {reason[:40]}')
                sys.stdout.flush()
        except Exception as ex:
            if i % 20 == 0: print(f'  W{wid}: {i+1} FAIL')

n = len(unique); chk = n // 4
threads = []; t0 = time.time()
for i in range(4):
    start = i * chk; end = start + chk if i < 3 else n
    t = threading.Thread(target=worker, args=(unique[start:end], i+1))
    t.start(); threads.append(t)
for t in threads: t.join()

elapsed = time.time() - t0
print(f'\nTested {n} factors in {elapsed/60:.1f}min')

# Cleanup low IC
cj = http.cookiejar.CookieJar()
o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: o.open(urllib.request.Request('http://127.0.0.1:5000/login',
    urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
resp = o.open('http://127.0.0.1:5000/api/alpha/history')
recs = json.loads(resp.read().decode()).get('records', [])
del_cnt = 0
for r in recs:
    if abs(r.get('metrics', {}).get('pearson_ic', 0)) < 0.01:
        try:
            o.open(urllib.request.Request('http://127.0.0.1:5000/api/alpha/history/' + r['id'], method='DELETE'))
            del_cnt += 1
        except: pass
resp = o.open('http://127.0.0.1:5000/api/alpha/history')
total = json.loads(resp.read().decode()).get('count', 0)
print(f'Cleanup: deleted {del_cnt} |IC|<0.01 | Remaining: {total} factors')
print('DONE')
