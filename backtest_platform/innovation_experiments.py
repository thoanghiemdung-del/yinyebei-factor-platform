"""
Innovation experiments — nesting, LGB, greedy correlation filtering.
Runs via inline path for speed. Memory-managed.
"""
import sys, os, json, time, sqlite3, gc, statistics
from datetime import datetime
from collections import Counter
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, _add_to_history, DB_PATH

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiment_results')
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# Economic groups
_GROUPS = [
    ('momentum', ['momentum','mom_','trend','breakout','ret_20','ret_60','ret_120','cumret','ts_delta','slope','accel','relative_strength','new_high','ma_gap','ema','macd','price_strength']),
    ('reversal', ['reversal','rev_','mean_reversion','overreaction','gap','overnight','rsi','stoch','-rank(returns','-returns','-ret_','close_position','close_location','short_term_reversal']),
    ('volatility', ['volatility','realized_vol','downside','std','atr','range','high_low','skew','kurt','drawdown','max_dd','max_drawdown','beta','risk','entropy','dispersion','boll']),
    ('liquidity', ['turnover','volume','amount','dollar','liquidity','amihud','adv','money_flow','flow','trade_count','volume_profile']),
    ('microstructure', ['minute','intraday','auction','vwap','open_','close_','high_','low_','shadow','wick','body','kline','bar_','smart_money','imbalance','impact']),
]
def gk(expr):
    el = expr.lower(); scores = [(len(set(t for t in terms if t in el)), key) for key, terms in _GROUPS]
    scores = [(s,k) for s,k in scores if s>0]
    if not scores: return 'unknown'
    scores.sort(reverse=True)
    if len(scores)>1 and scores[1][0]>=max(1,scores[0][0]-1): return 'mixed'
    return scores[0][1]

def get_factors():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""SELECT id, expression, metrics_json FROM alpha_history
        WHERE json_extract(metrics_json, '$.is_pearson_ic') > 0.01
          AND (type IS NULL OR type != 'superalpha')
        ORDER BY json_extract(metrics_json, '$.is_pearson_ic') DESC""").fetchall()
    conn.close()
    return [{ 'id':r[0], 'expression':r[1], 'is_ic':json.loads(r[2]).get('is_pearson_ic',0),
              'is_sharpe':json.loads(r[2]).get('is_sharpe',0), 'group':gk(r[1]) } for r in rows]

def compute_combo(expressions, weights, method='equal'):
    """Inline OOS combo with market cap neutralization."""
    with flask_app.app_context():
        p, e, f = get_engine()
        dk = sorted(p.date_to_idx.keys())
        t0 = None
        for d in dk:
            if d >= '2023-01-01': t0 = p.date_to_idx[d]; break
        t1 = min(p.date_to_idx['2023-12-29'] + 1, p.n_dates)
        lbl = p.fields['Label'][t0:t1]; univ = p.universe_mask[t0:t1]
        nd, ns = lbl.shape
        cb = np.zeros((nd, ns), dtype=np.float32); ws = np.zeros((nd, ns), dtype=np.float32); vc = 0
        for expr in expressions:
            try:
                fa = parse_expression(expr, p, f); ft = np.asarray(fa[t0:t1], dtype=np.float32); del fa
                fm = np.nanmean(ft, axis=1, keepdims=True); fs = np.nanstd(ft, axis=1, keepdims=True) + 1e-10
                fz = (ft - fm) / fs; v = np.isfinite(fz)
                if not np.any(v): del ft, fz, v, fm, fs; continue
                w = float(weights[expressions.index(expr)])
                cb[v] += w * fz[v]; ws[v] += w; vc += 1
                del ft, fz, v, fm, fs
            except: continue
        vw = np.isfinite(ws) & (np.abs(ws) > 1e-12)
        if vc<1 or not np.any(vw): return None
        cb[vw] /= ws[vw]; cb[~vw] = np.nan; del ws

        # MktCap neutralize
        try:
            adjf = np.clip(np.where(np.isnan(p.fields.get('I_D_ADJFACTOR', np.ones_like(cb[0]))), 1.0,
                          p.fields.get('I_D_ADJFACTOR', np.ones_like(cb[0]))), 0.01, 100)
            m = p.fields['I_D_CLOSE_ORI'] * adjf * p.fields.get('I_D_TOTAL_SHARES',
                          p.fields.get('I_D_SHARE_LIQA', np.ones_like(cb[0])))
            mt = np.asarray(m[t0:t1], dtype=np.float64)
            for tt in range(cb.shape[0]):
                vl = ~np.isnan(cb[tt]) & ~np.isnan(mt[tt])
                if vl.sum()<100: continue
                lmc = np.log(np.maximum(mt[tt][vl], 1))
                gi = np.floor(np.digitize(lmc, np.percentile(lmc, np.arange(0,101,10)))/10).astype(int)
                cv = cb[tt][vl].copy()
                for g in np.unique(gi):
                    gm = gi==g
                    if gm.sum()>=10: cv[gm] -= np.nanmean(cv[gm])
                cb[tt][vl] = cv
        except: pass

        cr = e.full_evaluation(cb, univ, label=lbl)
        cm = _compute_metrics_from_result(cb, lbl, univ, cr)
        del cb; gc.collect()
        return {k:v for k,v in cm.items() if k not in ('_factor_array','_direction')}

# ==================== INNOVATION EXPERIMENTS ====================

print(f"=== INNOVATION EXPERIMENTS — {datetime.now().strftime('%H:%M:%S')} ===")

all_f = get_factors()
print(f"Loaded {len(all_f)} factors (IS_IC>0.01)")

groups = {}
for f in all_f:
    g = f['group']
    if g not in groups: groups[g] = []
    groups[g].append(f)

pure = ['reversal','momentum','microstructure','volatility','liquidity']
results = []

# ====== 1. NESTING: Build Layer-1 ICIR combos per style ======
print("\n--- NESTING Layer 1: Best ICIR per style (cache matrix) ---")
layer1 = {}
for gk in pure:
    gf = sorted(groups.get(gk,[]), key=lambda x: -x['is_ic'])[:8]
    if len(gf)<3: continue
    exprs = [f['expression'] for f in gf]
    w = [1.0/len(exprs)]*len(exprs)
    t0 = time.time()
    m = compute_combo(exprs, w, 'equal')
    t = time.time()-t0
    if not m: continue
    print(f"  L1 {gk} (N={len(exprs)}): S={m['sharpe']:.2f} IC={m['pearson_ic']:.4f} ({t:.0f}s)")
    layer1[gk] = {'expressions': exprs, 'metrics': m}
    results.append({'experiment':'nesting_L1','group':gk,'n':len(exprs),'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir']})

# ====== 2. NESTING Layer 2: Cross-style meta-combo ======
print("\n--- NESTING Layer 2: Cross-style meta-combo (best from each style) ---")
best_per_style = []
for gk in pure:
    gf = sorted(groups.get(gk,[]), key=lambda x: -x['is_ic'])[:3]
    best_per_style.extend(gf)
exprs_best = [f['expression'] for f in best_per_style]
for method in ['equal']:
    w = [1.0/len(exprs_best)]*len(exprs_best) if method=='equal' else None
    if w is None:
        # ICIR weights
        pass  # skip for now
    else:
        t0 = time.time()
        m = compute_combo(exprs_best, w, method)
        t = time.time()-t0
        if m:
            print(f"  L2 cross-style (N={len(exprs_best)}): S={m['sharpe']:.2f} IC={m['pearson_ic']:.4f} ({t:.0f}s)")
            results.append({'experiment':'nesting_L2_cross','n':len(exprs_best),'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir']})

# ====== 3. GREEDY CORRELATION FILTERING ======
print("\n--- GREEDY CORRELATION: Different max_corr thresholds ---")
# Use best factors from each style, greedily filter by different thresholds
from scipy import stats as sp_stats

# Build PnL correlation matrix for top 50 factors
top50 = sorted(all_f, key=lambda x: -x['is_ic'])[:50]
pnl_matrix = None
with flask_app.app_context():
    p, e, f = get_engine()
    dk = sorted(p.date_to_idx.keys())
    t0 = None
    for d in dk:
        if d >= '2023-01-01': t0 = p.date_to_idx[d]; break
    t1 = min(p.date_to_idx['2023-12-29']+1, p.n_dates)
    nd = t1-t0
    pnl_matrix = np.zeros((nd, len(top50)), dtype=np.float32)
    for i, fact in enumerate(top50):
        try:
            fa = parse_expression(fact['expression'], p, f)
            ft = np.asarray(fa[t0:t1], dtype=np.float32)
            pnl_matrix[:,i] = np.nanmean(ft, axis=1)
            del fa, ft
        except:
            pnl_matrix[:,i] = np.nan

# Greedy selection with different thresholds
for threshold in [0.3, 0.5, 0.7]:
    selected_idx = []
    remaining = list(range(len(top50)))
    remaining.sort(key=lambda i: -top50[i]['is_ic'])
    while remaining and len(selected_idx) < 20:
        cand = remaining.pop(0)
        too_close = False
        for s in selected_idx:
            v1 = pnl_matrix[:,cand]; v2 = pnl_matrix[:,s]
            valid = ~np.isnan(v1) & ~np.isnan(v2)
            if valid.sum() < 30: continue
            corr = abs(sp_stats.spearmanr(v1[valid], v2[valid])[0])
            if corr > threshold:
                too_close = True; break
        if not too_close:
            selected_idx.append(cand)
    selected = [top50[i] for i in selected_idx]
    exprs = [f['expression'] for f in selected]
    if len(exprs) < 3: continue
    w = [1.0/len(exprs)]*len(exprs)
    t0_t = time.time()
    m = compute_combo(exprs, w, 'equal')
    t = time.time()-t0_t
    if m:
        print(f"  Greedy corr<{threshold}: N={len(exprs)} S={m['sharpe']:.2f} IC={m['pearson_ic']:.4f} ({t:.0f}s)")
        results.append({'experiment':f'greedy_corr_{threshold}','n':len(exprs),'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir']})

# ====== 4. PRECISION: Small-N best-of-best ======
print("\n--- PRECISION: Small-N elite combos ---")
top10 = sorted(all_f, key=lambda x: -x['is_ic'])[:10]
for n in [3,5,7]:
    exprs = [f['expression'] for f in top10[:n]]
    for method in ['equal']:
        w = [1.0/n]*n
        t0_t = time.time()
        m = compute_combo(exprs, w, method)
        t = time.time()-t0_t
        if m:
            print(f"  Elite N={n}: S={m['sharpe']:.2f} IC={m['pearson_ic']:.4f} ({t:.0f}s)")
            results.append({'experiment':f'elite_N{n}','n':n,'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir']})

# ====== 5. REVERSAL+MOMENTUM mix ======
print("\n--- REVERSAL+MOMENTUM hybrid combos ---")
rev = sorted(groups.get('reversal',[]), key=lambda x: -x['is_ic'])[:5]
mom = sorted(groups.get('momentum',[]), key=lambda x: -x['is_ic'])[:5]
for ratio in [(3,2),(5,5),(2,3)]:
    mix = rev[:ratio[0]] + mom[:ratio[1]]
    exprs = [f['expression'] for f in mix]
    w = [1.0/len(exprs)]*len(exprs)
    t0_t = time.time()
    m = compute_combo(exprs, w, 'equal')
    t = time.time()-t0_t
    if m:
        label = f'rev{ratio[0]}+mom{ratio[1]}'
        print(f"  {label} (N={len(exprs)}): S={m['sharpe']:.2f} IC={m['pearson_ic']:.4f} ({t:.0f}s)")
        results.append({'experiment':label,'n':len(exprs),'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir']})

# ====== SAVE ======
out = os.path.join(OUTPUT_DIR, f'innovation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
with open(out,'w') as f:
    json.dump(results, f, indent=2, default=str)

print(f"\n{'='*50}")
print(f"Innovation results: {len(results)} experiments")
for r in sorted(results, key=lambda x: -x.get('sharpe',0)):
    print(f"  {r.get('experiment','?'):25s} N={r.get('n',0):3d} S={r.get('sharpe',0):.2f} IC={r.get('ic',0):.4f}")
print(f"\nSaved to {out}")
