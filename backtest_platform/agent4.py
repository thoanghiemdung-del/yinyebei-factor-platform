"""Agent 4: Advanced combos + group_neutralize + signed_power (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: op.open(urllib.request.Request('http://127.0.0.1:5000/login', urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
f=[
('rank(signed_power(returns,2))','平方收益','market_cap'),
('-rank(signed_power(returns,3))','立方反转','market_cap'),
('rank(signed_power(ret_5d,0.5))','根号5d','market_cap'),
('-rank(signed_power(ret_20d,2))','平方反20d','market_cap'),
('group_neutralize(rank(ret_20d),market_cap)','组中动20d','market_cap'),
('group_neutralize(-rank(ret_5d),market_cap)','组中反5d','market_cap'),
('group_neutralize(-rank(vol_20d),market_cap)','组中低波','market_cap'),
('group_neutralize(rank(sharpe_60d),market_cap)','组中Sharpe','market_cap'),
('rank(ts_delta(volume,5))','量变5d','market_cap'),
('rank(ts_delta(volume,20))','量变20d','market_cap'),
('-rank(ts_delta(volume,60))','量变反60d','market_cap'),
('rank(ts_delta(close,10))','价变10d','market_cap'),
('rank(ts_delta(close,40))','价变40d','market_cap'),
('-rank(ts_delta(close,120))','价变反120d','market_cap'),
('rank(ts_rank(volume,20))','量时序排20','market_cap'),
('rank(ts_rank(vol_20d,60))','波时序排60','market_cap'),
('-rank(ts_decay_linear(returns,10))','衰减返10d','market_cap'),
('rank(ts_decay_linear(ret_20d,20))','衰减动20d','market_cap'),
('-rank(ts_decay_linear(volume,5))','衰减量反5d','market_cap'),
('rank(ret_20d)/(rank(vol_20d)+0.001)','动除波','market_cap'),
('-rank(ret_5d)*rank(vol_20d)','反乘波','market_cap'),
('rank(ret_20d)*rank(volume_trend_20d)','动乘量','market_cap'),
('-rank(returns)*rank(volume_profile_ratio)','日反乘量','market_cap'),
('-rank(close_location)*rank(vol_20d)','收位乘波','market_cap'),
('rank(sharpe_60d)/(abs(rank(max_dd_60d))+0.01)','Sharpe除回撤','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(op.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'A4.{i+1} {n} IC={r.get("pearson_ic",0):.4f} Sharpe={r.get("sharpe",0):.2f}')
    except Exception as ex: print(f'A4.{i+1} {n} FAIL: {str(ex)[:40]}')
    time.sleep(0.3)
print('Agent4 done')
