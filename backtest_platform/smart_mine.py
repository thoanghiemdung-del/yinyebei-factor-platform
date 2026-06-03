#!/usr/bin/env python3
"""Smart miner — focuses on patterns proven to work, avoids user red lines."""
import urllib.request, urllib.parse, json, sqlite3, datetime, time, os, uuid
from http.cookiejar import CookieJar

API = 'http://127.0.0.1:5000'
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest.db')
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs', 'smart_mine.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

# In-memory set: all expressions ever evaluated this session (pass + fail)
_seen = set()

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

def db_tested(expr):
    key = expr.strip()
    if key in _seen:
        return 1  # already tested this session
    c = sqlite3.connect(DB)
    r = c.execute("SELECT 1 FROM alpha_history WHERE trim(expression)=?", (key,)).fetchone()
    c.close()
    if r is not None:
        _seen.add(key)
    return r

def bt(expr):
    o = opener()
    data = json.dumps({'expression': expr, 'neutralize': 'market_cap'}).encode()
    req = urllib.request.Request(f'{API}/api/backtest', data=data,
                                 headers={'Content-Type': 'application/json'})
    try:
        return json.loads(o.open(req, timeout=30).read().decode())
    except:
        return None

def save(expr, r):
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

M = ['intraday_volatility', 'price_efficiency', 'vwap_gap', 'volume_concentration',
     'close_location', 'upper_shadow_pct', 'lower_shadow_pct', 'morning_return',
     'afternoon_return', 'first30min_return', 'last30min_return', 'body_return', 'am_pm_divergence']

D = ['ret_5d', 'ret_20d', 'ret_60d', 'ret_120d_skip5', 'vol_20d', 'vol_60d',
     'sharpe_60d', 'skewness_60d', 'kurtosis_60d', 'amihud_20d', 'turnover_rate',
     'hit_rate_60d', 'max_dd_60d', 'rsi_14', 'bollinger_pos', 'beta_60d',
     'market_cap_rank', 'log_dollar_vol', 'volume_profile_ratio', 'volume_breakout',
     'turnover_change', 'downside_vol_60d', 'upside_vol_60d', 'cumret_5d',
     'close_vs_high_20d', 'rev_5d', 'rev_overnight', 'auction_return', 'amount_volatility']

def gen_all():
    """One-shot: return complete deduplicated list, then never regenerate."""
    exprs = []
    seen_local = set()

    def add(e, desc):
        e = e.strip()
        if e not in seen_local and not db_tested(e):
            seen_local.add(e)
            exprs.append((e, desc))

    # Phase 0: signed MxM pairs
    for i, a in enumerate(M):
        for b in M[i + 1:]:
            for sign_a in ['-', '']:
                for sign_b in ['-', '']:
                    if sign_a == '' and sign_b == '':
                        continue
                    e = f"{sign_a}rank({a}) * {sign_b}rank({b})"
                    e = e.replace('  ', ' ').strip()
                    add(e, f"MxM:{a[:8]}*{b[:8]}")

    # Phase 1: signed MxD cross
    for mf in M:
        for df in D:
            for sign_m in ['-', '']:
                for sign_d in ['-', '']:
                    if sign_m == '' and sign_d == '':
                        continue
                    e = f"{sign_m}rank({mf}) * {sign_d}rank({df})"
                    e = e.replace('  ', ' ').strip()
                    add(e, f"MxD:{mf[:8]}*{df[:8]}")

    # Phase 2: 3-factor minute combos
    top_m = ['intraday_volatility', 'vwap_gap', 'volume_concentration', 'close_location',
             'price_efficiency', 'body_return', 'lower_shadow_pct']
    for i, a in enumerate(top_m):
        for j, b in enumerate(top_m):
            if j <= i: continue
            for c in top_m:
                if c == a or c == b: continue
                if c < b: continue
                for signs in [('-rank', 'rank', 'rank'), ('-rank', '-rank', 'rank')]:
                    e = f"{signs[0]}({a}) * {signs[1]}({b}) * {signs[2]}({c})"
                    add(e, f"M3:{a[:6]}*{b[:6]}*{c[:6]}")

    # Phase 3: signed_power on minute fields
    for f in M:
        for p in [2, 3]:
            for sign in ['-', '']:
                e = f"{sign}signed_power(rank({f}), {p})"
                add(e, f"PWR:{sign}{f[:8]}^{p}")

    # Phase 4: ts_delta on minute fields
    for f in M:
        for w in [3, 5, 10, 15, 20]:
            for sign in ['-', '']:
                e = f"{sign}rank(ts_delta({f}, {w}))"
                add(e, f"TSD:{sign}{f[:8]}_d{w}")

    # Phase 5: ts_mean on minute fields
    for f in M:
        for w in [5, 10, 20]:
            for sign in ['-', '']:
                e = f"{sign}rank(ts_mean({f}, {w}))"
                add(e, f"TSM:{sign}{f[:8]}_m{w}")

    log(f"Generator: {len(exprs)} untested expressions across 5 phases")
    return exprs

log("=" * 50 + " SMART MINE START " + "=" * 50)
log("Checking Flask...")
if not flask_alive():
    log("ERROR: Flask not alive!")
    sys.exit(1)

log("Pre-warming minute cache...")
for attempt in range(2):
    r = bt('rank(close_location)')
    if r and 'error' not in r:
        log(f"Cache warm OK (attempt {attempt+1})")
        break
    log(f"Warm attempt {attempt+1}...")
    time.sleep(5)

# One-shot: generate complete list, never regenerate
queue = gen_all()
queue_idx = 0
target = 300
last_report = datetime.datetime.now()
last_count = count()
log(f"Starting: {last_count}/{target}, queue={len(queue)}")

while True:
    if not flask_alive():
        log("FLASK DOWN - restarting...")
        import subprocess
        subprocess.Popen(['python', 'app.py'],
                         cwd=os.path.dirname(os.path.abspath(__file__)),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(20)
        continue

    n = count()
    if n >= target:
        log(f"TARGET {target} REACHED! ({n})")
        time.sleep(60)
        continue

    if queue_idx >= len(queue):
        log("Queue exhausted. Sleeping, will re-scan for new patterns...")
        time.sleep(300)
        # Rebuild queue in case new patterns are available
        queue = gen_all()
        queue_idx = 0
        continue

    # Take next batch of 6
    batch = queue[queue_idx:queue_idx + 6]
    queue_idx += 6

    p = 0
    for expr, desc in batch:
        # Double-check: DB might have been updated by external process
        if db_tested(expr):
            continue
        _seen.add(expr.strip())

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
    if queue_idx % 60 == 0:
        log(f"Progress: {queue_idx}/{len(queue)} tested | {n}/{target} found")

    now = datetime.datetime.now()
    if (now - last_report).total_seconds() >= 300:
        delta = n - last_count
        perc = n / target * 100
        log(f"=== 5min: {last_count}->{n} (+{delta}) | {perc:.1f}% | Flask={'OK' if flask_alive() else 'DOWN'} ===")
        last_report = now
        last_count = n

        # Clean sub-threshold entries
        c = sqlite3.connect(DB)
        c.execute("DELETE FROM alpha_history WHERE (type='alpha' OR type IS NULL) "
                  "AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) <= 0.01")
        c.commit()
        c.close()

    time.sleep(2)
