#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Direct miner — calls backtest engine in-process, zero HTTP dependency."""
import sys, os, json, sqlite3, datetime, time, uuid, numpy as np

DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DIR)  # app.py, expression_parser
sys.path.append('D:/yyb/project')  # DataPipeline, BacktestEngine, FactorComputer (check before D:/yyb)
# Remove D:/yyb from path to avoid conflict with D:/yyb/project
while 'D:/yyb' in sys.path:
    sys.path.remove('D:/yyb')
sys.path.append('D:/yyb')  # fallback last

DB = os.path.join(DIR, 'backtest.db')
LOG = os.path.join(DIR, '..', 'logs', 'direct_miner.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

_seen = set()
_start_time = time.time()

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

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

def count_q():
    try:
        c = sqlite3.connect(DB, timeout=5)
        n = c.execute("SELECT COUNT(*) FROM alpha_history WHERE ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01").fetchone()[0]
        c.close()
        return n
    except: return -1

def save(expr, metrics):
    try:
        eid = str(uuid.uuid4())
        ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        cl = {}
        for k in ['pearson_ic','sharpe','turnover','fitness']:
            v = metrics.get(k, 0)
            cl[k] = None if isinstance(v, float) and (v != v or v in [float('inf'), float('-inf')]) else v
        c = sqlite3.connect(DB, timeout=5)
        c.execute("INSERT OR IGNORE INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json,max_corr,neutralization) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (eid, expr[:40], expr, ts, 'alpha', json.dumps(cl),
                   json.dumps(metrics.get('pnl_series', [])), json.dumps([]), 0.0, 'market_cap'))
        c.commit(); c.close()
    except sqlite3.IntegrityError: pass

# ========== Load engine once ==========
log("Loading DataPipeline (2-3 min)...")
from data_pipeline import DataPipeline
pipeline = DataPipeline()
log(f"Pipeline: {pipeline.n_dates}d x {pipeline.n_stocks}s")

log("Loading BacktestEngine...")
from backtest_framework import BacktestEngine
engine = BacktestEngine()

log("Loading FactorComputer...")
from factor_library import FactorComputer
fc = FactorComputer(pipeline)

log("Loading expression parser...")
from expression_parser import parse_expression

# Pre-compute training window
t0 = pipeline.date_to_idx['2020-01-02']
t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
label_train = pipeline.fields['Label'][t0:t1]
univ_train = pipeline.universe_mask[t0:t1]

# Pre-warm minute cache
log("Pre-warming minute cache (~5 min)...")
r = parse_expression('rank(close_location)', pipeline, fc)
log(f"Minute cache warm. close_location valid: {np.isfinite(r[t0:t1]).sum()}")

# Import backtest metrics
sys.path.insert(0, DIR)
from app import _compute_metrics_from_result

def bt_direct(expr):
    try:
        factor = parse_expression(expr, pipeline, fc)
        factor_train = factor[t0:t1]

        # Market cap neutralization
        adjf = np.clip(np.where(np.isnan(pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(factor_train[0]))), 1.0,
                                pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(factor_train[0]))), 0.01, 100)
        mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES', np.ones_like(factor_train[0]))
        mcap_train = mcap[t0:t1]
        for t in range(factor_train.shape[0]):
            valid = ~np.isnan(factor_train[t]) & ~np.isnan(mcap_train[t])
            if valid.sum() < 100: continue
            log_mcap = np.log(np.maximum(mcap_train[t, valid], 1))
            gids = np.floor(np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0,101,10)))/10).astype(int)
            fv = factor_train[t, valid].copy()
            for g in np.unique(gids):
                gm = gids == g
                if gm.sum() >= 10: fv[gm] -= np.nanmean(fv[gm])
            factor_train[t, valid] = fv

        result = engine.full_evaluation(factor_train, univ_train, label=label_train)
        metrics = _compute_metrics_from_result(factor_train, label_train, univ_train, result)
        return metrics
    except Exception as e:
        return {'error': str(e)[:100]}

# ========== Expression pool ==========
M = ['intraday_volatility','price_efficiency','vwap_gap','volume_concentration',
     'close_location','upper_shadow_pct','lower_shadow_pct','morning_return',
     'afternoon_return','first30min_return','last30min_return','body_return','am_pm_divergence']

def build_pool():
    out = []; s = set()
    def add(e, tag):
        e = e.strip()
        if e in s or db_has(e): return
        s.add(e); out.append((e, tag))
    # Singles
    for f in M:
        add(f"-rank({f})", f"Single:{f[:10]}")
    # MxM mul + sum
    for i,a in enumerate(M):
        for b in M[i+1:]:
            add(f"-rank({a}) * rank({b})", f"MxM:{a[:8]}x{b[:8]}")
            add(f"-rank({a}) - rank({b})", f"Sum:{a[:8]}+{b[:8]}")
    # ts_delta
    for f in M:
        for w in [3,5,10,20]:
            add(f"-rank(ts_delta({f},{w}))", f"tsD:{f[:8]}_{w}")
    # ts_rank
    for f in M:
        for w in [5,10,20]:
            add(f"-rank(ts_rank({f},{w}))", f"tsR:{f[:8]}_{w}")
    # signed_power
    for f in M:
        add(f"-signed_power(rank({f}),2)", f"sP:{f[:8]}^2")
    # 3-factor
    t6 = M[:6]
    for i,a in enumerate(t6):
        for j,b in enumerate(t6):
            if j<=i: continue
            for c in t6:
                if c==a or c==b or c<b: continue
                add(f"-rank({a}) * rank({b}) * rank({c})", f"M3:{a[:6]}x{b[:6]}x{c[:6]}")
    return out

# ========== Main ==========
log("=" * 50)
log(f"DIRECT MINER START | DB: {count_q()}/300")
log("=" * 50)

pool = build_pool()
log(f"Pool: {len(pool)} untested")

idx = 0
last_report = time.time()
last_count = count_q()
total_found = 0

while True:
    try:
        n = count_q()
        if n >= 300:
            log(f">>> TARGET 300: {n} <<<"); time.sleep(60); continue

        if idx >= len(pool):
            log("Pool exhausted, rebuilding...")
            pool = build_pool(); idx = 0
            log(f"Rebuilt: {len(pool)} untested")
            if len(pool) == 0:
                log("All tested. Sleeping 10min."); time.sleep(600)
            continue

        expr, tag = pool[idx]; idx += 1
        if db_has(expr): continue
        _seen.add(expr.strip())

        r = bt_direct(expr)
        if 'error' in r: continue

        ic = r.get('pearson_ic', 0)
        if abs(ic) <= 0.01: continue

        save(expr, r)
        total_found += 1
        sh = r.get('sharpe', 0); to = r.get('turnover', 0)
        log(f"+ IC={ic:+.04f} S={sh:.2f} TO={to:.2f} | {tag}")

        if time.time() - last_report > 300:
            n = count_q(); delta = n - last_count
            elapsed = (time.time() - _start_time) / 60
            log(f"=== 5min: {last_count}>{n} (+{delta}) | {n}/300 ({n*100//300}%) | {elapsed:.0f}min ===")
            last_report = time.time(); last_count = n

    except Exception as e:
        import traceback
        log(f"CRASH: {e}\n{traceback.format_exc()[-200:]}")
        time.sleep(10)
