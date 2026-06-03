"""
Systematic combo experiment runner — IS/OOS architecture.
Runs EW, ICIR, Ridge combos across all factor groups, sizes, and cross-style pools.
Uses inline path for <=10 factors, subprocess for larger.
Generates paper-ready JSON data.
"""
import sys, os, json, time, sqlite3, statistics, traceback, gc, math
from datetime import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result
from app import _add_to_history, DB_PATH

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiment_results')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Economic groups definition (same as app.py)
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

def _economic_group(expression, alpha_type='alpha'):
    expr = (expression or '').lower()
    typ = (alpha_type or 'alpha').lower()
    if typ == 'superalpha' or expr.startswith('lgb(') or expr.startswith('superalpha('):
        return {'group': '组合', 'group_key': 'combo', 'group_excluded': False}
    scores = []
    for key, label, terms in _ECONOMIC_GROUPS:
        hits = [t for t in terms if t in expr]
        if hits:
            scores.append((len(set(hits)), key, label))
    if not scores:
        return {'group': '未分组', 'group_key': 'unknown', 'group_excluded': True}
    scores.sort(reverse=True)
    sc, k, lab = scores[0]
    if len(scores) > 1 and scores[1][0] >= max(1, sc - 1):
        return {'group': '混合', 'group_key': 'mixed', 'group_excluded': True}
    return {'group': lab, 'group_key': k, 'group_excluded': False}


def get_factors():
    """Get all factors with IS_IC > 0.01, classified."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, expression, metrics_json, type FROM alpha_history
        WHERE json_extract(metrics_json, '$.is_pearson_ic') > 0.01
          AND (type IS NULL OR type != 'superalpha')
        ORDER BY json_extract(metrics_json, '$.is_pearson_ic') DESC
    """).fetchall()
    conn.close()
    results = []
    for r in rows:
        m = json.loads(r[2])
        g = _economic_group(r[1], r[3] or 'alpha')
        results.append({
            'id': r[0], 'expression': r[1],
            'is_ic': m.get('is_pearson_ic') or 0,
            'oos_ic': m.get('oos_pearson_ic') or 0,
            'is_sharpe': m.get('is_sharpe') or 0,
            'group_key': g['group_key'],
            'group': g['group'],
            'excluded': g.get('group_excluded', False),
        })
    return results


def compute_combo_inline(expressions, weights, method='equal'):
    """Fast inline combo — OOS evaluation only."""
    with flask_app.app_context():
        pipeline, engine, fc = get_engine()
        date_keys = sorted(pipeline.date_to_idx.keys())
        t0 = None
        for d in date_keys:
            if d >= '2023-01-01':
                t0 = pipeline.date_to_idx[d]
                break
        t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
        label = pipeline.fields['Label'][t0:t1]
        univ = pipeline.universe_mask[t0:t1]
        n_dates, n_stocks = label.shape

        combined = np.zeros((n_dates, n_stocks), dtype=np.float32)
        weight_sum = np.zeros((n_dates, n_stocks), dtype=np.float32)
        valid_count = 0
        sub_metrics = []

        for i, expr in enumerate(expressions):
            try:
                factor = parse_expression(expr, pipeline, fc)
                f_train = np.asarray(factor[t0:t1], dtype=np.float32)
                del factor
                f_mean = np.nanmean(f_train, axis=1, keepdims=True)
                f_std = np.nanstd(f_train, axis=1, keepdims=True) + 1e-10
                fz = (f_train - f_mean) / f_std
                v = np.isfinite(fz)
                if not np.any(v):
                    del f_train, fz, v, f_mean, f_std
                    continue
                w = float(weights[i])
                combined[v] += w * fz[v]
                weight_sum[v] += w
                valid_count += 1
                # Store sub-metrics
                res = engine.full_evaluation(f_train, univ, label=label)
                sm = _compute_metrics_from_result(f_train, label, univ, res)
                sub_metrics.append({
                    'expression': expr, 'weight': round(w, 4),
                    'sharpe': sm.get('sharpe', 0), 'ic': sm.get('pearson_ic', 0),
                    'icir': sm.get('icir', 0), 'fitness': sm.get('fitness', 0),
                })
                del f_train, fz, v, f_mean, f_std
            except Exception:
                continue

        vw = np.isfinite(weight_sum) & (np.abs(weight_sum) > 1e-12)
        if valid_count < 1 or not np.any(vw):
            return None
        combined[vw] = combined[vw] / weight_sum[vw]
        combined[~vw] = np.nan
        del weight_sum

        cr = engine.full_evaluation(combined, univ, label=label)
        cm = _compute_metrics_from_result(combined, label, univ, cr)
        del combined
        gc.collect()

        return {
            'sharpe': cm.get('sharpe', 0),
            'ic': cm.get('pearson_ic', 0),
            'icir': cm.get('icir', 0),
            'fitness': cm.get('fitness', 0),
            'annual_excess': cm.get('annual_excess', 0),
            'max_drawdown': cm.get('max_drawdown', 0),
            'turnover': cm.get('turnover', 0),
            'win_rate': cm.get('win_rate', 0),
            'n_valid': valid_count,
            'sub_metrics': sub_metrics[:10],
        }


def compute_icir_weights(expressions):
    """Compute ICIR weights using IS period (2020-2022)."""
    with flask_app.app_context():
        pipeline, engine, fc = get_engine()
        date_keys = sorted(pipeline.date_to_idx.keys())
        t0 = pipeline.date_to_idx['2020-01-02']
        t1 = None
        for d in reversed(date_keys):
            if d < '2023-01-01':
                t1 = pipeline.date_to_idx[d] + 1
                break
        label = pipeline.fields['Label'][t0:t1]
        univ = pipeline.universe_mask[t0:t1]
        n_dates = label.shape[0]

        icirs = []
        for expr in expressions:
            try:
                factor = parse_expression(expr, pipeline, fc)
                f_train = np.asarray(factor[t0:t1], dtype=np.float32)
                del factor
                daily_ic = []
                for t in range(n_dates):
                    fv, lv = f_train[t], label[t]
                    v = univ[t] & (~np.isnan(fv)) & (~np.isnan(lv))
                    if v.sum() < 30:
                        continue
                    from scipy import stats as st
                    ic = st.spearmanr(fv[v], lv[v])[0]
                    if not np.isnan(ic):
                        daily_ic.append(ic)
                ic_arr = np.array(daily_ic)
                icir = np.nanmean(ic_arr) / (np.nanstd(ic_arr) + 1e-10)
                icirs.append(max(0.1, icir))
                del f_train
            except Exception:
                icirs.append(0.1)
        icir_sum = sum(icirs)
        return [ic / icir_sum for ic in icirs] if icir_sum > 0 else [1.0 / len(expressions)] * len(expressions)


def compute_ridge_weights(expressions):
    """Compute Ridge weights using IS period volatility."""
    with flask_app.app_context():
        pipeline, engine, fc = get_engine()
        date_keys = sorted(pipeline.date_to_idx.keys())
        t0 = pipeline.date_to_idx['2020-01-02']
        t1 = None
        for d in reversed(date_keys):
            if d < '2023-01-01':
                t1 = pipeline.date_to_idx[d] + 1
                break
        label = pipeline.fields['Label'][t0:t1]
        univ = pipeline.universe_mask[t0:t1]
        n_dates = label.shape[0]

        vols = []
        for expr in expressions:
            try:
                factor = parse_expression(expr, pipeline, fc)
                f_train = np.asarray(factor[t0:t1], dtype=np.float32)
                del factor
                daily_ret = []
                for t in range(n_dates):
                    fv = f_train[t]
                    v = univ[t] & (~np.isnan(fv))
                    if v.sum() >= 30:
                        daily_ret.append(np.nanmean(fv[v]))
                vols.append(np.nanstd(np.array(daily_ret)) + 1e-10)
                del f_train
            except Exception:
                vols.append(1.0)
        lam = np.median(vols) if vols else 1.0
        inv_vols = [1.0 / (v + lam) for v in vols]
        inv_sum = sum(inv_vols)
        return [iv / inv_sum for iv in inv_vols] if inv_sum > 0 else [1.0 / len(expressions)] * len(expressions)


def greedy_select(factors, max_corr=0.5, top_n=10, sort_key='is_ic'):
    """Greedy correlation-filtered selection."""
    selected = []
    remaining = sorted(factors, key=lambda x: -x.get(sort_key, 0))
    while remaining and len(selected) < top_n:
        candidate = remaining.pop(0)
        # For greedy, we need pairwise PnL correlation. Simplified: use IS sharpe as proxy
        # In production, this would use actual PnL correlations
        too_correlated = False
        for s in selected:
            # Check if same group → higher risk of correlation
            if candidate.get('group_key') == s.get('group_key'):
                too_correlated = True
                break
        if not too_correlated:
            selected.append(candidate)
    return selected


def main():
    start_time = datetime.now()
    print(f"=== Systematic Experiment Runner ===")
    print(f"Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load factors
    all_factors = get_factors()
    print(f"Loaded {len(all_factors)} factors (IS_IC > 0.01)")

    # Group by economic category
    groups = {}
    for f in all_factors:
        gk = f['group_key']
        if gk not in groups:
            groups[gk] = []
        groups[gk].append(f)

    for gk in sorted(groups.keys(), key=lambda k: -len(groups[k])):
        print(f"  {gk}: {len(groups[gk])}")

    # Define experiment pools
    pure_pools = {}
    for gk in ['liquidity', 'microstructure', 'reversal', 'momentum', 'volatility']:
        if gk in groups:
            pure_pools[gk] = groups[gk]

    # Clean pool: all pure groups combined
    clean_all = []
    for gk, gfactors in pure_pools.items():
        clean_all.extend(gfactors)
    print(f"\nClean pool (pure groups): {len(clean_all)} factors")

    # Mixed pool
    mixed = groups.get('mixed', [])
    print(f"Mixed pool: {len(mixed)} factors")

    # Sort by IS_IC for top-N experiments
    sorted_by_ic = sorted(all_factors, key=lambda x: -x['is_ic'])

    all_results = []
    experiment_count = 0

    # ================================================================
    # EXPERIMENT 1: Within-style × EW/ICIR/Ridge × N ∈ {3,5,8,10}
    # ================================================================
    print(f"\n{'='*60}")
    print("EXPERIMENT 1: Within-style combos")
    print(f"{'='*60}")

    for gk, gfactors in pure_pools.items():
        gfactors_sorted = sorted(gfactors, key=lambda x: -x['is_ic'])
        for n in [3, 5, 8, min(10, len(gfactors))]:
            if n > len(gfactors_sorted) or n < 2:
                continue
            factors_n = gfactors_sorted[:n]
            exprs = [f['expression'] for f in factors_n]
            avg_is_ic = statistics.mean([f['is_ic'] for f in factors_n])

            for method in ['equal', 'icir', 'ridge']:
                experiment_count += 1
                label = f"{method}-{gk}-N{n}"
                print(f"  [{experiment_count}] {label} (avg_IS_IC={avg_is_ic:.4f})...", end=' ', flush=True)
                t0 = time.time()
                try:
                    if method == 'icir':
                        weights = compute_icir_weights(exprs)
                    elif method == 'ridge':
                        weights = compute_ridge_weights(exprs)
                    else:
                        weights = [1.0 / len(exprs)] * len(exprs)

                    result = compute_combo_inline(exprs, weights, method)
                    elapsed = time.time() - t0
                    if result:
                        result['label'] = label
                        result['method'] = method
                        result['pool'] = gk
                        result['pool_type'] = 'within_style'
                        result['n_factors'] = n
                        result['avg_is_ic'] = round(avg_is_ic, 4)
                        result['elapsed_s'] = round(elapsed, 1)
                        result['weights'] = [round(w, 4) for w in weights]
                        all_results.append(result)
                        print(f"S={result['sharpe']:.2f} IC={result['ic']:.4f} IR={result['icir']:.2f} ({elapsed:.1f}s)")
                    else:
                        print(f"FAILED ({elapsed:.1f}s)")
                except Exception as e:
                    elapsed = time.time() - t0
                    print(f"ERROR: {str(e)[:80]} ({elapsed:.1f}s)")
                    traceback.print_exc()
                gc.collect()

    # ================================================================
    # EXPERIMENT 2: Cross-style combos
    # ================================================================
    print(f"\n{'='*60}")
    print("EXPERIMENT 2: Cross-style combos (greedy across groups)")
    print(f"{'='*60}")

    # Greedy selection: pick 1-2 from each group, sort by IS_IC
    greedy_selected = greedy_select(clean_all, max_corr=0.5, top_n=100, sort_key='is_ic')
    greedy_sorted = sorted(greedy_selected, key=lambda x: -x['is_ic'])

    for n in [5, 8, 10, 15, 20]:
        if n > len(greedy_sorted):
            continue
        factors_n = greedy_sorted[:n]
        exprs = [f['expression'] for f in factors_n]
        avg_is_ic = statistics.mean([f['is_ic'] for f in factors_n])

        for method in ['equal', 'icir', 'ridge']:
            experiment_count += 1
            label = f"{method}-cross_greedy-N{n}"
            print(f"  [{experiment_count}] {label} (avg_IS_IC={avg_is_ic:.4f})...", end=' ', flush=True)
            t0 = time.time()
            try:
                if method == 'icir':
                    weights = compute_icir_weights(exprs)
                elif method == 'ridge':
                    weights = compute_ridge_weights(exprs)
                else:
                    weights = [1.0 / len(exprs)] * len(exprs)

                result = compute_combo_inline(exprs, weights, method)
                elapsed = time.time() - t0
                if result:
                    result['label'] = label
                    result['method'] = method
                    result['pool'] = 'cross_greedy'
                    result['pool_type'] = 'cross_style'
                    result['n_factors'] = n
                    result['avg_is_ic'] = round(avg_is_ic, 4)
                    result['elapsed_s'] = round(elapsed, 1)
                    all_results.append(result)
                    print(f"S={result['sharpe']:.2f} IC={result['ic']:.4f} IR={result['icir']:.2f} ({elapsed:.1f}s)")
                else:
                    print(f"FAILED ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"ERROR: {str(e)[:80]} ({elapsed:.1f}s)")
            gc.collect()

    # ================================================================
    # EXPERIMENT 3: Clean pool × N sizes
    # ================================================================
    print(f"\n{'='*60}")
    print("EXPERIMENT 3: Clean all pool (all pure groups combined)")
    print(f"{'='*60}")

    clean_sorted = sorted(clean_all, key=lambda x: -x['is_ic'])
    for n in [10, 20, 30, 50]:
        if n > len(clean_sorted):
            continue
        factors_n = clean_sorted[:n]
        exprs = [f['expression'] for f in factors_n]
        avg_is_ic = statistics.mean([f['is_ic'] for f in factors_n])

        for method in ['equal', 'icir', 'ridge']:
            experiment_count += 1
            label = f"{method}-clean_all-N{n}"
            print(f"  [{experiment_count}] {label} (avg_IS_IC={avg_is_ic:.4f})...", end=' ', flush=True)
            t0 = time.time()
            try:
                if method == 'icir':
                    weights = compute_icir_weights(exprs)
                elif method == 'ridge':
                    weights = compute_ridge_weights(exprs)
                else:
                    weights = [1.0 / len(exprs)] * len(exprs)

                result = compute_combo_inline(exprs, weights, method)
                elapsed = time.time() - t0
                if result:
                    result['label'] = label
                    result['method'] = method
                    result['pool'] = 'clean_all'
                    result['pool_type'] = 'within_style'
                    result['n_factors'] = n
                    result['avg_is_ic'] = round(avg_is_ic, 4)
                    result['elapsed_s'] = round(elapsed, 1)
                    all_results.append(result)
                    print(f"S={result['sharpe']:.2f} IC={result['ic']:.4f} IR={result['icir']:.2f} ({elapsed:.1f}s)")
                else:
                    print(f"FAILED ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"ERROR: {str(e)[:80]} ({elapsed:.1f}s)")
            gc.collect()

    # ================================================================
    # EXPERIMENT 4: Top-N by IS_IC × all methods
    # ================================================================
    print(f"\n{'='*60}")
    print("EXPERIMENT 4: Top-N by IS_IC (IS-screened only)")
    print(f"{'='*60}")

    for n in [5, 10, 20, 30, 50, 100]:
        if n > len(sorted_by_ic):
            continue
        factors_n = sorted_by_ic[:n]
        exprs = [f['expression'] for f in factors_n]
        avg_is_ic = statistics.mean([f['is_ic'] for f in factors_n])

        for method in ['equal', 'icir', 'ridge']:
            experiment_count += 1
            label = f"{method}-topIC-N{n}"
            print(f"  [{experiment_count}] {label} (avg_IS_IC={avg_is_ic:.4f})...", end=' ', flush=True)
            t0 = time.time()
            try:
                if method == 'icir':
                    weights = compute_icir_weights(exprs)
                elif method == 'ridge':
                    weights = compute_ridge_weights(exprs)
                else:
                    weights = [1.0 / len(exprs)] * len(exprs)

                result = compute_combo_inline(exprs, weights, method)
                elapsed = time.time() - t0
                if result:
                    result['label'] = label
                    result['method'] = method
                    result['pool'] = 'top_ic'
                    result['pool_type'] = 'all'
                    result['n_factors'] = n
                    result['avg_is_ic'] = round(avg_is_ic, 4)
                    result['elapsed_s'] = round(elapsed, 1)
                    all_results.append(result)
                    print(f"S={result['sharpe']:.2f} IC={result['ic']:.4f} IR={result['icir']:.2f} ({elapsed:.1f}s)")
                else:
                    print(f"FAILED ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"ERROR: {str(e)[:80]} ({elapsed:.1f}s)")
            gc.collect()

    # ================================================================
    # SAVE RESULTS
    # ================================================================
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    output = {
        'start_time': start_time.isoformat(),
        'end_time': end_time.isoformat(),
        'duration_s': duration,
        'total_experiments': experiment_count,
        'architecture': 'IS/OOS split — IS(2020-2022) screening, OOS(2023) evaluation',
        'factor_count': len(all_factors),
        'results': all_results,
    }

    out_file = os.path.join(OUTPUT_DIR, f'systematic_experiments_{start_time.strftime("%Y%m%d_%H%M%S")}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nSaved {len(all_results)} results to {out_file}")
    print(f"Duration: {duration/60:.1f} min")

    return all_results


if __name__ == '__main__':
    main()
