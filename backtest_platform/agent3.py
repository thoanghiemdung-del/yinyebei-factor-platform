"""Agent 3: Volume-Price + Statistical + Cross-modal (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try: op.open(urllib.request.Request('http://127.0.0.1:5000/login', urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except: pass
f=[
('rank(volume_price_corr)','量价相关','market_cap'),
('-rank(volume_price_div)','量价背离','market_cap'),
('rank(volume_trend_20d)','量趋势','market_cap'),
('-rank(turnover_change)','换手减缓','market_cap'),
('-rank(adv5)','低短均量','market_cap'),
('-rank(adv20)','低长均量','market_cap'),
('rank(log_dollar_vol)','对数成交额','market_cap'),
('rank(dollar_volume)','成交额','market_cap'),
('rank(hit_rate_20d)','胜率20d','market_cap'),
('rank(hit_rate_60d)','胜率60d','market_cap'),
('-rank(max_ret_20d)','低彩票','market_cap'),
('rank(min_ret_20d)','高风险','market_cap'),
('-rank(skewness_60d)','低偏度60d','market_cap'),
('-rank(upside_vol_60d)','低上行波','market_cap'),
('rank(cumret_5d)','累积5d','market_cap'),
('rank(gap_momentum)','跳空动量','market_cap'),
('-rank(intraday_reversal)','日内不反转','market_cap'),
('rank(rev_vol_conf)','反转波确认','market_cap'),
('rank(mom_vol_conf)','动波确认','market_cap'),
('rank(mom_liquidity_adj)','动流动性调','market_cap'),
('rank(abnormal_vol_rev)','异常量反转','market_cap'),
('-rank(vol_ratio_20_60)','低波趋势','market_cap'),
('rank(ts_mean(volume,20))','均量20d','market_cap'),
('rank(ts_mean(turnover_rate,20))','均换手20d','market_cap'),
('-rank(ts_skew(returns,60))','时序低偏','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(op.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'A3.{i+1} {n} IC={r.get("pearson_ic",0):.4f} Sharpe={r.get("sharpe",0):.2f}')
    except Exception as ex: print(f'A3.{i+1} {n} FAIL: {str(ex)[:40]}')
    time.sleep(0.3)
print('Agent3 done')
