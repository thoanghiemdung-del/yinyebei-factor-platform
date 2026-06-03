"""
Systematic combo experiment runner.
Classifies factors, runs EW/ICIR/Ridge combos per group via Flask internal API.
"""
import sys, os, json, time, sqlite3, gc, traceback, statistics
import numpy as np
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result
from app import _add_to_history, _to_json_safe, _economic_group, DB_PATH

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiment_results')
os.makedirs(RESULTS_DIR, exist_ok=True)


def classify_all_factors():
    """Return {group_key: [id, expr, metrics_json, type]} for all IS_IC>0.01 factors."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT id, expression, metrics_json, type FROM alpha_history
        WHERE json_extract(metrics_json, '$.is_pearson_ic') > 0.01
          AND (type IS NULL OR type != 'superalpha')
    """).fetchall()
    conn.close()

    groups = {}
    for r in rows:
        g = _economic_group(r[1], r[3] or 'alpha')
        gk = g['group_key']
        if gk not in groups:
            groups[gk] = []
        groups[gk].append(r)
    return groups


def run_combo_ew(group_name, group_factors, oos_only=True):
    """Equal-weight combo for a list of (id, expr, metrics_json, type) factors."""
    expressions = [r[1] for r in group_factors]
    n = len(expressions)
    weights = [1.0/n] * n

    return _run_combo_internal(expressions, weights, 'equal', group_name, oos_only=oos_only)


def run_combo_weighted(group_name, group_factors, method='icir'):
    """ICIR or Ridge weighted combo."""
    with flask_app.app_context():
        pipeline, engine, fc = get_engine()

        # IS period (2020-2022) for weight calculation
        date_keys = sorted(pipeline.date_to_idx.keys())
        t0_is = pipeline.date_to_idx['2020-01-02']
        t1_is = None
        for d in reversed(date_keys):
            if d < '2023-01-01':
                t1_is = pipeline.date_to_idx[d] + 1
                break
        label_is = pipeline.fields['Label'][t0_is:t1_is]
        univ_is = pipeline.universe_mask[t0_is:t1_is]
        n_dates = label_is.shape[0]

        expressions = [r[1] for r in group_factors]
        icirs = []
        vols = []

        for expr in expressions:
            try:
                factor = parse_expression(expr, pipeline, fc)
                f_train = np.asarray(factor[t0_is:t1_is], dtype=np.float32)
                del factor
                daily_ic = []
                daily_returns = []
                for t in range(n_dates):
                    fv = f_train[t]
                    lv = label_is[t]
                    valid = univ_is[t] & (~np.isnan(fv)) & (~np.isnan(lv))
                    if valid.sum() < 30:
                        continue
                    from scipy import stats as _scipy_stats
                    ic = _scipy_stats.spearmanr(fv[valid], lv[valid])[0]
                    if not np.isnan(ic):
                        daily_ic.append(ic)
                        daily_returns.append(np.nanmean(fv[valid]))
                ic_arr = np.array(daily_ic)
                mean_ic = np.nanmean(ic_arr)
                std_ic = np.nanstd(ic_arr)
                icir = mean_ic / (std_ic + 1e-10)
                icirs.append(max(0.1, icir))
                vols.append(np.nanstd(np.array(daily_returns)) + 1e-10)
                del f_train
            except Exception:
                icirs.append(0.1)
                vols.append(1.0)

        if method == 'icir':
            icir_sum = sum(icirs)
            weights = [ic / icir_sum for ic in icirs] if icir_sum > 0 else [1.0/len(expressions)]*len(expressions)
        elif method == 'ridge':
            lam = np.median(vols) if vols else 1.0
            inv_vols = [1.0/(v + lam) for v in vols]
            inv_sum = sum(inv_vols)
            weights = [iv/inv_sum for iv in inv_vols] if inv_sum > 0 else [1.0/len(expressions)]*len(expressions)
        else:
            weights = [1.0/len(expressions)]*len(expressions)

    return _run_combo_internal(expressions, weights, method, group_name, oos_only=True)


def _run_combo_internal(expressions, weights, method, group_name, oos_only=True):
    """Core combo computation — OOS evaluation with pre-computed weights."""
    with flask_app.app_context():
        pipeline, engine, fc = get_engine()

        # OOS period
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

        for i, expr in enumerate(expressions):
            try:
                factor = parse_expression(expr, pipeline, fc)
                f_train = np.asarray(factor[t0:t1], dtype=np.float32)
                del factor
                f_mean = np.nanmean(f_train, axis=1, keepdims=True)
                f_std = np.nanstd(f_train, axis=1, keepdims=True) + 1e-10
                fz = (f_train - f_mean) / f_std
                valid = np.isfinite(fz)
                if not np.any(valid):
                    continue
                w = float(weights[i])
                combined[valid] += w * fz[valid]
                weight_sum[valid] += w
                valid_count += 1
                del f_train, fz, valid, f_mean, f_std
            except Exception:
                continue

        valid_weight = np.isfinite(weight_sum) & (np.abs(weight_sum) > 1e-12)
        if valid_count < 2 or not np.any(valid_weight):
            return None

        combined[valid_weight] = combined[valid_weight] / weight_sum[valid_weight]
        combined[~valid_weight] = np.nan
        del weight_sum
        gc.collect()

        result = engine.full_evaluation(combined, univ, label=label)
        metrics = _compute_metrics_from_result(combined, label, univ, result)
        metrics_clean = {k: v for k, v in metrics.items() if k not in ('_factor_array', '_direction')}

        # Build expression string
        if method == 'equal':
            expr_str = 'superalpha(' + ' + '.join(expressions) + ')'
        else:
            weighted_parts = [f'{round(w, 4)}*{e}' for w, e in zip(weights, expressions)]
            expr_str = f'superalpha[{method}](' + ' + '.join(weighted_parts) + ')'

        name = f'{method}-{group_name}-{len(expressions)}f'
        history_id = _add_to_history(expr_str, metrics, 'superalpha', name=name)

        del combined
        gc.collect()

        return {
            'history_id': history_id,
            'name': name,
            'method': method,
            'group': group_name,
            'n_factors': len(expressions),
            'n_valid': valid_count,
            'sharpe': metrics_clean.get('sharpe', 0),
            'ic': metrics_clean.get('pearson_ic', 0),
            'icir': metrics_clean.get('icir', 0),
            'fitness': metrics_clean.get('fitness', 0),
            'annual_excess': metrics_clean.get('annual_excess', 0),
            'max_drawdown': metrics_clean.get('max_drawdown', 0),
            'expression': expr_str[:200],
        }


def main():
    print(f"=== Experiment Runner — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print()

    with flask_app.app_context():
        print("Classifying factors...")
        groups = classify_all_factors()
        total = sum(len(v) for v in groups.values())
        print(f"Total factors: {total}, Groups: {len(groups)}")
        for gk in sorted(groups.keys(), key=lambda k: -len(groups[k])):
            print(f"  {gk}: {len(groups[gk])}")

    # Define experiment pools
    # Pure groups (non-mixed, non-unknown): liquidity, microstructure, reversal, momentum, volatility
    pure_groups = ['liquidity', 'microstructure', 'reversal', 'momentum', 'volatility']

    # Combined pools
    # Clean pool: all pure groups combined
    clean_factors = []
    for gk in pure_groups:
        clean_factors.extend(groups.get(gk, []))
    print(f"\nClean pool (pure groups): {len(clean_factors)} factors")

    # All pool: everything including mixed
    all_factors = []
    for gk in groups:
        all_factors.extend(groups[gk])
    print(f"All pool: {len(all_factors)} factors")

    all_results = []

    # ============================================================
    # Experiment Set 1: Pure groups — EW, ICIR, Ridge
    # ============================================================
    for gk in pure_groups:
        gfactors = groups.get(gk, [])
        if len(gfactors) < 3:
            continue
        print(f"\n{'='*60}")
        print(f"Group: {gk} ({len(gfactors)} factors)")

        for method in ['equal', 'icir', 'ridge']:
            tag = f"{method}-{gk}"
            print(f"  {method}...", end=' ', flush=True)
            try:
                if method == 'equal':
                    r = run_combo_ew(gk, gfactors)
                else:
                    r = run_combo_weighted(gk, gfactors, method=method)
                if r:
                    all_results.append(r)
                    print(f"Sharpe={r['sharpe']:.2f} IC={r['ic']:.4f} IR={r['icir']:.2f} n_valid={r['n_valid']}")
                else:
                    print("FAILED")
            except Exception as e:
                print(f"ERROR: {e}")
                traceback.print_exc()
            gc.collect()

    # ============================================================
    # Experiment Set 2: Clean pool — EW, ICIR, Ridge
    # ============================================================
    print(f"\n{'='*60}")
    print(f"Clean pool ({len(clean_factors)} factors)")
    for method in ['equal', 'icir', 'ridge']:
        print(f"  {method}...", end=' ', flush=True)
        try:
            if method == 'equal':
                r = run_combo_ew('clean', clean_factors)
            else:
                r = run_combo_weighted('clean', clean_factors, method=method)
            if r:
                all_results.append(r)
                print(f"Sharpe={r['sharpe']:.2f} IC={r['ic']:.4f} IR={r['icir']:.2f} n_valid={r['n_valid']}")
            else:
                print("FAILED")
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()
        gc.collect()

    # ============================================================
    # Experiment Set 3: Top-N pools by IS_IC (top 20, 50, 100)
    # ============================================================
    print(f"\n{'='*60}")
    print("Top-N by IS_IC experiments")

    def get_is_ic(row):
        m = json.loads(row[2])
        return m.get('is_pearson_ic') or 0

    sorted_all = sorted(all_factors, key=get_is_ic, reverse=True)

    for top_n in [30, 50, 100]:
        top_factors = sorted_all[:top_n]
        print(f"\n  Top-{top_n} (avg IS_IC={statistics.mean([get_is_ic(r) for r in top_factors]):.4f})")
        for method in ['equal', 'icir', 'ridge']:
            print(f"    {method}...", end=' ', flush=True)
            try:
                if method == 'equal':
                    r = run_combo_ew(f'top{top_n}', top_factors)
                else:
                    r = run_combo_weighted(f'top{top_n}', top_factors, method=method)
                if r:
                    all_results.append(r)
                    print(f"Sharpe={r['sharpe']:.2f} IC={r['ic']:.4f} IR={r['icir']:.2f}")
                else:
                    print("FAILED")
            except Exception as e:
                print(f"ERROR: {e}")
            gc.collect()

    # ============================================================
    # Summary
    # ============================================================
    print(f"\n{'='*60}")
    print(f"=== ALL RESULTS ({len(all_results)} combos) ===")
    print(f"{'method':8s} {'group':20s} {'n':>5s} {'Sharpe':>8s} {'IC':>8s} {'ICIR':>8s} {'Fitness':>8s} {'AnnEx':>8s} {'MaxDD':>8s}")
    print("-" * 96)
    for r in sorted(all_results, key=lambda x: -(x['sharpe'] or 0)):
        print(f"{r['method']:8s} {r['group']:20s} {r['n_factors']:5d} {r['sharpe']:8.2f} {r['ic']:8.4f} {r['icir']:8.2f} {r['fitness']:8.2f} {r['annual_excess']:8.4f} {r['max_drawdown']:8.4f}")

    # Save results
    out_file = os.path.join(RESULTS_DIR, f'experiments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nResults saved to {out_file}")

    return all_results


if __name__ == '__main__':
    main()
