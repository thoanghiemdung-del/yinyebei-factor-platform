"""Auto-clean: delete factors with |IC| < 0.01 every 2 minutes."""
import urllib.request, http.cookiejar, json, time
while True:
    try:
        cj=http.cookiejar.CookieJar();o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        try:o.open(urllib.request.Request('http://127.0.0.1:5000/login',urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
        except:pass
        resp=o.open('http://127.0.0.1:5000/api/alpha/history')
        recs=json.loads(resp.read().decode()).get('records',[])
        deleted=0;kept=0
        for r in recs:
            ic=abs(r.get('metrics',{}).get('pearson_ic',0))
            if ic<0.01:
                try:o.open(urllib.request.Request('http://127.0.0.1:5000/api/alpha/history/'+r['id'],method='DELETE'));deleted+=1
                except:pass
            else:kept+=1
        if deleted:print(f'[Clean] Deleted {deleted} | Kept {kept}')
    except Exception as e:print(f'[Clean] Error: {e}')
    time.sleep(120)
