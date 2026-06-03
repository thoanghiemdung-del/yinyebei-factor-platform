"""Agent M2: Momentum + VWAP + Technical (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[
('rank(ret_60d)','中动量60d','market_cap'),
('rank(ret_120d_skip5)','长动量跳5','market_cap'),
('rank(sharpe_20d)','Sharpe20d','market_cap'),
('rank(sharpe_60d)','Sharpe60d','market_cap'),
('rank(mom_vol_adj)','波调整动量','market_cap'),
('-rank(max_dd_60d)','低回撤','market_cap'),
('rank(ts_rank(returns,20))','时序排20','market_cap'),
('rank(ts_rank(returns,60))','时序排60','market_cap'),
('rank(ts_decay_linear(ret_20d,20))','衰减动20d','market_cap'),
('rank(vwap_gap)','VWAP偏离','market_cap'),
('-rank(vwap_trend)','VWAP趋势反','market_cap'),
('rank(close_location)','收盘位置','market_cap'),
('-rank(upper_shadow_pct)','低上影','market_cap'),
('rank(lower_shadow_pct)','高下影','market_cap'),
('-rank(beta_20d)','低Beta20d','market_cap'),
('-rank(beta_60d)','低Beta60d','market_cap'),
('-rank(rsi_14)','RSI反转','market_cap'),
('-rank(market_cap_rank)','小市值','none'),
('-rank(bollinger_pos)','布林下轨','market_cap'),
('rank(bollinger_width)','布林带宽','market_cap'),
('rank(body_ratio)','大实体','market_cap'),
('-rank(gap_down)','低下跳','market_cap'),
('rank(close_vs_low_20d)','近20d低','market_cap'),
('-rank(close_vs_high_20d)','远20d高','market_cap'),
('rank(gap_momentum)','跳空动量','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        ic=r.get('pearson_ic',0);sh=r.get('sharpe',0)
        print(f'M2.{i+1} {n} IC={ic:.4f} S={sh:.2f}')
    except Exception as ex:print(f'M2.{i+1} {n} FAIL:{str(ex)[:30]}')
print('Agent M2 done')
