"""Batch backtest ~1000 WQ-inspired factors."""
import urllib.request, http.cookiejar, json, time, sys

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: opener.open(urllib.request.Request('http://127.0.0.1:5000/login',
    urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass

factors = set()  # (expr, neut) tuples

# All available daily fields (no minute data for speed)
fields = ['returns','ret_5d','ret_10d','ret_20d','ret_40d','ret_60d','ret_120d_skip5',
          'vol_5d','vol_10d','vol_20d','vol_40d','vol_60d','vol_120d',
          'downside_vol_60d','upside_vol_60d','down_up_vol_ratio',
          'skewness_20d','skewness_60d','kurtosis_60d',
          'max_ret_20d','min_ret_20d','hit_rate_20d','hit_rate_60d',
          'volume','amount','turnover_rate','adv5','adv20',
          'volume_profile_ratio','volume_breakout','turnover_5d','turnover_change',
          'amihud_20d','log_dollar_vol','dollar_volume','amount_volatility',
          'volume_price_corr','volume_trend_20d','vol_ratio_5_20','vol_ratio_20_60',
          'upper_shadow','lower_shadow','body_ratio','gap_up','gap_down','doji_score',
          'close_vs_high_20d','close_vs_low_20d',
          'rsi_14','bollinger_pos','bollinger_width','beta_20d','beta_60d',
          'market_cap_rank','sharpe_20d','sharpe_60d','mom_vol_adj','max_dd_60d',
          'mom_vol_conf','mom_liquidity_adj','rev_vol_conf','rev_vol_regime',
          'volume_price_div','gap_momentum','intraday_reversal',
          'cumret_5d','rev_1d','rev_5d','rev_10d','rev_20d','rev_overnight',
          'abnormal_vol_rev','extreme_loser_5d']

print(f'Base fields: {len(fields)}')

# Strategy 1: Simple rank/negative rank for each field
for f in fields:
    factors.add((f'rank({f})', 'market_cap'))
    factors.add((f'-rank({f})', 'market_cap'))
    factors.add((f'rank({f})', 'none'))
    factors.add((f'-rank({f})', 'none'))

# Strategy 2: ts_delta with various windows
for f in ['close','volume','returns','vol_20d']:
    for w in [5,10,20,40,60,120]:
        factors.add((f'rank(ts_delta({f},{w}))', 'market_cap'))
        factors.add((f'-rank(ts_delta({f},{w}))', 'market_cap'))

# Strategy 3: ts_rank with various windows
for f in ['returns','ret_20d','volume','vol_20d']:
    for w in [20,60,120]:
        factors.add((f'rank(ts_rank({f},{w}))', 'market_cap'))
        factors.add((f'-rank(ts_rank({f},{w}))', 'market_cap'))

# Strategy 4: ts_std (stability)
for f in ['returns','close','volume']:
    for w in [20,60,120]:
        factors.add((f'-rank(ts_std({f},{w}))', 'market_cap'))

# Strategy 5: ts_mean based
for f in ['volume','returns','turnover_rate']:
    for w in [20,60]:
        factors.add((f'rank(ts_mean({f},{w}))', 'market_cap'))

# Strategy 6: signed_power variants
for f in ['returns','ret_5d','ret_20d']:
    for p in [0.5,2,3]:
        factors.add((f'rank(signed_power({f},{p}))', 'market_cap'))
        factors.add((f'-rank(signed_power({f},{p}))', 'market_cap'))
        factors.add((f'rank(signed_power({f},{p}))', 'none'))

# Strategy 7: ts_decay_linear
for f in ['returns','volume','close']:
    for w in [10,20,60]:
        factors.add((f'rank(ts_decay_linear({f},{w}))', 'market_cap'))
        factors.add((f'-rank(ts_decay_linear({f},{w}))', 'market_cap'))

# Strategy 8: Combined factors (additive)
combos = [
    ('rank(ret_20d)+rank(vol_20d)', '动量加波动'),
    ('-rank(ret_5d)+-rank(ret_10d)', '双反转'),
    ('rank(ret_20d)-rank(ret_5d)', '动减反'),
    ('rank(vol_20d)+rank(skewness_20d)', '波动加偏度'),
    ('rank(hit_rate_60d)+rank(sharpe_60d)', '胜率加Sharpe'),
    ('-rank(vol_20d)+-rank(downside_vol_60d)', '双低波'),
    ('rank(body_ratio)+rank(close_vs_high_20d)', '形态动'),
    ('-rank(gap_down)+-rank(doji_score)', '跳空十字'),
]
for expr, _ in combos:
    factors.add((expr, 'market_cap'))
    factors.add((expr, 'none'))

# Strategy 9: group_neutralize variants
for f in ['ret_20d','ret_5d','vol_20d','sharpe_60d','volume_price_corr']:
    factors.add((f'group_neutralize(rank(ts_delta({f},20)),market_cap)', 'market_cap'))
    factors.add((f'group_neutralize(rank({f}),market_cap)', 'market_cap'))

factors_list = list(factors)
print(f'Unique factors: {len(factors_list)}')

# Limit to ~1000 to be practical
if len(factors_list) > 1200:
    factors_list = factors_list[:1200]

print(f'Starting batch: {len(factors_list)} factors')
t0 = time.time()
ok = 0
for i, (expr, neut) in enumerate(factors_list):
    d = json.dumps({'expression': expr, 'neutralize': neut}).encode()
    req = urllib.request.Request('http://127.0.0.1:5000/api/backtest', data=d,
                                 headers={'Content-Type':'application/json'})
    try:
        resp = opener.open(req)
        r = json.loads(resp.read().decode())
        ok += 1
        if i % 100 == 0 and i > 0:
            elapsed = time.time() - t0
            eta = elapsed / (i+1) * (len(factors_list)-i-1)
            ic = r.get('pearson_ic', 0)
            print(f'  {i}/{len(factors_list)} ({100*i//len(factors_list)}%) IC={ic:.3f} ETA {eta/60:.0f}min')
            sys.stdout.flush()
    except Exception as e:
        if i % 50 == 0: print(f'  FAIL {i}: {str(e)[:40]}')

elapsed = time.time() - t0
print(f'\nOK: {ok}/{len(factors_list)} in {elapsed/60:.1f}min')
