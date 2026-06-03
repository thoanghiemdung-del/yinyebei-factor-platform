#!/usr/bin/env python3
"""Lightweight mining — raw pipeline fields, no FactorComputer, low memory."""
import sys, os, json, sqlite3, datetime, gc, numpy as np
sys.path.insert(0, 'D:/yyb/模型'); sys.path.insert(0, 'D:/yyb/backtest_platform')
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

DB = 'backtest.db'
LOG = '../logs/light_mine.log'
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)
    with open(LOG, 'a', encoding='utf-8') as f: f.write(f"[{ts}] {msg}\n")

log("Lightweight init...")
p = DataPipeline(); e = BacktestEngine(p)
t0 = p.date_to_idx['2020-01-02']; t1 = min(p.date_to_idx['2023-12-29'] + 1, p.n_dates)
lt = p.fields['Label'][t0:t1]; ut = p.universe_mask[t0:t1]
adjf = np.clip(np.where(np.isnan(p.fields.get('I_D_ADJFACTOR', np.ones((p.n_dates, p.n_stocks)))), 1.0,
    p.fields.get('I_D_ADJFACTOR', np.ones((p.n_dates, p.n_stocks)))), 0.01, 100)
mcap = p.fields['I_D_CLOSE_ORI'] * adjf * p.fields.get('I_D_TOTAL_SHARES', np.ones((p.n_dates, p.n_stocks)))
mcap_train = mcap[t0:t1]
log(f"Ready: {p.n_dates}d x {p.n_stocks}s")

def evaluate(expr):
    try:
        factor = parse_expression(expr, p, None)
    except Exception:
        return None
    ft = factor[t0:t1]
    vf = ft[np.isfinite(ft)]
    if len(vf) < 970 * 100 or np.nanstd(vf) < 1e-8:
        return None
    for t in range(ft.shape[0]):
        valid = ~np.isnan(ft[t]) & ~np.isnan(mcap_train[t])
        if valid.sum() < 100:
            continue
        lm = np.log(np.maximum(mcap_train[t, valid], 1))
        gi = np.floor(np.digitize(lm, np.percentile(lm, np.arange(0, 101, 10))) / 10).astype(int)
        fv = ft[t, valid].copy()
        for g in np.unique(gi):
            gm = gi == g
            if gm.sum() >= 10:
                fv[gm] -= np.nanmean(fv[gm])
        ft[t, valid] = fv
    try:
        r = e.full_evaluation(ft, ut, lt)
    except Exception:
        return None
    ic = float(r.get('mean_pearson_ic', 0))
    if abs(ic) <= 0.01:
        return None
    de = []; dt = []
    for t in range(ft.shape[0]):
        f, l = ft[t], lt[t]
        valid = ut[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100:
            de.append(None); dt.append(set()); continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * 0.1))
        ti = np.argsort(fv)[-n_top:]
        de.append(float(np.nanmean(lv[ti]) - np.nanmean(lv)))
        dt.append(set(np.where(valid)[0][ti]))
    ea = np.array([x for x in de if x is not None])
    if len(ea) < 100:
        return None
    es = float(np.std(ea))
    ae = float(np.mean(ea)) * 250
    sh = ae / (es * np.sqrt(250) + 1e-10)
    if abs(sh) > 50:
        return None
    ts = []
    for t in range(1, len(dt)):
        p, c = dt[t - 1], dt[t]
        if len(p) > 0 and len(c) > 0:
            ts.append(1.0 - len(p & c) / max(len(p), len(c)))
    at = float(np.mean(ts)) if ts else 0.0
    if at < 0.01:
        return None
    cp = []; cum = 0.0
    for r in de:
        if r is not None:
            cum += r
        cp.append(float(cum * 100))
    return {'ic': ic, 'sh': sh, 'to': at, 'pnl': cp}

def load_existing():
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id,expression,pnl_json FROM alpha_history WHERE (type='alpha' OR type IS NULL) "
        "AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) > 0.01"
    ).fetchall()
    conn.close()
    exist, tested = [], set()
    for row in rows:
        tested.add(row['expression'].strip())
        try:
            pnl = json.loads(row['pnl_json'] or '[]')
            if len(pnl) < 20:
                continue
        except Exception:
            continue
        d = [pnl[i] - pnl[i - 1] for i in range(1, len(pnl))]
        exist.append({'id': row['id'], 'dailies': np.array(d)})
    return exist, tested

def save(expr, m):
    import uuid
    eid = str(uuid.uuid4())
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    clean = {}
    for k, v in [('pearson_ic', m['ic']), ('sharpe', m['sh']), ('turnover', m['to'])]:
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            v = None
        clean[k] = v
    conn = sqlite3.connect(DB)
    conn.execute(
        'INSERT INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json,max_corr) '
        'VALUES(?,?,?,?,?,?,?,?,?)',
        (eid, expr[:40], expr, ts, 'alpha', json.dumps(clean),
         json.dumps(m['pnl']), json.dumps([]), 0.0))
    conn.commit(); conn.close()

# Build factor list
BATCH = []
def a(e, d):
    BATCH.append((e, d))

# TS delta close
for w in range(1, 21):
    for sign in ['', '-']:
        a(f"{sign}rank(ts_delta(close, {w}))", f"delta_close_{w}")

# TS delta returns
for w in range(1, 21):
    for sign in ['', '-']:
        a(f"{sign}rank(ts_delta(close/open-1, {w}))", f"delta_ret_{w}")

# TS mean
for w in [3, 5, 10, 20, 40, 60]:
    for sign in ['', '-']:
        a(f"{sign}rank(ts_mean(close/open-1, {w}))", f"mean_ret_{w}")

# TS std
for w in [5, 10, 20, 40, 60]:
    a(f"-rank(ts_std(close/open-1, {w}))", f"std_ret_{w}")

# TS sum
for w in [3, 5, 8, 10, 15, 20]:
    a(f"-rank(ts_sum(close/open-1, {w}))", f"sum_ret_{w}")

# TS rank
for w in [5, 10, 20, 40, 60]:
    a(f"-rank(ts_rank(close/open-1, {w}))", f"rank_ret_{w}")

# TS decay
for w in [3, 5, 10, 20]:
    for sign in ['', '-']:
        a(f"{sign}rank(ts_decay_linear(close/open-1, {w}))", f"decay_ret_{w}")

# Volume patterns
for w in [3, 5, 7, 10, 20]:
    a(f"-rank(ts_delta(volume, {w}))", f"delta_vol_{w}")
    a(f"-rank(volume/ts_mean(volume, {w}))", f"vol_rel_{w}")

a("-rank((volume-ts_mean(volume,20))/ts_std(volume,20))", "vol_zscore")
a("-rank(ts_mean(volume,3)/ts_mean(volume,10))", "vol_ma_ratio")

# Price pattern
for expr, sign, desc in [
    ('(close-open)/open', '', 'daily_ret'),
    ('(close-open)/open', '-', 'daily_ret_rev'),
    ('(high-close)/(close-low+0.001)', '', 'sell_pressure'),
    ('(high-close)/(close-low+0.001)', '-', 'buy_support'),
    ('(close-open)/(high-low+0.001)', '', 'body_ratio'),
    ('(3*close-high-low-open)/(high-low+0.001)', '', 'wick_score'),
    ('(high-low)/ts_mean(high-low,20)', '', 'range_rel'),
]:
    a(f"{sign}rank({expr})", desc)

# Volume * return
for w in [3, 5, 10, 20]:
    for sign in ['', '-']:
        a(f"{sign}rank(ts_mean(volume*(close-open)/open, {w}))", f"vol_ret_{w}")

# Overnight / gap
a("rank((open-preclose)/preclose)", "overnight")
a("-rank((open-preclose)/preclose)", "overnight_rev")
a("-rank((close-open)/open-(open-preclose)/preclose)", "gap_diff")

# Cross-window
for sign in ['', '-']:
    a(f"{sign}rank(ts_delta(close, 5) * ts_delta(close, 20))", "delta5x20_close")
    a(f"{sign}rank(ts_delta(close/open-1, 5) / (ts_std(close/open-1, 5)+0.001))", "delta_ir5")
    a(f"{sign}rank(ts_mean((close-open)/open, 5)/ts_std((close-open)/open, 5))", "mean_ir5")

# Nested
a("-rank(ts_delta(ts_delta(close, 5), 5))", "nested_delta")

# Close vs MA
for sign in ['', '-']:
    a(f"{sign}rank(close/ts_mean(close, 20))", "close_ma20")

# High/low
a("rank((high+low)/2/close)", "hl_mid")
a("-rank((high+low)/2/close)", "hl_mid_rev")

log(f"Generated {len(BATCH)} factors")
existing, tested = load_existing()
candidates = [(e, d) for e, d in BATCH if e not in tested]
log(f"Existing: {len(existing)}, New: {len(candidates)}")

passed = 0
for i, (expr, desc) in enumerate(candidates):
    gc.collect()
    m = evaluate(expr)
    if m is None:
        continue
    nd = np.array([m['pnl'][j] - m['pnl'][j - 1] for j in range(1, len(m['pnl']))])
    max_c = 0.0
    for ef in existing:
        a = nd[-min(len(nd), len(ef['dailies'])):]
        b = ef['dailies'][-len(a):]
        vc = np.isfinite(a) & np.isfinite(b)
        if vc.sum() < 20:
            continue
        c = abs(float(np.corrcoef(a[vc], b[vc])[0, 1]))
        if np.isfinite(c) and c > max_c:
            max_c = c
    if max_c > 0.7:
        log(f"  SKIP max_c={max_c:.3f} IC={m['ic']:+.04f} | {desc}")
        continue
    save(expr, m)
    existing.append({'id': '', 'dailies': nd})
    passed += 1
    log(f"  KEPT #{len(existing)} IC={m['ic']:+.04f} S={m['sh']:.2f} TO={m['to']:.3f} corr={max_c:.2f} | {desc}")

log(f"DONE: +{passed} new, {len(existing)} total factors")
