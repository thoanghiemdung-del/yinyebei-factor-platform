"""Agent M5: ts_delta variants + signed_power combos (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[
('-rank(ts_delta(close,3))','价变3d反','market_cap'),
('-rank(ts_delta(close,10))','价变10d反','market_cap'),
('-rank(ts_delta(close,30))','价变30d反','market_cap'),
('-rank(ts_delta(close,60))','价变60d反','market_cap'),
('-rank(ts_delta(volume,3))','量变3d反','market_cap'),
('-rank(ts_delta(volume,10))','量变10d反','market_cap'),
('-rank(ts_delta(volume,30))','量变30d反','market_cap'),
('rank(ts_rank(volume,10))','量时序10','market_cap'),
('rank(ts_rank(volume,40))','量时序40','market_cap'),
('rank(ts_rank(returns,10))','收益时序10','market_cap'),
('rank(ts_rank(returns,40))','收益时序40','market_cap'),
('-rank(ts_decay_linear(volume,10))','衰减量10反','market_cap'),
('-rank(ts_decay_linear(volume,20))','衰减量20反','market_cap'),
('-rank(ts_decay_linear(returns,5))','衰减返5反','market_cap'),
('rank(ts_decay_linear(close,20))','衰减价20','market_cap'),
('-rank(ts_decay_linear(close,60))','衰减价60反','market_cap'),
('-rank(signed_power(ret_5d,1.5))','幂1.5反5d','market_cap'),
('-rank(signed_power(ret_20d,0.5))','根号反20d','market_cap'),
('rank(signed_power(returns,0.5))','根号收益','market_cap'),
('-rank(signed_power(vol_20d,2))','平方低波','market_cap'),
('-rank(signed_power(downside_vol_60d,0.5))','根号低下行','market_cap'),
('rank(ts_mean(returns,5))','均收益5d','market_cap'),
('rank(ts_mean(returns,20))','均收益20d','market_cap'),
('-rank(ts_mean(returns,60))','均收益60反','market_cap'),
('-rank(ts_kurt(returns,60))','峰度反','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'M5.{i+1} {n} IC={r.get("pearson_ic",0):.4f}')
    except Exception as ex:print(f'M5.{i+1} {n} FAIL')
print('Agent M5 done')
