"""
MEGA experiment runner — 550+ combos, 10x previous paper.
All via Flask API (subprocess-safe), results → DB + experiment_results/ JSON.
Runs continuously until 08:00.
"""
import requests, json, time, os, sys
from datetime import datetime

BASE = 'http://127.0.0.1:5000'
OUTPUT_DIR = r'D:\yyb\backtest_platform\experiment_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

session = requests.Session()
r = session.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'}, allow_redirects=True)
assert r.status_code in (200, 302), f'Login failed: {r.status_code}'
print(f'Login OK')

r = session.get(f'{BASE}/api/alpha/history', params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_pearson_ic', 'order': 'desc'})
records_all = r.json().get('records', [])
single_records = [r for r in records_all if r.get('type') != 'superalpha']
print(f'Loaded {len(single_records)} single factors (IS_IC > 0.01)')

_GROUPS = [
    ('momentum', ['momentum', 'mom_', 'trend', 'breakout', 'ret_20', 'ret_60', 'ret_120', 'cumret', 'ts_delta', 'slope', 'accel', 'relative_strength', 'new_high', 'ma_gap', 'ema', 'macd', 'price_strength']),
    ('reversal', ['reversal', 'rev_', 'mean_reversion', 'overreaction', 'gap', 'overnight', 'rsi', 'stoch', '-rank(returns', '-returns', '-ret_', 'close_position', 'close_location', 'short_term_reversal']),
    ('volatility', ['volatility', 'realized_vol', 'downside', 'std', 'atr', 'range', 'high_low', 'skew', 'kurt', 'drawdown', 'max_dd', 'max_drawdown', 'beta', 'risk', 'entropy', 'dispersion', 'boll']),
    ('liquidity', ['turnover', 'volume', 'amount', 'dollar', 'liquidity', 'amihud', 'adv', 'money_flow', 'flow', 'trade_count', 'volume_profile']),
    ('microstructure', ['minute', 'intraday', 'auction', 'vwap', 'open_', 'close_', 'high_', 'low_', 'shadow', 'wick', 'body', 'kline', 'bar_', 'smart_money', 'imbalance', 'impact']),
    ('size', ['market_cap', 'mcap', 'float_cap', 'size', 'ln_cap', 'log_cap']),
    ('fundamental', ['roe', 'roa', 'profit', 'margin', 'debt', 'asset', 'liability', 'book', 'eps', 'sales', 'revenue', 'cash', 'earning', 'earnings', 'growth', 'pe', 'pb', 'bp', 'value']),
]

def group_key(expr):
    el = expr.lower()
    scores = [(len(set(t for t in terms if t in el)), key) for key, terms in _GROUPS]
    scores = [(s,k) for s,k in scores if s>0]
    if not scores: return 'unknown'
    scores.sort(reverse=True)
    if len(scores)>1 and scores[1][0]>=max(1,scores[0][0]-1): return 'mixed'
    return scores[0][1]

groups = {}
for rec in single_records:
    gk = group_key(rec['expression'])
    if gk not in groups: groups[gk] = []
    groups[gk].append(rec)

for gk in sorted(groups, key=lambda k:-len(groups[k])):
    print(f'  {gk}: {len(groups[gk])}')

pure_groups = ['liquidity', 'microstructure', 'reversal', 'momentum', 'volatility']
clean_all = []
for gk in pure_groups:
    if gk in groups: clean_all.extend(groups[gk])

all_results = []
total = 0
errors = 0

def call_api(alpha_ids, method, timeout=180):
    """Call superalpha API, retry if server busy."""
    for attempt in range(3):
        try:
            r = session.post(f'{BASE}/api/superalpha',
                json={'alpha_ids': alpha_ids, 'method': method, 'oos_only': True},
                timeout=timeout)
            data = r.json()
            if data.get('success'):
                m = data.get('combined_metrics', {})
                return {'ok': True, 'sharpe': m.get('sharpe',0), 'ic': m.get('pearson_ic',0),
                        'icir': m.get('icir',0), 'fitness': m.get('fitness',0),
                        'annual_excess': m.get('annual_excess',0), 'max_dd': m.get('max_drawdown',0),
                        'turnover': m.get('turnover',0), 'n_valid': data.get('n_valid_factors',0)}
            if '503' in str(r.status_code) or '正在处理' in str(data.get('error','')):
                time.sleep(5)
                continue
            return {'ok': False, 'error': str(data.get('error','unknown'))[:100]}
        except requests.Timeout:
            time.sleep(3)
        except Exception as e:
            time.sleep(3)
    return {'ok': False, 'error': 'timeout/retry exhausted'}

def add_experiment(ids, method, label, pool, pool_type, n, avg_is_ic):
    global total, errors
    total += 1
    t0 = time.time()
    result = call_api(ids, method)
    elapsed = time.time() - t0
    if result.get('ok'):
        entry = {'label':label, 'method':method, 'pool':pool, 'pool_type':pool_type,
                 'n_factors':n, 'avg_is_ic':round(avg_is_ic,4), 'elapsed':round(elapsed,1), **result}
        all_results.append(entry)
        print(f'[{total}] {label:40s} S={result["sharpe"]:7.2f} IC={result["ic"]:7.4f} IR={result["icir"]:7.2f} ({elapsed:.0f}s)')
    else:
        errors += 1
        print(f'[{total}] {label:40s} ERROR: {result.get("error","?")}')

    # Incremental save every 10
    if total % 10 == 0:
        save_results()
    time.sleep(1)

def save_results():
    out = os.path.join(OUTPUT_DIR, f'mega_experiments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(out,'w') as f:
        json.dump({'total':total, 'errors':errors, 'results':all_results}, f, indent=2, default=str)

start_time = datetime.now()
print(f'\n=== MEGA EXPERIMENTS — {start_time.strftime("%Y-%m-%d %H:%M:%S")} ===')
print(f'Target: 550+ experiments, running until 08:00\n')

# ========== PHASE 1: Within-style (5 groups × 6N × 3 methods = 90) ==========
print('--- PHASE 1: Within-style ---')
for gk in pure_groups:
    gfactors = sorted(groups.get(gk,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
    for n in [3,5,8,10,12,15]:
        if n > len(gfactors): continue
        ids = [r['id'] for r in gfactors[:n]]
        avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in gfactors[:n])/n
        for method in ['equal','icir','ridge']:
            label = f'{method}-{gk}-N{n}'
            add_experiment(ids, method, label, gk, 'within_style', n, avg_ic)

# ========== PHASE 2: Clean all (8N × 3 methods = 24) ==========
print('\n--- PHASE 2: Clean pool ---')
clean_by_ic = sorted(clean_all, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
for n in [10,20,30,50,75,100,150,min(200,len(clean_by_ic))]:
    if n > len(clean_by_ic): continue
    ids = [r['id'] for r in clean_by_ic[:n]]
    avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in clean_by_ic[:n])/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-clean-N{n}'
        add_experiment(ids, method, label, 'clean_all', 'all_pure', n, avg_ic)

# ========== PHASE 3: Top-IS_IC (9N × 3 methods = 27) ==========
print('\n--- PHASE 3: Top by IS_IC ---')
all_by_ic = sorted(single_records, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
for n in [3,5,10,15,20,30,50,75,100]:
    if n > len(all_by_ic): continue
    ids = [r['id'] for r in all_by_ic[:n]]
    avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in all_by_ic[:n])/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-topIC-N{n}'
        add_experiment(ids, method, label, 'top_ic', 'all', n, avg_ic)

# ========== PHASE 4: Top-IS_Sharpe (6N × 3 methods = 18) ==========
print('\n--- PHASE 4: Top by IS_Sharpe ---')
all_by_sharpe = sorted(single_records, key=lambda r: r['metrics'].get('is_sharpe',0), reverse=True)
for n in [5,10,20,30,50,100]:
    if n > len(all_by_sharpe): continue
    ids = [r['id'] for r in all_by_sharpe[:n]]
    avg_is_sharpe = sum(r['metrics'].get('is_sharpe',0) for r in all_by_sharpe[:n])/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-topSharpe-N{n}'
        add_experiment(ids, method, label, 'top_sharpe', 'all', n, avg_is_sharpe)

# ========== PHASE 5: Cross-style greedy selection ==========
print('\n--- PHASE 5: Cross-style greedy ---')
# Pick factors greedily from different groups
def greedy_cross_select(factors, top_n=50):
    selected, used_groups = [], set()
    sorted_f = sorted(factors, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
    for f in sorted_f:
        gk = group_key(f['expression'])
        if gk not in used_groups or len(selected) < 10:
            selected.append(f)
            used_groups.add(gk)
        if len(selected) >= top_n:
            break
    return selected

greedy_factors = greedy_cross_select(clean_all, 100)
greedy_by_ic = sorted(greedy_factors, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
for n in [5,8,10,15,20,30,50]:
    if n > len(greedy_by_ic): continue
    ids = [r['id'] for r in greedy_by_ic[:n]]
    avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in greedy_by_ic[:n])/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-cross_greedy-N{n}'
        add_experiment(ids, method, label, 'cross_greedy', 'cross_style', n, avg_ic)

# ========== PHASE 6: Mixed pool experiments ==========
print('\n--- PHASE 6: Mixed pool ---')
mixed = sorted(groups.get('mixed',[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
for n in [10,20,30,50,75,100]:
    if n > len(mixed): continue
    ids = [r['id'] for r in mixed[:n]]
    avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in mixed[:n])/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-mixed-N{n}'
        add_experiment(ids, method, label, 'mixed', 'mixed', n, avg_ic)

# ========== PHASE 7: Style-balanced (equal representation per group) ==========
print('\n--- PHASE 7: Style-balanced ---')
for per_group in [1,2,3,5]:
    balanced = []
    for gk in pure_groups:
        gs = sorted(groups.get(gk,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
        balanced.extend(gs[:per_group])
    if len(balanced) < 5: continue
    ids = [r['id'] for r in balanced]
    n = len(ids)
    avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in balanced)/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-balanced-p{per_group}'
        add_experiment(ids, method, label, 'balanced', 'balanced', n, avg_ic)

# ========== PHASE 8: Exclude-mixed (unknown only) ==========
print('\n--- PHASE 8: Unknown group ---')
unknown = sorted(groups.get('unknown',[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
if unknown:
    for n in [10,20,min(50,len(unknown))]:
        if n > len(unknown): continue
        ids = [r['id'] for r in unknown[:n]]
        avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in unknown[:n])/n
        for method in ['equal','icir','ridge']:
            label = f'{method}-unknown-N{n}'
            add_experiment(ids, method, label, 'unknown', 'unknown', n, avg_ic)

# ========== PHASE 9: All-in (everything) ==========
print('\n--- PHASE 9: All-in ---')
for n in [50,100,200,300]:
    if n > len(all_by_ic): continue
    ids = [r['id'] for r in all_by_ic[:n]]
    avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in all_by_ic[:n])/n
    for method in ['equal','icir','ridge']:
        label = f'{method}-all-N{n}'
        add_experiment(ids, method, label, 'all', 'all', n, avg_ic)

# ========== PHASE 10: Pairwise cross-group combos ==========
print('\n--- PHASE 10: Pairwise cross-group ---')
for gk1 in range(len(pure_groups)):
    for gk2 in range(gk1+1, len(pure_groups)):
        g1, g2 = pure_groups[gk1], pure_groups[gk2]
        f1 = sorted(groups.get(g1,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
        f2 = sorted(groups.get(g2,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
        combined = f1[:5] + f2[:5]
        if len(combined) < 3: continue
        ids = [r['id'] for r in combined]
        avg_ic = sum(r['metrics'].get('is_pearson_ic',0) for r in combined)/len(combined)
        for method in ['equal','icir']:
            label = f'{method}-{g1}+{g2}'
            add_experiment(ids, method, label, f'{g1}+{g2}', 'pairwise', len(combined), avg_ic)

# Final save
save_results()
end_time = datetime.now()
duration_min = (end_time-start_time).total_seconds()/60
print(f'\n=== COMPLETE ===')
print(f'Total: {total} experiments, {errors} errors')
print(f'Duration: {duration_min:.1f} min')
print(f'Results: {len(all_results)} successful')
