"""
Batch combo experiments via HTTP API (subprocess-safe, no memory issues).
"""
import requests, json, time, sys, os

BASE = 'http://127.0.0.1:5000'
PY = r'python'
RESULTS_DIR = r'D:\yyb\backtest_platform\experiment_results'
os.makedirs(RESULTS_DIR, exist_ok=True)


def classify_via_api(session):
    """Get all factor IDs grouped by economic group via API."""
    # First get all factors with IS_IC > 0.01
    r = session.get(f'{BASE}/api/alpha_history',
                    params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_pearson_ic', 'order': 'desc'})
    data = r.json()
    records = data.get('records', [])

    # Classify using server-side economic_group (we do it client-side by keyword)
    from app import _economic_group
    groups = {}
    for rec in records:
        g = _economic_group(rec.get('expression', ''), rec.get('type', 'alpha'))
        gk = g['group_key']
        if gk not in groups:
            groups[gk] = []
        groups[gk].append(rec)
    return groups, records


def run_combo(session, alpha_ids, method, label, timeout=600):
    """Call /api/superalpha with alpha_ids."""
    payload = {
        'alpha_ids': alpha_ids,
        'method': method,
        'oos_only': True,
    }
    t0 = time.time()
    try:
        r = session.post(f'{BASE}/api/superalpha', json=payload, timeout=timeout)
        elapsed = time.time() - t0
        result = r.json()
        if result.get('success'):
            m = result.get('combined_metrics', {})
            return {
                'label': label,
                'method': method,
                'n_factors': len(alpha_ids),
                'sharpe': m.get('sharpe', 0),
                'ic': m.get('pearson_ic', 0),
                'icir': m.get('icir', 0),
                'fitness': m.get('fitness', 0),
                'annual_excess': m.get('annual_excess', 0),
                'max_drawdown': m.get('max_drawdown', 0),
                'elapsed': round(elapsed, 1),
                'n_valid': result.get('n_valid_factors', 0),
            }
        else:
            return {'label': label, 'method': method, 'error': result.get('error', 'unknown'), 'elapsed': round(elapsed, 1)}
    except Exception as e:
        return {'label': label, 'method': method, 'error': str(e), 'elapsed': round(time.time()-t0, 1)}


def main():
    # Login
    session = requests.Session()
    r = session.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'}, allow_redirects=False)
    if r.status_code not in (200, 302):
        print(f'Login failed: {r.status_code}')
        return
    # Follow redirect to establish session
    if r.status_code == 302:
        session.get(f'{BASE}{r.headers["Location"]}')
    print('Logged in OK')

    # Get factor list
    r = session.get(f'{BASE}/api/alpha_history',
                    params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_pearson_ic', 'order': 'desc'})
    data = r.json()
    records = data.get('records', [])
    # Filter out superalpha
    records = [r for r in records if r.get('type') != 'superalpha']

    print(f'Loaded {len(records)} factors with IS_IC > 0.01')

    # Classify (inline to avoid importing app.py)
    _ECONOMIC_GROUPS = [
        ('momentum', '动量', ['momentum', 'mom_', 'trend', 'breakout', 'ret_20', 'ret_60', 'ret_120', 'cumret', 'ts_delta', 'slope', 'accel', 'relative_strength', 'new_high', 'ma_gap', 'ema', 'macd', 'price_strength']),
        ('reversal', '反转', ['reversal', 'rev_', 'mean_reversion', 'overreaction', 'gap', 'overnight', 'rsi', 'stoch', '-rank(returns', '-returns', '-ret_', 'close_position', 'close_location', 'short_term_reversal']),
        ('volatility', '波动率', ['volatility', 'realized_vol', 'downside', 'std', 'atr', 'range', 'high_low', 'skew', 'kurt', 'drawdown', 'max_dd', 'max_drawdown', 'beta', 'risk', 'entropy', 'dispersion', 'boll']),
        ('liquidity', '流动性', ['turnover', 'volume', 'amount', 'dollar', 'liquidity', 'amihud', 'adv', 'money_flow', 'flow', 'trade_count', 'volume_profile']),
        ('microstructure', '微观结构', ['minute', 'intraday', 'auction', 'vwap', 'open_', 'close_', 'high_', 'low_', 'shadow', 'wick', 'body', 'kline', 'bar_', 'smart_money', 'imbalance', 'impact']),
        ('size', '规模', ['market_cap', 'mcap', 'float_cap', 'size', 'ln_cap', 'log_cap']),
        ('fundamental', '基本面', ['roe', 'roa', 'profit', 'margin', 'debt', 'asset', 'liability', 'book', 'eps', 'sales', 'revenue', 'cash', 'earning', 'earnings', 'growth', 'pe', 'pb', 'bp', 'value']),
        ('sentiment', '情绪/分析师', ['news', 'sentiment', 'social', 'analyst', 'revision', 'rating', 'recommend', 'estimate', 'forecast']),
    ]

    def _economic_group_inline(expression, alpha_type='alpha'):
        expr = (expression or '').lower()
        typ = (alpha_type or 'alpha').lower()
        if typ == 'superalpha' or expr.startswith('lgb(') or expr.startswith('superalpha('):
            return {'group': '组合', 'group_key': 'combo', 'group_excluded': False, 'group_reason': '组合因子'}
        scores = []
        for key, label, terms in _ECONOMIC_GROUPS:
            hits = []
            for term in terms:
                if term in expr:
                    hits.append(term)
            if hits:
                scores.append((len(set(hits)), key, label, sorted(set(hits))[:5]))
        if not scores:
            return {'group': '未分组', 'group_key': 'unknown', 'group_excluded': True, 'group_reason': '未识别出单一稳定经济含义'}
        scores.sort(reverse=True)
        top_score, top_key, top_label, top_hits = scores[0]
        secondary = [x for x in scores[1:] if x[0] > 0]
        if secondary:
            second_score, second_key, second_label, second_hits = secondary[0]
            if second_score >= max(1, top_score - 1):
                return {'group': '混合/剔除', 'group_key': 'mixed', 'group_excluded': True, 'group_reason': ' + '.join([top_label, second_label]) + ' 信号混合'}
        return {'group': top_label, 'group_key': top_key, 'group_excluded': False, 'group_reason': '命中: ' + ', '.join(top_hits)}

    groups = {}
    for rec in records:
        g = _economic_group_inline(rec.get('expression', ''), rec.get('type', 'alpha'))
        gk = g['group_key']
        if gk not in groups:
            groups[gk] = []
        groups[gk].append(rec)

    for gk in sorted(groups.keys(), key=lambda k: -len(groups[k])):
        print(f'  {gk}: {len(groups[gk])}')

    all_results = []

    # Experiment pools
    pure_pools = {
        'liquidity': groups.get('liquidity', []),
        'microstructure': groups.get('microstructure', []),
        'reversal': groups.get('reversal', []),
        'momentum': groups.get('momentum', []),
    }

    # Pure groups × EW/ICIR/Ridge
    for gk, gfactors in pure_pools.items():
        if len(gfactors) < 3:
            continue
        ids = [r['id'] for r in gfactors]
        print(f'\n--- {gk}: {len(ids)} factors ---')
        for method in ['equal', 'icir', 'ridge']:
            label = f'{method}-{gk}'
            print(f'  {label} ({len(ids)} factors)...', end=' ', flush=True)
            result = run_combo(session, ids, method, label)
            all_results.append(result)
            if 'error' in result:
                print(f'ERROR: {result["error"]}')
            else:
                print(f'Sharpe={result["sharpe"]:.2f} IC={result["ic"]:.4f} ({result["elapsed"]}s)')

    # Clean pool (all pure combined)
    clean_all = []
    for gk in pure_pools:
        clean_all.extend(pure_pools[gk])
    clean_ids = [r['id'] for r in clean_all]
    print(f'\n--- clean-all: {len(clean_ids)} factors ---')
    for method in ['equal', 'icir', 'ridge']:
        label = f'{method}-clean-all'
        print(f'  {label}...', end=' ', flush=True)
        result = run_combo(session, clean_ids, method, label)
        all_results.append(result)
        if 'error' in result:
            print(f'ERROR: {result["error"]}')
        else:
            print(f'Sharpe={result["sharpe"]:.2f} IC={result["ic"]:.4f} ({result["elapsed"]}s)')

    # Top-N pools
    sorted_records = sorted(records, key=lambda r: r.get('metrics', {}).get('is_pearson_ic', 0), reverse=True)
    for top_n in [30, 50, 100]:
        top_ids = [r['id'] for r in sorted_records[:top_n]]
        print(f'\n--- top{top_n}: {len(top_ids)} factors ---')
        for method in ['equal', 'icir', 'ridge']:
            label = f'{method}-top{top_n}'
            print(f'  {label}...', end=' ', flush=True)
            result = run_combo(session, top_ids, method, label)
            all_results.append(result)
            if 'error' in result:
                print(f'ERROR: {result["error"]}')
            else:
                print(f'Sharpe={result["sharpe"]:.2f} IC={result["ic"]:.4f} ({result["elapsed"]}s)')

    # Summary table
    print(f'\n\n{"="*100}')
    print(f'{"Label":30s} {"n":>5s} {"Sharpe":>8s} {"IC":>8s} {"ICIR":>8s} {"Fitness":>8s} {"AnnEx":>8s} {"MaxDD":>8s} {"Time":>8s}')
    print('-'*100)
    for r in sorted([x for x in all_results if 'error' not in x], key=lambda x: -x['sharpe']):
        print(f'{r["label"]:30s} {r["n_factors"]:5d} {r["sharpe"]:8.2f} {r["ic"]:8.4f} {r["icir"]:8.2f} {r["fitness"]:8.2f} {r["annual_excess"]:8.4f} {r["max_drawdown"]:8.4f} {r["elapsed"]:7.1f}s')

    # Errors
    errors = [x for x in all_results if 'error' in x]
    if errors:
        print(f'\nErrors: {len(errors)}')
        for e in errors:
            print(f'  {e["label"]}: {e["error"]}')

    # Save
    from datetime import datetime
    out = os.path.join(RESULTS_DIR, f'experiments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f'\nSaved to {out}')


if __name__ == '__main__':
    main()
