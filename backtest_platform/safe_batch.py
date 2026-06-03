"""Safe batch: 2 threads, 0.3s delay, won't crash server."""
import urllib.request, http.cookiejar, json, time, threading

cj=http.cookiejar.CookieJar()
o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass

# Get existing expressions
resp=o.open('http://127.0.0.1:5000/api/alpha/history')
existing=set()
for r in json.loads(resp.read().decode()).get('records',[]):
    existing.add(r['expression'].strip())

F=[];mc='market_cap'
# Every field, 5+ variants
for fld in ['returns','ret_5d','ret_10d','ret_20d','ret_40d','ret_60d','ret_120d_skip5']:
    F.extend([(f'rank({fld})',mc),(f'-rank({fld})',mc),(f'-rank(signed_power({fld},2))',mc),
              (f'-rank(ts_rank({fld},20))',mc),(f'rank(ts_rank({fld},60))',mc),(f'-rank(ts_decay_linear({fld},10))',mc)])
for w in [5,10,20,40,60,120]:
    f=f'vol_{w}d'
    F.extend([(f'-rank({f})',mc),(f'-rank(ts_rank({f},20))',mc),(f'-rank(ts_rank({f},60))',mc),
              (f'-rank(signed_power({f},2))',mc),(f'-rank(ts_decay_linear({f},10))',mc)])
for fld in ['downside_vol_60d','upside_vol_60d','down_up_vol_ratio','vol_ratio_5_20','vol_ratio_20_60',
            'skewness_20d','skewness_60d','kurtosis_60d','max_ret_20d','min_ret_20d','hit_rate_20d','hit_rate_60d']:
    F.extend([(f'-rank({fld})',mc),(f'rank({fld})',mc),(f'-rank(ts_rank({fld},20))',mc)])
for fld in ['volume','amount','turnover_rate','adv5','adv20','volume_profile_ratio','volume_breakout',
            'turnover_5d','turnover_change','amihud_20d','log_dollar_vol','dollar_volume','amount_volatility',
            'volume_price_corr','volume_trend_20d','volume_price_div']:
    F.extend([(f'rank({fld})',mc),(f'-rank({fld})',mc),(f'-rank(ts_rank({fld},20))',mc),
              (f'rank(ts_rank({fld},20))',mc),(f'-rank(ts_delta({fld},20))',mc)])
for fld in ['upper_shadow','lower_shadow','body_ratio','gap_up','gap_down','doji_score',
            'close_vs_high_20d','close_vs_low_20d','gap_momentum']:
    F.extend([(f'rank({fld})',mc),(f'-rank({fld})',mc)])
for fld in ['beta_20d','beta_60d','rsi_14','bollinger_pos','bollinger_width','market_cap_rank',
            'sharpe_20d','sharpe_60d','mom_vol_adj','max_dd_60d']:
    F.extend([(f'-rank({fld})',mc),(f'rank({fld})',mc)])
for fld in ['first30_mom','last30_mom','intraday_mom','morning_return','afternoon_return',
            'body_return','auction_return','vwap_gap','close_location','price_efficiency',
            'intraday_volatility','volume_concentration','am_pm_divergence']:
    F.extend([(f'-rank({fld})',mc),(f'rank({fld})',mc),(f'-rank(ts_rank({fld},20))',mc),(f'-rank(signed_power({fld},2))',mc)])
for fld in ['intraday_reversal','rev_overnight','rev_vol_regime','abnormal_vol_rev',
            'rev_vol_conf','mom_vol_conf','mom_liquidity_adj','cumret_5d']:
    F.extend([(f'rank({fld})',mc),(f'-rank({fld})',mc)])
for fld in ['close','volume','returns']:
    for w in [5,10,20,40,60,120]:
        F.append((f'-rank(ts_delta({fld},{w}))',mc))
    for w in [10,20,40,60,120]:
        F.append((f'-rank(ts_std({fld},{w}))',mc))
for fld in ['returns','ret_5d','ret_20d']:
    for p in [0.5,1.5,2,3]:
        F.append((f'-rank(signed_power({fld},{p}))',mc))
for fld in ['returns','volume','close']:
    for w in [10,20,40,60]:
        F.append((f'-rank(ts_decay_linear({fld},{w}))',mc))

uniq=[];seen=set()
for e,n in F:
    if e not in seen and e not in existing:
        seen.add(e);uniq.append((e,n))
print(f'Factors: {len(uniq)}')

# 2 threads ONLY, with delay
def worker(chunk, wid):
    cj2=http.cookiejar.CookieJar()
    o2=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj2))
    try:o2.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
    except:pass
    for i,(e,n) in enumerate(chunk):
        d=json.dumps({'expression':e,'neutralize':n}).encode()
        try:o2.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'}))
        except:pass
        time.sleep(0.3)  # CRITICAL: prevent connection flood
        if i%50==0:print(f'  W{wid}:{i}/{len(chunk)}')

T=2;n=len(uniq);sz=n//T;threads=[];t0=time.time()
for i in range(T):
    chunk=uniq[i*sz:(i+1)*sz if i<T-1 else n]
    t=threading.Thread(target=worker,args=(chunk,i+1))
    t.start();threads.append(t)
for t in threads:t.join()
print(f'Done {n} in {(time.time()-t0)/60:.1f}min')

# Cleanup
resp=o.open('http://127.0.0.1:5000/api/alpha/history')
recs=json.loads(resp.read().decode()).get('records',[])
for r in recs:
    if abs(r.get('metrics',{}).get('pearson_ic',0))<0.01:
        try:o.open(urllib.request.Request('http://127.0.0.1:5000/api/alpha/history/'+r['id'],method='DELETE'))
        except:pass
resp=o.open('http://127.0.0.1:5000/api/alpha/history')
r2=json.loads(resp.read().decode())
alphas=[x for x in r2.get('records',[]) if x['type']=='alpha']
print(f'Total:{r2.get("count",0)} Single:{len(alphas)}')
