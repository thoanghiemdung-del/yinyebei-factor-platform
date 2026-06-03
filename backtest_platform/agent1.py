"""Agent 1: Reversal + Low Vol + Liquidity (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: op.open(urllib.request.Request('http://127.0.0.1:5000/login', urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
f=[
('-rank(returns)','1日反转','market_cap'),
('-rank(ret_5d)','5日反转','market_cap'),
('-rank(ret_10d)','10日反转','market_cap'),
('-rank(ret_20d)','20日反转','market_cap'),
('-rank(ret_40d)','40日反转','market_cap'),
('-rank(ts_delta(close,5))','5日价变反转','market_cap'),
('-rank(ts_delta(close,20))','20日价变反转','market_cap'),
('-rank(rev_overnight)','隔夜反转','none'),
('-rank(rev_vol_regime)','高波反转','market_cap'),
('-rank(vol_5d)','低波5d','market_cap'),
('-rank(vol_20d)','低波20d','market_cap'),
('-rank(vol_60d)','低波60d','market_cap'),
('-rank(vol_120d)','低波120d','market_cap'),
('-rank(downside_vol_60d)','低下行波','market_cap'),
('-rank(down_up_vol_ratio)','低上下波比','market_cap'),
('-rank(vol_ratio_5_20)','低波加速','market_cap'),
('rank(amihud_20d)','Amihud流动性','market_cap'),
('-rank(turnover_5d)','低换手5d','market_cap'),
('-rank(turnover_rate)','低换手率','market_cap'),
('-rank(volume_profile_ratio)','低量比','market_cap'),
('-rank(volume_breakout)','低量突破','market_cap'),
('-rank(ts_std(returns,20))','稳定收益20d','market_cap'),
('-rank(ts_std(returns,60))','稳定收益60d','market_cap'),
('-rank(amount_volatility)','低成交额波','market_cap'),
('-rank(signed_power(returns,2))','极端反转','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(op.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'A1.{i+1} {n} IC={r.get("pearson_ic",0):.4f} Sharpe={r.get("sharpe",0):.2f}')
    except Exception as ex: print(f'A1.{i+1} {n} FAIL: {str(ex)[:40]}')
    time.sleep(0.3)
print('Agent1 done')
