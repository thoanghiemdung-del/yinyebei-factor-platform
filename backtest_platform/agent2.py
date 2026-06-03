"""Agent 2: Momentum + Technical + Price Patterns (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: op.open(urllib.request.Request('http://127.0.0.1:5000/login', urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
f=[
('rank(ret_60d)','中动量60d','market_cap'),
('rank(ret_120d_skip5)','长动量跳5','market_cap'),
('rank(sharpe_20d)','高Sharpe20d','market_cap'),
('rank(sharpe_60d)','高Sharpe60d','market_cap'),
('rank(mom_vol_adj)','波调动量','market_cap'),
('-rank(max_dd_60d)','低回撤','market_cap'),
('rank(ts_rank(returns,20))','时序排收益20d','market_cap'),
('rank(ts_rank(returns,60))','时序排收益60d','market_cap'),
('rank(ts_decay_linear(returns,20))','衰减动20d','market_cap'),
('-rank(beta_20d)','低Beta20d','market_cap'),
('-rank(beta_60d)','低Beta60d','market_cap'),
('-rank(rsi_14)','RSI反转','market_cap'),
('-rank(bollinger_pos)','布林下轨','market_cap'),
('rank(bollinger_width)','布林带宽','market_cap'),
('-rank(market_cap_rank)','小市值','none'),
('rank(lower_shadow)','长下影','market_cap'),
('-rank(upper_shadow)','短上影','market_cap'),
('rank(body_ratio)','大实体','market_cap'),
('-rank(gap_down)','低下跳','market_cap'),
('rank(close_vs_low_20d)','近20d低','market_cap'),
('-rank(close_vs_high_20d)','远20d高','market_cap'),
('-rank(doji_score)','非十字星','market_cap'),
('rank(gap_up)','上跳空','market_cap'),
('-rank(skewness_20d)','低偏度20d','market_cap'),
('-rank(kurtosis_60d)','低峰度','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(op.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'A2.{i+1} {n} IC={r.get("pearson_ic",0):.4f} Sharpe={r.get("sharpe",0):.2f}')
    except Exception as ex: print(f'A2.{i+1} {n} FAIL: {str(ex)[:40]}')
    time.sleep(0.3)
print('Agent2 done')
