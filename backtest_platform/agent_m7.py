"""Agent M7: windows sweep (25 factors)"""
import urllib.request, http.cookiejar, json, time
cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
except:pass
f=[]
for w in [5,10,20,30,40,50,60,80,100,120]:
    f.append((f'-rank(ts_delta(close,{w}))',f'{w}d价变反转','market_cap'))
    f.append((f'-rank(ts_std(returns,{w}))',f'{w}d稳定','market_cap'))
    f.append((f'-rank(ts_mean(volume,{w}))',f'{w}d均量反','market_cap'))
f=f[:25]
for i,(e,n,neut) in enumerate(f):
    d=json.dumps({'expression':e,'neutralize':neut}).encode()
    try:
        r=json.loads(o.open(urllib.request.Request('http://127.0.0.1:5000/api/backtest',data=d,headers={'Content-Type':'application/json'})).read().decode())
        print(f'M7.{i+1} {n} IC={r.get("pearson_ic",0):.4f}')
    except:print(f'M7.{i+1} {n} FAIL')
print('Agent M7 done')
