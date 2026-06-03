"""Generate 1000+ factors covering ALL fields, 4-thread parallel."""
import urllib.request, http.cookiejar, json, time, threading, sys

# All fields grouped by category
FIELDS = {
    '收益':['returns','ret_5d','ret_10d','ret_20d','ret_40d','ret_60d','ret_120d_skip5','cumret_5d',
           'morning_return','afternoon_return','auction_return'],
    '波动':['vol_5d','vol_10d','vol_20d','vol_40d','vol_60d','vol_120d','downside_vol_60d','upside_vol_60d',
           'down_up_vol_ratio','vol_ratio_5_20','vol_ratio_20_60','skewness_20d','skewness_60d','kurtosis_60d'],
    '量价':['volume','amount','turnover_rate','turnover_5d','turnover_change','adv5','adv20',
           'volume_profile_ratio','volume_breakout','amihud_20d','log_dollar_vol','dollar_volume',
           'amount_volatility','volume_price_corr','volume_trend_20d'],
    '形态':['upper_shadow','lower_shadow','body_ratio','gap_up','gap_down','doji_score',
           'close_vs_high_20d','close_vs_low_20d','bollinger_pos','bollinger_width'],
    '微观':['first30_mom','last30_mom','intraday_mom','body_return','intraday_volatility',
           'upper_shadow_pct','lower_shadow_pct','price_efficiency','vwap_gap','volume_concentration',
           'am_pm_divergence','close_location','intraday_reversal'],
    '技术':['rsi_14','beta_20d','beta_60d','market_cap_rank','sharpe_20d','sharpe_60d',
           'mom_vol_adj','max_dd_60d','hit_rate_20d','hit_rate_60d','max_ret_20d','min_ret_20d'],
    '跨模态':['mom_vol_conf','mom_liquidity_adj','rev_vol_conf','rev_vol_regime',
             'volume_price_div','gap_momentum','abnormal_vol_rev','rev_overnight'],
    '反转':['rev_1d','rev_5d','rev_10d','rev_20d'],
}

WINDOWS = [5,10,20,40,60,120]
OPS = ['rank','-rank','ts_delta','ts_rank','ts_decay_linear','signed_power']
POWERS = [0.5, 2, 3]

factors = set()

# For each field, generate 5+ variants
for cat, fields in FIELDS.items():
    for f in fields:
        # 1. Simple rank
        factors.add((f'rank({f})', 'market_cap'))
        # 2. Negative rank
        factors.add((f'-rank({f})', 'market_cap'))
        # 3. rank + no neutralization
        factors.add((f'rank({f})', 'none'))
        # 4. -rank + no neutralization
        factors.add((f'-rank({f})', 'none'))
        # 5-6. signed_power variants
        for p in [0.5, 2]:
            factors.add((f'rank(signed_power({f},{p}))', 'market_cap'))
            factors.add((f'-rank(signed_power({f},{p}))', 'market_cap'))

    # ts_delta for key fields
    for f in ['close','volume','returns','vol_20d']:
        for w in WINDOWS:
            factors.add((f'rank(ts_delta({f},{w}))', 'market_cap'))
            factors.add((f'-rank(ts_delta({f},{w}))', 'market_cap'))

    # ts_rank for key fields
    for f in ['returns','volume','vol_20d']:
        for w in [20,60,120]:
            factors.add((f'rank(ts_rank({f},{w}))', 'market_cap'))
            factors.add((f'-rank(ts_rank({f},{w}))', 'market_cap'))

    # ts_decay_linear for key fields
    for f in ['returns','volume','close']:
        for w in [10,20,60]:
            factors.add((f'rank(ts_decay_linear({f},{w}))', 'market_cap'))
            factors.add((f'-rank(ts_decay_linear({f},{w}))', 'market_cap'))

    # ts_std for stability
    for f in ['returns','close','volume']:
        for w in [20,60,120]:
            factors.add((f'-rank(ts_std({f},{w}))', 'market_cap'))

    # Cross-field combos
    combos = [
        ('rank(ret_20d)+rank(vol_20d)', 'market_cap'),
        ('-rank(ret_5d)+-rank(ret_20d)', 'market_cap'),
        ('rank(ret_20d)-rank(ret_5d)', 'market_cap'),
        ('rank(ret_60d)-rank(ret_20d)', 'market_cap'),
        ('-rank(returns)+-rank(ret_5d)', 'market_cap'),
        ('rank(sharpe_60d)+rank(hit_rate_60d)', 'market_cap'),
        ('-rank(vol_20d)+-rank(downside_vol_60d)', 'market_cap'),
        ('rank(lower_shadow)+-rank(upper_shadow)', 'market_cap'),
        ('rank(ret_20d)*rank(volume_trend_20d)', 'market_cap'),
        ('-rank(ret_5d)*rank(vol_20d)', 'market_cap'),
    ]
    for expr, neut in combos:
        factors.add((expr, neut))

factors_list = list(factors)
# Deduplicate by expression
seen_expr = set()
unique = []
for e, neut in factors_list:
    if e not in seen_expr:
        seen_expr.add(e)
        unique.append((e, neut))
factors_list = unique

print(f'Total unique factors: {len(factors_list)}')
if len(factors_list) > 1000:
    factors_list = factors_list[:1000]
print(f'Running {len(factors_list)} factors...')

# Worker
def worker(chunk, wid, results_list):
    cj = http.cookiejar.CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try: o.open(urllib.request.Request('http://127.0.0.1:5000/login',
        urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
    except: pass
    for i, (e, neut) in enumerate(chunk):
        d = json.dumps({'expression': e, 'neutralize': neut}).encode()
        try:
            r = json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',
                data=d, headers={'Content-Type':'application/json'})).read().decode())
            ic = r.get('pearson_ic', 0)
            if i % 25 == 0:
                print(f'  W{wid}: {i+1}/{len(chunk)} IC={ic:.4f}')
                sys.stdout.flush()
        except:
            pass

# 4 threads
n = len(factors_list)
chunk = n // 4
threads = []
t0 = time.time()
for i in range(4):
    start = i * chunk
    end = start + chunk if i < 3 else n
    results = []
    t = threading.Thread(target=worker, args=(factors_list[start:end], i+1, results))
    t.start()
    threads.append(t)

for t in threads:
    t.join()

elapsed = time.time() - t0

# Cleanup
cj = http.cookiejar.CookieJar()
o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: o.open(urllib.request.Request('http://127.0.0.1:5000/login',
    urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
resp = o.open('http://127.0.0.1:5000/api/alpha/history')
recs = json.loads(resp.read().decode()).get('records', [])
deleted = 0
for r in recs:
    ic = abs(r.get('metrics', {}).get('pearson_ic', 0))
    if ic < 0.01:
        try:
            o.open(urllib.request.Request('http://127.0.0.1:5000/api/alpha/history/' + r['id'], method='DELETE'))
            deleted += 1
        except: pass
resp = o.open('http://127.0.0.1:5000/api/alpha/history')
total = json.loads(resp.read().decode()).get('count', 0)

print(f'\nDone: {elapsed/60:.1f}min | Deleted {deleted} low-IC | {total} factors remain')
