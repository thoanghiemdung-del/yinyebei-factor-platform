#!/usr/bin/env python3
"""Continuous minute-based factor mining. Never stops. 15-min self-checks."""
import urllib.request, urllib.parse, json, sqlite3, datetime, time, sys, numpy as np
from http.cookiejar import CookieJar

API, DB = 'http://127.0.0.1:5000', 'backtest.db'
LOG = '../logs/continuous.log'

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

def flask_alive():
    try:
        urllib.request.urlopen(f'{API}/api/fields', timeout=5)
        return True
    except:
        return False

def bt(expr):
    o = opener()
    data = json.dumps({'expression': expr, 'neutralize': 'market_cap'}).encode()
    req = urllib.request.Request(f'{API}/api/backtest', data=data,
                                 headers={'Content-Type': 'application/json'})
    try:
        return json.loads(o.open(req, timeout=60).read().decode())
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

def load_dailies():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rs = c.execute(
        "SELECT id, pnl_json FROM alpha_history WHERE (type='alpha' OR type IS NULL) "
        "AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) > 0.01"
    ).fetchall()
    c.close()
    xs = []
    for r in rs:
        try:
            p = json.loads(r['pnl_json'] or '[]')
            if len(p) < 20:
                continue
        except:
            continue
        xs.append({'id': r['id'], 'd': np.array([p[i] - p[i - 1] for i in range(1, len(p))])})
    return xs

def corr_check(nd, existing):
    mc = 0.0
    for ef in existing:
        a = nd[-min(len(nd), len(ef['d'])):]
        b = ef['d'][-len(a):]
        vc = np.isfinite(a) & np.isfinite(b)
        if vc.sum() < 20:
            continue
        c = abs(float(np.corrcoef(a[vc], b[vc])[0, 1]))
        if np.isfinite(c) and c > mc:
            mc = c
    return mc

# ---- Factor pool ----
# Minute fields
M = ['intraday_volatility', 'price_efficiency', 'vwap_gap', 'volume_concentration',
     'close_location', 'upper_shadow_pct', 'lower_shadow_pct', 'morning_return',
     'afternoon_return', 'first30min_return', 'last30min_return', 'body_return', 'am_pm_divergence']

# Daily pre-computed fields (via FactorComputer)
D = ['ret_5d', 'ret_20d', 'ret_60d', 'ret_120d_skip5', 'vol_20d', 'vol_60d',
     'sharpe_60d', 'skewness_60d', 'kurtosis_60d', 'amihud_20d', 'turnover_rate',
     'hit_rate_60d', 'max_dd_60d', 'rsi_14', 'bollinger_pos', 'beta_60d',
     'market_cap_rank', 'log_dollar_vol', 'volume_profile_ratio', 'volume_breakout']

def make_batch(size=15):
    """Generate untested minute-based factors."""
    batch = []
    # All M×D crosses (minute × daily)
    for mf in M:
        for df in D:
            e = f"rank({mf}) * rank({df})"
            if not tested(e):
                batch.append((e, f"{mf[:8]}x{df[:8]}"))
    # All M×M crosses
    for i, a in enumerate(M):
        for b in M[i + 1:]:
            e = f"rank({a}) * rank({b})"
            if not tested(e):
                batch.append((e, f"{a[:8]}x{b[:8]}"))
    # Signed power on key minute fields
    for f in ['vwap_gap', 'close_location', 'price_efficiency']:
        for pwr in [2, 3]:
            e = f"signed_power(rank({f}), {pwr})"
            if not tested(e):
                batch.append((e, f"pwr({f[:6]},{pwr})"))
    # ts_delta on minute fields
    for f in ['close_location', 'vwap_gap', 'price_efficiency']:
        for w in [3, 5]:
            e = f"rank(ts_delta({f}, {w}))"
            if not tested(e):
                batch.append((e, f"td({f[:6]},{w})"))
    import random
    random.shuffle(batch)
    return batch[:size]


log("=" * 50 + " CONTINUOUS MINE START " + "=" * 50)
target = 300
last_check = datetime.datetime.now()
last_count = 0

while True:
    # Health check
    if not flask_alive():
        log("FLASK DOWN - restarting...")
        import subprocess, os
        subprocess.Popen(['python', 'app.py'],
                         cwd=os.path.dirname(os.path.abspath(__file__)),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(15)
        if flask_alive():
            log("Flask restarted")
            # Wait for engine warm
            time.sleep(180)
        else:
            log("Flask still down, retrying...")
            time.sleep(30)
            continue

    # Get current count
    xs = load_dailies()
    n = len(xs)
    if last_count == 0:
        last_count = n
    log(f"Status: {n}/{target} factors")

    # Generate and test batch
    batch = make_batch(12)
    if not batch:
        log("No new candidates - expanding search...")
        time.sleep(30)
        continue

    passed = 0
    for expr, desc in batch:
        r = bt(expr)
        if r is None or 'error' in r:
            continue
        ic = r.get('pearson_ic', 0)
        if abs(ic) <= 0.01:
            continue
        pnl = r.get('pnl_series', [])
        if len(pnl) < 50:
            continue
        nd = np.array([pnl[i] - pnl[i - 1] for i in range(1, len(pnl))])
        mc = corr_check(nd, xs)
        if mc > 0.7:
            continue
        save(expr, r)
        xs.append({'id': '', 'd': nd})
        passed += 1
        log(f"  + IC={ic:+.04f} S={r.get('sharpe', 0):.2f} | {desc}")

    n = len(xs)
    log(f"  Batch: +{passed} | {n}/{target}")

    # 15-minute self-check
    now = datetime.datetime.now()
    if (now - last_check).total_seconds() >= 900:
        delta = n - last_count
        log(f"=== 15min CHECK: {last_count}->{n} (+{delta}) ===")
        last_check = now
        last_count = n

        # Clean low-IC
        c = sqlite3.connect(DB)
        c.execute("DELETE FROM alpha_history WHERE (type='alpha' OR type IS NULL) "
                  "AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) <= 0.01")
        c.commit()
        clean = c.execute("SELECT COUNT(*) FROM alpha_history WHERE (type='alpha' OR type IS NULL)").fetchone()[0]
        c.close()
        log(f"  Clean: {clean} factors")

        # If no progress, expand
        if delta == 0:
            log("  WARNING: 0 progress in 15min! Expanding patterns...")
            D.append('ret_40d')
            D.append('vol_40d')
            D.append('downside_vol_60d')
            D.append('upside_vol_60d')

    time.sleep(2)
