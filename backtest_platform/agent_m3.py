"""Agent M3: Volume + Statistical + Cross-modal (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[
('rank(volume_price_corr)','量价相关','market_cap'),
('-rank(volume_price_div)','量价背离','market_cap'),
('rank(volume_trend_20d)','量趋势','market_cap'),
('-rank(turnover_5d)','低换手','market_cap'),
('-rank(turnover_rate)','低换手率','market_cap'),
('-rank(volume_profile_ratio)','低量比','market_cap'),
('-rank(adv5)','低短均量','market_cap'),
('-rank(adv20)','低长均量','market_cap'),
('rank(log_dollar_vol)','对数成交额','market_cap'),
('rank(dollar_volume)','成交额','market_cap'),
('-rank(volume_breakout)','低量突破','market_cap'),
('-rank(turnover_change)','换手减缓','market_cap'),
('rank(hit_rate_20d)','高胜率20d','market_cap'),
('rank(hit_rate_60d)','高胜率60d','market_cap'),
('-rank(skewness_20d)','低偏度20d','market_cap'),
('-rank(skewness_60d)','低偏度60d','market_cap'),
('-rank(kurtosis_60d)','低峰度','market_cap'),
('-rank(max_ret_20d)','低彩票','market_cap'),
('rank(min_ret_20d)','高风险','market_cap'),
('-rank(upside_vol_60d)','低上行波','market_cap'),
('rank(cumret_5d)','累积5d','market_cap'),
('rank(rev_vol_conf)','反转波确认','market_cap'),
('rank(mom_vol_conf)','动波确认','market_cap'),
('rank(mom_liquidity_adj)','动流动性调','market_cap'),
('rank(abnormal_vol_rev)','异常量反转','market_cap'),
]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        ic=r.get('pearson_ic',0);sh=r.get('sharpe',0)
        print(f'M3.{i+1} {n} IC={ic:.4f} S={sh:.2f}')
    except Exception as ex:print(f'M3.{i+1} {n} FAIL:{str(ex)[:30]}')
print('Agent M3 done')
