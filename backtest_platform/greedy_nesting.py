"""Greedy correlation filtering + combo nesting experiments."""
import requests, json, time, numpy as np, os
from datetime import datetime
from scipy import stats as sp_stats

BASE = 'http://127.0.0.1:5000'
OUT = r'D:\yyb\backtest_platform\experiment_results\greedy_nesting.json'
os.makedirs(os.path.dirname(OUT), exist_ok=True)

s = requests.Session()
s.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'})

r = s.get(f'{BASE}/api/alpha/history', params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_sharpe', 'order': 'desc'})
records = [x for x in r.json().get('records',[]) if x.get('type') != 'superalpha']
print(f'{len(records)} factors')

# Group by economic category
_GROUPS = [
    ('reversal', ['reversal','rev_','mean_reversion','-rank(returns','-returns','-ret_','close_position','close_location','short_term_reversal']),
    ('momentum', ['momentum','mom_','trend','breakout','ret_20','ret_60','ret_120','cumret','ts_delta','slope','accel','relative_strength','new_high','ma_gap','ema','macd','price_strength']),
    ('microstructure', ['minute','intraday','auction','vwap','open_','close_','high_','low_','shadow','wick','body','kline','bar_','smart_money','imbalance','impact']),
]
def gk(expr):
    el = expr.lower()
    scores = [(len(set(t for t in terms if t in el)), key) for key, terms in _GROUPS]
    scores = [(s,k) for s,k in scores if s>0]
    if not scores: return 'other'
    scores.sort(reverse=True)
    return scores[0][1]

groups = {}
for rec in records:
    g = gk(rec['expression'])
    if g not in groups: groups[g] = []
    groups[g].append(rec)

# Top-50 by IS_Sharpe for greedy
top50 = sorted(records, key=lambda r: r['metrics'].get('is_sharpe',0), reverse=True)[:50]

# Fetch PnL from DB directly (API may fail for individual PnL)
print('Fetching PnL from DB...')
import sqlite3 as _sq
dconn = _sq.connect(r'D:\yyb\backtest_platform\backtest.db')
pnls = []
for rec in top50:
    try:
        row = dconn.execute('SELECT pnl_json, metrics_json FROM alpha_history WHERE id=?', (rec['id'],)).fetchone()
        if row:
            pnl = None
            if row[0]:
                d = json.loads(row[0])
                if isinstance(d, list) and len(d) > 100:
                    pnl = d
                elif isinstance(d, dict):
                    pnl = d.get('_pnl_series', d.get('oos_pnl', d.get('pnl_series', d.get('pnl'))))
            if not pnl and row[1]:
                m = json.loads(row[1])
                pnl = m.get('is_pnl_series', m.get('pnl_series'))
                if isinstance(pnl, list) and len(pnl) < 100:
                    pnl = None
            if pnl and isinstance(pnl, list) and len(pnl) > 100:
                pnls.append(np.array(pnl, dtype=np.float64))
            else:
                pnls.append(None)
        else:
            pnls.append(None)
    except Exception as e:
        pnls.append(None)
dconn.close()
valid_pnls = sum(1 for p in pnls if p is not None)
print(f'  Valid PnLs: {valid_pnls}/50')

results = []

# ====== GREEDY CORRELATION ======
print('\n=== GREEDY FILTERING ===')

def greedy_select(factors, pnl_data, max_corr, top_n=12):
    selected = []
    remaining = list(range(len(factors)))
    remaining.sort(key=lambda i: -(factors[i]['metrics'].get('is_sharpe',0)))
    while remaining and len(selected) < top_n:
        cand = remaining.pop(0)
        if pnl_data[cand] is None:
            continue
        too_close = False
        for s in selected:
            if pnl_data[s] is None: continue
            v1, v2 = pnl_data[cand], pnl_data[s]
            valid = ~np.isnan(v1) & ~np.isnan(v2)
            if valid.sum() < 30: continue
            corr = abs(sp_stats.spearmanr(v1[valid], v2[valid])[0])
            if corr > max_corr:
                too_close = True
                break
        if not too_close:
            selected.append(cand)
    return selected

for threshold in [0.3, 0.5, 0.7]:
    print(f'\n--- Threshold {threshold} ---')
    sel = greedy_select(top50, pnls, threshold, top_n=12)
    n_sel = len(sel)
    print(f'  Selected {n_sel} factors (from 50, max_corr<{threshold})')

    # Show group breakdown
    gcount = {}
    for i in sel:
        g = gk(top50[i]['expression'])
        gcount[g] = gcount.get(g, 0) + 1
    print(f'  Groups: {gcount}')

    if n_sel < 3:
        continue

    ids = [top50[i]['id'] for i in sel]
    for method in ['equal','icir','ridge']:
        label = f'{method}-greedy_cr{int(threshold*10)}'
        t0 = time.time()
        try:
            r = s.post(f'{BASE}/api/superalpha',
                json={'alpha_ids': ids, 'method': method, 'oos_only': True, 'neutralize': 'market_cap'},
                timeout=180)
            d = r.json()
            if d.get('success'):
                m = d.get('combined_metrics',{})
                entry = {'label':label, 'method':method, 'threshold':threshold, 'n':len(ids),
                         'sharpe':m.get('sharpe',0), 'ic':m.get('pearson_ic',0), 'icir':m.get('icir',0)}
                results.append(entry)
                print(f'    {label}: N={len(ids)} S={m["sharpe"]:.2f} IC={m["pearson_ic"]:.4f}')
            else:
                print(f'    {label}: ERR {d.get("error","?")[:60]}')
        except Exception as e:
            print(f'    {label}: {str(e)[:60]}')
        time.sleep(1.5)

# ====== NESTING ======
print('\n=== NESTING (COMBO of COMBOS) ===')

# Layer 1: Build style-specific ICIR combos
layer1_ids = {}
for gk_name in ['reversal','momentum','microstructure']:
    gf = sorted(groups.get(gk_name,[]), key=lambda r: r['metrics'].get('is_sharpe',0), reverse=True)[:5]
    if len(gf) < 3: continue
    ids = [r['id'] for r in gf]
    t0 = time.time()
    try:
        r = s.post(f'{BASE}/api/superalpha',
            json={'alpha_ids': ids, 'method': 'icir', 'oos_only': True, 'neutralize': 'market_cap'},
            timeout=180)
        d = r.json()
        if d.get('success'):
            m = d.get('combined_metrics',{})
            r2 = s.get(f'{BASE}/api/alpha/history', params={'limit': 1, 'sort': 'timestamp', 'order': 'desc'})
            latest = r2.json().get('records',[])
            if latest:
                layer1_ids[gk_name] = latest[0]['id']
            entry = {'label':f'nestL1_ICIR_{gk_name}', 'method':'icir', 'pool':gk_name,
                     'n':5, 'sharpe':m.get('sharpe',0), 'ic':m.get('pearson_ic',0), 'icir':m.get('icir',0)}
            results.append(entry)
            print(f'  L1 ICIR-{gk_name}: S={m["sharpe"]:.2f} IC={m["pearson_ic"]:.4f}')
    except Exception as e:
        print(f'  L1 {gk_name}: {str(e)[:60]}')
    time.sleep(2)

# Layer 2: Nest the L1 combos
if len(layer1_ids) >= 2:
    nest_ids = list(layer1_ids.values())
    print(f'\n  Layer 2: Nesting {len(nest_ids)} layer-1 combos')
    for method in ['equal','icir']:
        t0 = time.time()
        try:
            r = s.post(f'{BASE}/api/superalpha',
                json={'alpha_ids': nest_ids, 'method': method, 'oos_only': True, 'neutralize': 'market_cap'},
                timeout=180)
            d = r.json()
            if d.get('success'):
                m = d.get('combined_metrics',{})
                entry = {'label':f'{method}-nestL2', 'method':method, 'pool':'nesting',
                         'n':len(nest_ids), 'sharpe':m.get('sharpe',0), 'ic':m.get('pearson_ic',0), 'icir':m.get('icir',0)}
                results.append(entry)
                print(f'  L2 {method}: S={m["sharpe"]:.2f} IC={m["pearson_ic"]:.4f}')
        except Exception as e:
            print(f'  L2 {method}: {str(e)[:60]}')
        time.sleep(1.5)

# Summary
print(f'\n=== ALL INNOVATION ({len(results)}) ===')
for r in sorted(results, key=lambda x: -x['sharpe']):
    th = r.get('threshold', 0)
    print(f'  {r["label"]:35s} N={r["n"]:3d} corr<{th:.1f} S={r["sharpe"]:.2f} IC={r["ic"]:.4f}')

with open(OUT, 'w') as f:
    json.dump(results, f, indent=2)
print(f'\nSaved: {OUT}')
