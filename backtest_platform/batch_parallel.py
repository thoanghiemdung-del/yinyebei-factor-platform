"""Parallel batch backtest using multiple workers."""
import urllib.request, http.cookiejar, json, time, sys
from multiprocessing import Process, Queue
import itertools

# Generate factors (same logic as batch_1000.py)
def gen_factors():
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

    factors = set()
    for f in fields:
        factors.add((f'rank({f})', 'market_cap'))
        factors.add((f'-rank({f})', 'market_cap'))
        factors.add((f'rank({f})', 'none'))
        factors.add((f'-rank({f})', 'none'))

    for f in ['close','volume','returns','vol_20d']:
        for w in [5,10,20,40,60,120]:
            factors.add((f'rank(ts_delta({f},{w}))', 'market_cap'))
            factors.add((f'-rank(ts_delta({f},{w}))', 'market_cap'))

    for f in ['returns','ret_20d','volume','vol_20d']:
        for w in [20,60,120]:
            factors.add((f'rank(ts_rank({f},{w}))', 'market_cap'))
            factors.add((f'-rank(ts_rank({f},{w}))', 'market_cap'))

    for f in ['returns','close','volume']:
        for w in [20,60,120]:
            factors.add((f'-rank(ts_std({f},{w}))', 'market_cap'))

    for f in ['returns','ret_5d','ret_20d']:
        for p in [0.5,2,3]:
            factors.add((f'rank(signed_power({f},{p}))', 'market_cap'))
            factors.add((f'-rank(signed_power({f},{p}))', 'market_cap'))

    for f in ['returns','volume','close']:
        for w in [10,20,60]:
            factors.add((f'rank(ts_decay_linear({f},{w}))', 'market_cap'))

    combos = ['rank(ret_20d)+rank(vol_20d)','-rank(ret_5d)+-rank(ret_10d)',
              'rank(ret_20d)-rank(ret_5d)','rank(vol_20d)+rank(skewness_20d)',
              '-rank(vol_20d)+-rank(downside_vol_60d)']
    for expr in combos:
        factors.add((expr, 'market_cap'))

    return list(factors)[:500]  # Limit to 500

def worker(chunk, worker_id):
    """Process a chunk of factors."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try: opener.open(urllib.request.Request('http://127.0.0.1:5000/login',
        urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
    except: pass

    ok = 0
    for i, (expr, neut) in enumerate(chunk):
        d = json.dumps({'expression': expr, 'neutralize': neut}).encode()
        req = urllib.request.Request('http://127.0.0.1:5000/api/backtest', data=d,
                                     headers={'Content-Type':'application/json'})
        try:
            resp = opener.open(req)
            json.loads(resp.read().decode())
            ok += 1
        except:
            pass
        # Print progress every 20
        if (i+1) % 20 == 0:
            print(f'  W{worker_id}: {i+1}/{len(chunk)}')
            sys.stdout.flush()
    print(f'  W{worker_id} DONE: {ok}/{len(chunk)}')
    sys.stdout.flush()

if __name__ == '__main__':
    factors = gen_factors()
    print(f'Total factors: {len(factors)}')

    # Split into 4 chunks for 4 parallel workers
    N = 4
    chunk_size = len(factors) // N
    chunks = []
    for i in range(N):
        start = i * chunk_size
        end = start + chunk_size if i < N-1 else len(factors)
        chunks.append(factors[start:end])

    print(f'Starting {N} parallel workers...')
    t0 = time.time()

    procs = []
    for i, chunk in enumerate(chunks):
        p = Process(target=worker, args=(chunk, i+1))
        p.start()
        procs.append(p)

    for p in procs:
        p.join()

    elapsed = time.time() - t0
    print(f'\nAll workers done in {elapsed/60:.1f}min')
