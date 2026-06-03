#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minute-field miner with persistent dedup pool."""
import urllib.request, urllib.parse, json, sqlite3, datetime, time, os, uuid, sys
from http.cookiejar import CookieJar

API = 'http://127.0.0.1:5000'
DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DIR, 'backtest.db')
LOG = os.path.join(DIR, '..', 'logs', 'miner.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

_seen = set()
_SEEN_FILE = os.path.join(os.path.dirname(LOG), 'miner_seen.txt')

def _load_seen():
    try:
        if os.path.exists(_SEEN_FILE):
            with open(_SEEN_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    _seen.add(line.strip())
    except: pass

def _save_seen():
    try:
        with open(_SEEN_FILE, 'w', encoding='utf-8') as f:
            for e in list(_seen)[-50000:]:
                f.write(e + '\n')
    except: pass

_load_seen()
_start_time = time.time()

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

def db_has(expr):
    key = expr.strip()
    if key in _seen: return True
    try:
        c = sqlite3.connect(DB, timeout=5)
        r = c.execute("SELECT 1 FROM alpha_history WHERE trim(expression)=?", (key,)).fetchone()
        c.close()
        if r: _seen.add(key)
        return r is not None
    except: return False

def bt(expr, timeout=300):
    try:
        o = opener()
        data = json.dumps({'expression': expr, 'neutralize': 'market_cap'}).encode()
        req = urllib.request.Request(f'{API}/api/backtest', data=data,
                                     headers={'Content-Type': 'application/json'})
        return json.loads(o.open(req, timeout=timeout).read().decode())
    except: return None

def save(expr, r):
    try:
        eid = str(uuid.uuid4())
        ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        cl = {}
        for k in ['pearson_ic','sharpe','turnover','fitness']:
            v = r.get(k, 0)
            cl[k] = None if isinstance(v, float) and (v != v or v in [float('inf'), float('-inf')]) else v
        c = sqlite3.connect(DB, timeout=5)
        c.execute("INSERT OR IGNORE INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json,max_corr,neutralization) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (eid, expr[:40], expr, ts, 'alpha', json.dumps(cl),
                   json.dumps(r.get('pnl_series', [])), json.dumps([]), 0.0, 'market_cap'))
        c.commit(); c.close()
    except sqlite3.IntegrityError: pass

def count_q():
    try:
        c = sqlite3.connect(DB, timeout=5)
        n = c.execute("SELECT COUNT(*) FROM alpha_history WHERE (type='alpha' OR type IS NULL) AND ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01").fetchone()[0]
        c.close()
        return n
    except: return -1

def flask_ok():
    try:
        urllib.request.urlopen(f'{API}/api/fields', timeout=5)
        return True
    except: return False

def restart_flask():
    import subprocess
    subprocess.Popen(['python', 'app.py'], cwd=DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(10)
    return flask_ok()

# ============ Minute fields ============
M = ['intraday_volatility','price_efficiency','vwap_gap','volume_concentration',
     'close_location','upper_shadow_pct','lower_shadow_pct','morning_return',
     'afternoon_return','first30min_return','last30min_return','body_return','am_pm_divergence']

def build_pool():
    """Generate all untested minute-field expressions. Returns list of (expr, tag, econ)."""
    out = []; s = set()
    def add(e, tag, econ=''):
        e = e.strip()
        if e in s or db_has(e): return
        s.add(e); out.append((e, tag, econ))

    # Single-field signals (13)
    singles = [
        ("-rank(intraday_volatility)", "低波异象", "高日内波动的股票未来收益更低"),
        ("-rank(vwap_gap)", "VWAP回归", "收盘价高于VWAP后均值回复"),
        ("-rank(close_location)", "收盘动量", "高位收盘买方控盘短期延续"),
        ("-rank(volume_concentration)", "量集反转", "大单集中后散户跟进反转"),
        ("-rank(price_efficiency)", "效率反转", "过高趋势效率后不可持续"),
        ("-rank(upper_shadow_pct)", "上影卖压", "冲高回落反映卖盘压力"),
        ("rank(lower_shadow_pct)", "下影支撑", "探底回升反映买盘支撑"),
        ("-rank(morning_return)", "早盘反转", "开盘过度反应后日内修正"),
        ("-rank(afternoon_return)", "尾盘动量", "尾盘机构定价方向延续"),
        ("-rank(first30min_return)", "开盘冲击", "开盘30min过度冲击后回复"),
        ("-rank(last30min_return)", "尾盘反转", "尾盘拉抬/打压次日反转"),
        ("-rank(body_return)", "全日反转", "全日方向性移动后均值回复"),
        ("-rank(am_pm_divergence)", "午间背离", "上午x下午方向背离预示反转"),
    ]
    for e, t, econ in singles: add(e, t, econ)

    # ALL MxM pairs — multiplication (78 pairs x 1 sign variant each)
    for i, a in enumerate(M):
        for b in M[i+1:]:
            add(f"-rank({a}) * rank({b})", f"MxM:{a[:8]}x{b[:8]}", f"{a[:10]}与{b[:10]}交互")
            add(f"-rank({a}) - rank({b})", f"Sum:{a[:8]}+{b[:8]}", f"{a[:10]}+{b[:10]}双信号")

    # ts_delta on ALL minute fields (4 windows each = 52 exprs)
    for f in M:
        for w in [3, 5, 10, 20]:
            add(f"-rank(ts_delta({f}, {w}))", f"tsD:{f[:10]}_{w}", f"{f[:10]}的{w}日时序变化")

    # ts_rank on ALL minute fields (3 windows each = 39 exprs)
    for f in M:
        for w in [5, 10, 20]:
            add(f"-rank(ts_rank({f}, {w}))", f"tsR:{f[:10]}_{w}", f"{f[:10]}的{w}日滚动排名")

    # signed_power on ALL minute fields (power=2, 13 exprs)
    for f in M:
        add(f"-signed_power(rank({f}), 2)", f"sP:{f[:10]}^2", f"{f[:10]}信号增强")

    # ---- Expanded patterns for better coverage ----
    # ts_corr between minute pairs
    for i, a in enumerate(M[:6]):
        for b in M[i+1:6]:
            for w in [10, 20]:
                add(f"-rank(ts_corr({a}, {b}, {w}))", f"tsCorr:{a[:6]}x{b[:6]}_{w}", f"{a[:6]}与{b[:6]}的{w}日滚动相关")

    # Ratio patterns: minute field / another minute field
    for i, a in enumerate(M[:8]):
        for b in M[i+1:8]:
            add(f"-rank({a} / ({b} + 1e-10))", f"Ratio:{a[:6]}/{b[:6]}", f"{a[:6]}相对{b[:6]}的比值")

    # Signed-power enhanced cross: -signed_power(rank(A), 2) * rank(B)
    for i, a in enumerate(M[:6]):
        for b in M[i+1:6]:
            add(f"-signed_power(rank({a}), 2) * rank({b})", f"sP2xM:{a[:6]}x{b[:6]}", f"{a[:6]}信号增强x{b[:6]}")

    # Volatility-scaled: divide by ts_std(returns)
    for f in M[:8]:
        for w in [10, 20, 60]:
            add(f"-rank({f} / (ts_std(returns, {w}) + 1e-10))", f"VolScl:{f[:8]}_s{w}", f"{f[:8]}按{w}日波动缩放")

    # ts_decay_linear weighted signal
    for f in M[:8]:
        for w in [10, 20]:
            add(f"-rank(ts_decay_linear({f}, {w}))", f"Decay:{f[:8]}_{w}", f"{f[:8]}的{w}日线性衰减加权")

    # Delay patterns: previous-day minute signal
    for f in M[:8]:
        add(f"-rank(ts_delay({f}, 1))", f"Delay1:{f[:8]}", f"{f[:8]}滞后1日信号")

    # Winsorized signals
    for f in M[:8]:
        add(f"-rank(winsorize({f}, 3))", f"Winsor:{f[:8]}", f"{f[:8]}去极值(3σ)")

    # Exponential of rank signals
    for f in M[:6]:
        add(f"-exp(rank({f}))", f"Exp:{f[:8]}", f"{f[:8]}的指数变换")

    # 3-factor combos (top 7 fields, combination)
    top7 = M[:7]
    for i, a in enumerate(top7):
        for j, b in enumerate(top7):
            if j <= i: continue
            for c in top7:
                if c == a or c == b or c < b: continue
                add(f"-rank({a}) * rank({b}) * rank({c})", f"M3:{a[:6]}x{b[:6]}x{c[:6]}", "三重独立信号交叉验证")

    return out

# ============ Main ============
log("=" * 50)
log("MINER START")
log(f"Loaded {len(_seen)} previously-seen expressions")
log("=" * 50)

if not flask_ok():
    log("Flask DOWN, restarting...")
    restart_flask()

pool = build_pool()
log(f"Pool: {len(pool)} untested minute-only expressions | Start: {count_q()}/300")

# Pre-warm minute cache via actual backtest (more reliable than debug endpoint)
log("Pre-warming minute cache via backtest (up to 10 min)...")
for warm_try in range(3):
    try:
        # Use unique expression to avoid UNIQUE constraint on existing entries
        r = bt("-rank(intraday_volatility)", timeout=600)
        if r and 'pearson_ic' in r:
            log(f"Minute cache WARM (attempt {warm_try+1}, IC={r.get('pearson_ic',0):+.4f})")
            break
        else:
            log(f"Warm attempt {warm_try+1}: backtest failed, retrying...")
    except Exception as e:
        log(f"Warm attempt {warm_try+1} failed: {str(e)[:60]}")
        if warm_try == 2:
            log("WARNING: Cache warm failed, will try individual backtests with 600s timeout")

idx = 0
last_report = time.time()
last_count = count_q()
flask_restarts = 0
total_found = 0

while True:
    try:
        if not flask_ok():
            log(f"Flask DOWN (restart #{flask_restarts+1})")
            if restart_flask():
                log("Flask restarted OK")
                flask_restarts += 1
            else:
                log("Flask restart FAILED"); time.sleep(30)
            continue

        n = count_q()
        if n >= 300:
            log(f">>> TARGET 300: {n} <<<"); time.sleep(60); continue

        if idx >= len(pool):
            _save_seen()
            log("Pool exhausted, rebuilding...")
            pool = build_pool()
            idx = 0
            log(f"Rebuilt: {len(pool)} untested")
            if len(pool) == 0:
                log("ALL expressions tested! Will retry in 10min.")
                time.sleep(600); continue
            continue

        expr, tag, econ = pool[idx]; idx += 1

        if db_has(expr):
            if idx % 100 == 0:
                log(f"  Skipping (in DB): {tag}")
            continue
        _seen.add(expr.strip())

        r = bt(expr, timeout=60)
        if r is None:
            if idx % 20 == 0:
                log(f"  bt None: {tag}")
            continue
        if 'error' in r:
            continue

        ic = r.get('pearson_ic', 0) or 0
        if abs(ic) <= 0.01: continue

        save(expr, r)
        total_found += 1
        sh = r.get('sharpe', 0); to = r.get('turnover', 0)
        log(f"+ IC={ic:+.04f} S={sh:.2f} TO={to:.2f} | {tag}")

        if len(_seen) % 50 == 0:
            _save_seen()

        if time.time() - last_report > 300:
            n = count_q(); delta = n - last_count
            elapsed = (time.time() - _start_time) / 60
            log(f"=== 5min: {last_count}>{n} (+{delta}) | {n}/300 ({n*100//300}%) | {elapsed:.0f}min | F={'OK' if flask_ok() else 'DOWN'} ===")
            last_report = time.time(); last_count = n
            _save_seen()

        time.sleep(3)  # Rate limit to prevent Flask thread exhaustion

    except Exception as e:
        log(f"CRASH: {e}")
        _save_seen()
        time.sleep(10)
