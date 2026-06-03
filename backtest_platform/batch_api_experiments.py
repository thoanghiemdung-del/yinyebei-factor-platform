"""
Batch experiments via Flask API. Each combo runs in subprocess, memory safe.
Results saved to experiment_results/ for paper generation.
"""
import requests, json, time, os, sqlite3, sys
from datetime import datetime

BASE = 'http://127.0.0.1:5000'
OUTPUT_DIR = r'D:\yyb\backtest_platform\experiment_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Login first
session = requests.Session()
r = session.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'}, allow_redirects=True)
print(f'Login: {r.status_code}')

# Get all factors
r = session.get(f'{BASE}/api/alpha/history', params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_pearson_ic', 'order': 'desc'})
records = [r for r in r.json().get('records', []) if r.get('type') != 'superalpha']
print(f'Factors: {len(records)}')

# Classify
_ECONOMIC_GROUPS = [
    ('momentum', ['momentum', 'mom_', 'trend', 'breakout', 'ret_20', 'ret_60', 'ret_120', 'cumret', 'ts_delta', 'slope', 'accel', 'relative_strength', 'new_high', 'ma_gap', 'ema', 'macd', 'price_strength']),
    ('reversal', ['reversal', 'rev_', 'mean_reversion', 'overreaction', 'gap', 'overnight', 'rsi', 'stoch', '-rank(returns', '-returns', '-ret_', 'close_position', 'close_location', 'short_term_reversal']),
    ('volatility', ['volatility', 'realized_vol', 'downside', 'std', 'atr', 'range', 'high_low', 'skew', 'kurt', 'drawdown', 'max_dd', 'max_drawdown', 'beta', 'risk', 'entropy', 'dispersion', 'boll']),
    ('liquidity', ['turnover', 'volume', 'amount', 'dollar', 'liquidity', 'amihud', 'adv', 'money_flow', 'flow', 'trade_count', 'volume_profile']),
    ('microstructure', ['minute', 'intraday', 'auction', 'vwap', 'open_', 'close_', 'high_', 'low_', 'shadow', 'wick', 'body', 'kline', 'bar_', 'smart_money', 'imbalance', 'impact']),
    ('size', ['market_cap', 'mcap', 'float_cap', 'size', 'ln_cap', 'log_cap']),
    ('fundamental', ['roe', 'roa', 'profit', 'margin', 'debt', 'asset', 'liability', 'book', 'eps', 'sales', 'revenue', 'cash', 'earning', 'earnings', 'growth', 'pe', 'pb', 'bp', 'value']),
    ('sentiment', ['news', 'sentiment', 'social', 'analyst', 'revision', 'rating', 'recommend', 'estimate', 'forecast']),
]

def economic_group_key(expr):
    expr_l = expr.lower()
    scores = []
    for key, terms in _ECONOMIC_GROUPS:
        hits = [t for t in terms if t in expr_l]
        if hits:
            scores.append((len(set(hits)), key))
    if not scores:
        return 'unknown'
    scores.sort(reverse=True)
    if len(scores) > 1 and scores[1][0] >= max(1, scores[0][0] - 1):
        return 'mixed'
    return scores[0][1]

groups = {}
for rec in records:
    gk = economic_group_key(rec['expression'])
    rec['_group'] = gk
    if gk not in groups:
        groups[gk] = []
    groups[gk].append(rec)

for gk in sorted(groups.keys(), key=lambda k: -len(groups[k])):
    print(f'  {gk}: {len(groups[gk])}')

all_results = []

def run_combo(alpha_ids, method='equal', label='', timeout=120):
    """Call superalpha API, wait for result."""
    payload = {'alpha_ids': alpha_ids, 'method': method, 'oos_only': True}
    t0 = time.time()
    try:
        r = session.post(f'{BASE}/api/superalpha', json=payload, timeout=timeout)
        elapsed = time.time() - t0
        data = r.json()
        if data.get('success'):
            m = data.get('combined_metrics', {})
            return {
                'label': label, 'method': method, 'n_factors': len(alpha_ids),
                'sharpe': m.get('sharpe', 0), 'ic': m.get('pearson_ic', 0),
                'icir': m.get('icir', 0), 'fitness': m.get('fitness', 0),
                'annual_excess': m.get('annual_excess', 0),
                'max_drawdown': m.get('max_drawdown', 0),
                'turnover': m.get('turnover', 0),
                'elapsed': round(elapsed, 1), 'n_valid': data.get('n_valid_factors', 0),
            }
        else:
            err = data.get('error', 'unknown')
            if '正在处理' in str(err) or '503' in str(r.status_code):
                # Server busy — another combo running, retry
                time.sleep(5)
                return run_combo(alpha_ids, method, label, timeout)
            return {'label': label, 'method': method, 'error': str(err)[:100], 'elapsed': round(elapsed, 1)}
    except requests.Timeout:
        elapsed = time.time() - t0
        return {'label': label, 'method': method, 'error': 'timeout', 'elapsed': round(elapsed, 1)}
    except Exception as e:
        return {'label': label, 'method': method, 'error': str(e)[:100], 'elapsed': round(time.time()-t0, 1)}


# Build experiment queue
experiments = []

pure_groups = ['liquidity', 'microstructure', 'reversal', 'momentum', 'volatility']
clean_all = []
for gk in pure_groups:
    if gk in groups:
        clean_all.extend(groups[gk])
        gs = sorted(groups[gk], key=lambda r: r['metrics'].get('is_pearson_ic', 0), reverse=True)
        for n in [3, 5, 8, min(10, len(gs))]:
            if n < 2 or n > len(gs): continue
            for method in ['equal', 'icir', 'ridge']:
                experiments.append({
                    'pool': gk, 'pool_type': 'within_style', 'n': n,
                    'method': method, 'ids': [r['id'] for r in gs[:n]],
                    'label': f'{method}-{gk}-N{n}',
                    'avg_is_ic': sum(r['metrics'].get('is_pearson_ic',0) for r in gs[:n])/n,
                })

# Cross-style: greedy top across groups
by_ic = sorted(clean_all, key=lambda r: r['metrics'].get('is_pearson_ic', 0), reverse=True)
for n in [5, 8, 10, 15, 20]:
    if n > len(by_ic): continue
    for method in ['equal', 'icir', 'ridge']:
        experiments.append({
            'pool': 'cross', 'pool_type': 'cross_style', 'n': n,
            'method': method, 'ids': [r['id'] for r in by_ic[:n]],
            'label': f'{method}-cross-N{n}',
            'avg_is_ic': sum(r['metrics'].get('is_pearson_ic',0) for r in by_ic[:n])/n,
        })

# Top-N by IS_IC
all_by_ic = sorted(records, key=lambda r: r['metrics'].get('is_pearson_ic', 0), reverse=True)
for n in [5, 10, 20, 30, 50, 100]:
    if n > len(all_by_ic): continue
    for method in ['equal', 'icir', 'ridge']:
        experiments.append({
            'pool': 'topIC', 'pool_type': 'all', 'n': n,
            'method': method, 'ids': [r['id'] for r in all_by_ic[:n]],
            'label': f'{method}-topIC-N{n}',
            'avg_is_ic': sum(r['metrics'].get('is_pearson_ic',0) for r in all_by_ic[:n])/n,
        })

print(f'\nTotal experiments: {len(experiments)}')
print(f'Estimated time: {len(experiments)*20/60:.0f} min')

# Run experiments sequentially
start_time = datetime.now()
for i, exp in enumerate(experiments):
    print(f'[{i+1}/{len(experiments)}] {exp["label"]} (avg_IS_IC={exp["avg_is_ic"]:.4f})...', end=' ', flush=True)
    result = run_combo(exp['ids'], exp['method'], exp['label'], timeout=180)
    if 'error' in result:
        print(f'ERROR: {result["error"]}')
    else:
        exp_result = {**exp, **result}
        all_results.append(exp_result)
        print(f'S={result["sharpe"]:.2f} IC={result["ic"]:.4f} ({result["elapsed"]}s)')

    # Save intermediate results every 5 experiments
    if (i+1) % 5 == 0:
        out = os.path.join(OUTPUT_DIR, f'batch_{start_time.strftime("%Y%m%d_%H%M%S")}.json')
        with open(out, 'w') as f:
            json.dump(all_results, f, indent=2, default=str)

    # Brief pause to let memory settle
    time.sleep(2)

# Final save
end_time = datetime.now()
out = os.path.join(OUTPUT_DIR, f'batch_{start_time.strftime("%Y%m%d_%H%M%S")}.json')
output = {
    'start_time': start_time.isoformat(), 'end_time': end_time.isoformat(),
    'duration_s': (end_time-start_time).total_seconds(),
    'total_experiments': len(experiments), 'completed': len(all_results),
    'results': all_results,
}
with open(out, 'w') as f:
    json.dump(output, f, indent=2, default=str)

print(f'\n\n=== DONE ===')
print(f'Completed: {len(all_results)}/{len(experiments)}')
print(f'Saved to: {out}')

# Summary table
print(f'\n{"Label":35s} {"N":>4s} {"Sharpe":>8s} {"IC":>8s} {"ICIR":>7s} {"Fit":>7s}')
print('-'*75)
for r in sorted(all_results, key=lambda x: -(x.get('sharpe') or 0)):
    print(f'{r["label"]:35s} {r["n_factors"]:4d} {r.get("sharpe",0):8.2f} {r.get("ic",0):8.4f} {r.get("icir",0):7.2f} {r.get("fitness",0):7.2f}')
