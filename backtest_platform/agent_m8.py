"""Agent M8: Pure single-factor diversity (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[
# Volatility family - all windows
('-rank(vol_10d)','低波10d','market_cap'),('-rank(vol_40d)','低波40d','market_cap'),
# Downside risk variants
('-rank(ts_min(returns,20))','低20d最差','market_cap'),('-rank(ts_min(returns,60))','低60d最差','market_cap'),
# Volume-at-price
('rank(open_vol_ratio)','开盘量占比','market_cap'),('-rank(close_vol_ratio)','低收盘量','market_cap'),
# Trend strength
('-rank(ts_argmax(close,20))','远离20d高','market_cap'),('rank(ts_argmin(close,20))','近20d低','market_cap'),
# Gap analysis
('-rank(auction_return)','竞价反转','none'),('-rank(abs(auction_return))','低竞价跳空','market_cap'),
# Cross-sectional stability
('-rank(ts_std(rank(close),20))','排名稳定20','market_cap'),('-rank(ts_std(rank(close),60))','排名稳定60','market_cap'),
# Volume stability
('-rank(ts_std(volume,20))','量稳定20','market_cap'),('-rank(ts_std(volume,60))','量稳定60','market_cap'),
# Reversal-momentum hybrid
('-rank(ret_5d)+rank(ret_60d)','反5加动60','market_cap'),('-rank(ret_10d)+rank(ret_40d)','反10加动40','market_cap'),
# Vol-of-vol
('-rank(ts_std(vol_20d,60))','低波之波','market_cap'),
# Price acceleration
('-rank(ts_delta(ret_20d,20))','动量减速','market_cap'),('rank(ts_delta(ret_5d,5))','反转加速','market_cap'),
# Volume confirmation of reversal
('-rank(ret_5d)*rank(volume_profile_ratio)','反乘量比','market_cap'),
('-rank(ret_20d)*rank(volume_breakout)','反20乘量突','market_cap'),
# Risk-adjusted returns
('rank(sharpe_20d)/(rank(vol_20d)+0.01)','Sharpe除波','market_cap'),
('-rank(max_dd_60d)*rank(sharpe_60d)','低回撤乘Sharpe','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'M8.{i+1} {n} IC={r.get("pearson_ic",0):.4f}')
    except:print(f'M8.{i+1} {n} FAIL')
print('Agent M8 done')
