#!/usr/bin/env python3
"""Continuous mining daemon — never stops, 5-min self-reports."""
import urllib.request, urllib.parse, json, sqlite3, datetime, time, random, sys, os, numpy as np
from http.cookiejar import CookieJar

API, DB = 'http://127.0.0.1:5000', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest.db')
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs', 'daemon.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def opener():
    cj = CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    o.open(urllib.request.Request(f'{API}/login',
        urllib.parse.urlencode({'username': 'admin', 'password': 'quant2026'}).encode()))
    return o

def bt(expr):
    o = opener()
    data = json.dumps({'expression': expr, 'neutralize': 'market_cap'}).encode()
    req = urllib.request.Request(f'{API}/api/backtest', data=data,
                                 headers={'Content-Type': 'application/json'})
    try:
        return json.loads(o.open(req, timeout=30).read().decode())
    except:
        return None

def tested(expr):
    c = sqlite3.connect(DB)
    r = c.execute("SELECT 1 FROM alpha_history WHERE trim(expression)=?",
                  (expr.strip(),)).fetchone()
    c.close()
    return r is not None

def save(expr, r):
    import uuid
    eid = str(uuid.uuid4())
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    cl = {}
    for k in ['pearson_ic', 'sharpe', 'turnover', 'fitness', 'annual_excess', 'max_drawdown']:
        v = r.get(k, 0)
        cl[k] = None if isinstance(v, float) and (v != v or v in [float('inf'), float('-inf')]) else v
    c = sqlite3.connect(DB)
    c.execute('INSERT INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json,max_corr,neutralization) '
              'VALUES(?,?,?,?,?,?,?,?,?,?)',
              (eid, expr[:40], expr, ts, 'alpha', json.dumps(cl),
               json.dumps(r.get('pnl_series', [])), json.dumps([]), 0.0, 'market_cap'))
    c.commit()
    c.close()

def count():
    c = sqlite3.connect(DB)
    n = c.execute("SELECT COUNT(*) FROM alpha_history WHERE (type='alpha' OR type IS NULL) "
                  "AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) > 0.01").fetchone()[0]
    c.close()
    return n

def flask_alive():
    try:
        urllib.request.urlopen(f'{API}/api/fields', timeout=5)
        return True
    except:
        return False

# Fields
M = ['intraday_volatility', 'price_efficiency', 'vwap_gap', 'volume_concentration',
     'close_location', 'upper_shadow_pct', 'lower_shadow_pct', 'morning_return',
     'afternoon_return', 'first30min_return', 'last30min_return', 'body_return', 'am_pm_divergence']
D = ['ret_5d', 'ret_20d', 'ret_60d', 'ret_120d_skip5', 'vol_20d', 'vol_60d',
     'sharpe_60d', 'skewness_60d', 'kurtosis_60d', 'amihud_20d', 'turnover_rate',
     'hit_rate_60d', 'max_dd_60d', 'rsi_14', 'bollinger_pos', 'beta_60d',
     'market_cap_rank', 'log_dollar_vol', 'volume_profile_ratio', 'volume_breakout',
     'turnover_change', 'downside_vol_60d', 'upside_vol_60d', 'cumret_5d',
     'close_vs_high_20d', 'rev_5d', 'rev_overnight', 'auction_return', 'amount_volatility']

R = 'close/open-1'
extra_patterns = [
    # ts_delta daily
    f"-rank(ts_delta(close, {w}))" for w in [2,3,4,5,6,7,8,9,10,12,15,20,30,40,60]
] + [
    f"-rank(ts_delta({R}, {w}))" for w in [2,3,4,5,6,7,8,9,10,12,15,20,30,40]
] + [
    f"-rank(ts_mean({R}, {w}))" for w in [3,5,8,10,12,15,20,30,40,60]
] + [
    f"-rank(ts_std({R}, {w}))" for w in [5,10,15,20,30,60]
] + [
    f"-rank(ts_sum({R}, {w}))" for w in [3,5,8,12,15,20]
] + [
    f"-rank(ts_delta(volume, {w}))" for w in [3,5,7,10,15,20]
] + [
    f"-rank(volume/ts_mean(volume, {w}))" for w in [3,5,10,20]
] + [
    "-rank((volume-ts_mean(volume,20))/ts_std(volume,20))",
    "-rank(ts_mean(volume,3)/ts_mean(volume,10))",
    "rank((close-open)/open)", "-rank((close-open)/open)",
    "rank((high-close)/(close-low+0.001))", "-rank((high-close)/(close-low+0.001))",
    "rank((close-open)/(high-low+0.001))",
    "rank((3*close-high-low-open)/(high-low+0.001))",
    "rank((open-preclose)/preclose)", "-rank((open-preclose)/preclose)",
    "-rank(ts_delta(close, 5) * ts_delta(close, 20))",
]

log("=" * 50 + " DAEMON START " + "=" * 50)

# Pre-warm Flask minute cache with ONE long-timeout request
log("Pre-warming Flask minute cache (6 min wait)...")
warmed = False
for attempt in range(3):
    o = opener()
    data = json.dumps({'expression': 'rank(close_location)', 'neutralize': 'market_cap'}).encode()
    req = urllib.request.Request(f'{API}/api/backtest', data=data, headers={'Content-Type': 'application/json'})
    try:
        r = json.loads(o.open(req, timeout=600).read().decode())
        if 'error' not in r:
            log(f"Minute cache WARM (attempt {attempt+1})")
            warmed = True
            break
        else:
            log(f"Warm attempt {attempt+1} returned error: {r.get('error','')[:60]}")
    except Exception as e:
        log(f"Warm attempt {attempt+1} failed: {str(e)[:60]}")
    time.sleep(5)

if not warmed:
    log("WARNING: Minute cache warm failed! Will retry in main loop.")

target = 300
last_report = datetime.datetime.now()
last_count = 0
round_num = 0
phase = 0  # 0=MxD, 1=MxM, 2=extras, 3=expanded

while True:
    round_num += 1
    if not flask_alive():
        log("FLASK DOWN - restarting...")
        import subprocess
        subprocess.Popen(['python', 'app.py'],
                         cwd=os.path.dirname(os.path.abspath(__file__)),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(20)
        continue

    n = count()
    if last_count == 0:
        last_count = n

    if n >= target:
        log(f"TARGET {target} REACHED! ({n})")
        time.sleep(60)
        continue

    # Generate batch
    batch = []
    if phase == 0:
        for mf in M:
            for df in D:
                e = f"rank({mf}) * rank({df})"
                if not tested(e):
                    batch.append((e, f"MxD:{mf[:8]}*{df[:8]}"))
    if not batch or phase >= 1:
        phase = 1
        for i, a in enumerate(M):
            for b in M[i + 1:]:
                e = f"rank({a}) * rank({b})"
                if not tested(e):
                    batch.append((e, f"MxM:{a[:8]}*{b[:8]}"))
    if not batch or phase >= 2:
        phase = 2
        for expr in extra_patterns:
            if not tested(expr):
                batch.append((expr, f"EXT:{expr[:30]}"))
    if not batch or phase >= 3:
        phase = 3
        # Signed power variants
        for f in ['vwap_gap', 'close_location', 'price_efficiency']:
            for p in [2, 3]:
                e = f"signed_power(rank({f}), {p})"
                if not tested(e):
                    batch.append((e, f"PWR:{f[:6]}^{p}"))
    if not batch:
        log(f"PHASE {phase}: all tested. Expanding...")
        phase += 1
        time.sleep(10)
        continue

    random.shuffle(batch)
    batch = batch[:12]

    p = 0
    for expr, desc in batch:
        r = bt(expr)
        if r is None or 'error' in r:
            continue
        ic = r.get('pearson_ic', 0)
        if abs(ic) <= 0.01:
            continue
        save(expr, r)
        p += 1
        log(f"  + IC={ic:+.04f} S={r.get('sharpe', 0):.2f} | {desc}")

    n = count()
    if round_num % 10 == 0:
        log(f"Round {round_num}: +{p} | {n}/{target}")

    # 5-minute report
    now = datetime.datetime.now()
    if (now - last_report).total_seconds() >= 300:
        delta = n - last_count
        perc = n / target * 100
        log(f"=== 5min REPORT: {last_count}->{n} (+{delta}) | {perc:.1f}% | Flask={'OK' if flask_alive() else 'DOWN'} ===")
        last_report = now
        last_count = n

        # Clean low-IC factors
        c = sqlite3.connect(DB)
        c.execute("DELETE FROM alpha_history WHERE (type='alpha' OR type IS NULL) "
                  "AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) <= 0.01")
        c.commit()
        c.close()

    time.sleep(2)
