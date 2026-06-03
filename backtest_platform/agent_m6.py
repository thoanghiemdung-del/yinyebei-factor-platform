"""Agent M6: Price patterns + doji + shadow combos (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[
('rank(lower_shadow)','长下影','market_cap'),('-rank(upper_shadow)','短上影','market_cap'),
('rank(body_ratio)','大实体','market_cap'),('-rank(gap_down)','低下跳','market_cap'),
('rank(gap_up)','上跳空','market_cap'),('-rank(doji_score)','非十字星','market_cap'),
('rank(close_vs_low_20d)','近20d低','market_cap'),('-rank(close_vs_high_20d)','远20d高','market_cap'),
('-rank(upper_shadow_pct)','低上影分','market_cap'),('rank(lower_shadow_pct)','高下影分','market_cap'),
('rank(gap_momentum)','跳空动量','market_cap'),('-rank(intraday_reversal)','日内不反转','market_cap'),
('rank(close_location)','收盘位置','market_cap'),('-rank(price_efficiency)','低价格效率','market_cap'),
('-rank(volume_concentration)','低量集中','market_cap'),('-rank(intraday_volatility)','低日内波','market_cap'),
('-rank(first30_mom)','开盘反转','market_cap'),('-rank(last30_mom)','尾盘反转','market_cap'),
('-rank(intraday_mom)','日内反转','market_cap'),('-rank(am_pm_divergence)','上下行反转','market_cap'),
('-rank(body_return)','实体反转','market_cap'),('-rank(morning_return)','上午反转','market_cap'),
('-rank(afternoon_return)','下午反转','market_cap'),('-rank(auction_return)','竞价反转','none'),
('-rank(vwap_gap)','VWAP反转','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'M6.{i+1} {n} IC={r.get("pearson_ic",0):.4f}')
    except:print(f'M6.{i+1} {n} FAIL')
print('Agent M6 done')
