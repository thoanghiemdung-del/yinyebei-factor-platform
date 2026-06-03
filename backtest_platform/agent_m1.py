"""Agent M1: Reversal + Intraday + Microstructure (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[
('-rank(returns)','1日反转','market_cap'),
('-rank(ret_5d)','5日反转','market_cap'),
('-rank(ret_10d)','10日反转','market_cap'),
('-rank(ret_20d)','20日反转','market_cap'),
('-rank(rev_overnight)','隔夜反转','none'),
('-rank(rev_vol_regime)','高波反转','market_cap'),
('-rank(signed_power(returns,2))','平方反转','market_cap'),
('-rank(first30_mom)','开盘30min反转','market_cap'),
('-rank(last30_mom)','尾盘30min反转','market_cap'),
('-rank(intraday_mom)','日内动量反转','market_cap'),
('-rank(am_pm_divergence)','上下行反转','market_cap'),
('-rank(intraday_reversal)','日内不反转','market_cap'),
('-rank(price_efficiency)','价格效率反转','market_cap'),
('-rank(vol_20d)','低波20d','market_cap'),
('-rank(vol_60d)','低波60d','market_cap'),
('-rank(downside_vol_60d)','低下行波','market_cap'),
('-rank(down_up_vol_ratio)','低上下波比','market_cap'),
('-rank(intraday_volatility)','低日内波','market_cap'),
('-rank(vol_ratio_5_20)','低波加速','market_cap'),
('-rank(vol_ratio_20_60)','低波趋势','market_cap'),
('-rank(ts_std(returns,20))','稳定收益20d','market_cap'),
('-rank(ts_std(returns,60))','稳定收益60d','market_cap'),
('-rank(amount_volatility)','低成交额波','market_cap'),
('-rank(volume_concentration)','低量集中','market_cap'),
('-rank(ts_delta(close,120))','价变反120d','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        ic=r.get('pearson_ic',0);sh=r.get('sharpe',0)
        print(f'M1.{i+1} {n} IC={ic:.4f} S={sh:.2f}')
    except Exception as ex:print(f'M1.{i+1} {n} FAIL:{str(ex)[:30]}')
print('Agent M1 done')
