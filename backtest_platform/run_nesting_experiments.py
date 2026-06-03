"""
Nesting experiments — combo of combos ("ultimate alpha").
Demonstrates true matrix-level nesting using cached OOS matrices.
"""
import sys, os, json, time, sqlite3, statistics, gc, math
from datetime import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, _add_to_history, DB_PATH

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'experiment_results')
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')


def compute_nesting_layer1():
    """Layer 1: Build pure-style combos via ICIR, cache their matrices."""
    print("=== NESTING LAYER 1: Pure-style ICIR combos ===")
    results = {}

    with flask_app.app_context():
        pipeline, engine, fc = get_engine()

        # Get factors grouped by style
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("""
            SELECT id, expression, metrics_json FROM alpha_history
            WHERE json_extract(metrics_json, '$.is_pearson_ic') > 0.01
              AND (type IS NULL OR type != 'superalpha')
            ORDER BY json_extract(metrics_json, '$.is_pearson_ic') DESC
        """).fetchall()
        conn.close()

        # Classify
        _ECONOMIC_GROUPS = [
            ('momentum', ['momentum', 'mom_', 'trend', 'breakout', 'ret_20', 'ret_60', 'ret_120', 'cumret', 'ts_delta', 'slope', 'accel', 'relative_strength', 'new_high', 'ma_gap', 'ema', 'macd', 'price_strength']),
            ('reversal', ['reversal', 'rev_', 'mean_reversion', 'overreaction', 'gap', 'overnight', 'rsi', 'stoch', '-rank(returns', '-returns', '-ret_', 'close_position', 'close_location', 'short_term_reversal']),
            ('volatility', ['volatility', 'realized_vol', 'downside', 'std', 'atr', 'range', 'high_low', 'skew', 'kurt', 'drawdown', 'max_dd', 'max_drawdown', 'beta', 'risk', 'entropy', 'dispersion', 'boll']),
            ('liquidity', ['turnover', 'volume', 'amount', 'dollar', 'liquidity', 'amihud', 'adv', 'money_flow', 'flow', 'trade_count', 'volume_profile']),
            ('microstructure', ['minute', 'intraday', 'auction', 'vwap', 'open_', 'close_', 'high_', 'low_', 'shadow', 'wick', 'body', 'kline', 'bar_', 'smart_money', 'imbalance', 'impact']),
        ]

        groups = {}
        for r in rows:
            expr = r[1].lower()
            for gk, terms in _ECONOMIC_GROUPS:
                hits = [t for t in terms if t in expr]
                if hits:
                    if gk not in groups:
                        groups[gk] = []
                    m = json.loads(r[2])
                    groups[gk].append({
                        'id': r[0], 'expression': r[1],
                        'is_ic': m.get('is_pearson_ic') or 0,
                        'oos_ic': m.get('oos_pearson_ic') or 0,
                    })
                    break

        date_keys = sorted(pipeline.date_to_idx.keys())
        t0_oos = None
        for d in date_keys:
            if d >= '2023-01-01':
                t0_oos = pipeline.date_to_idx[d]
                break
        t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
        label = pipeline.fields['Label'][t0_oos:t1]
        univ = pipeline.universe_mask[t0_oos:t1]
        n_dates, n_stocks = label.shape

        for gk in sorted(groups.keys(), key=lambda k: -len(groups[k])):
            gfactors = sorted(groups[gk], key=lambda x: -x['is_ic'])[:min(10, len(groups[gk]))]
            if len(gfactors) < 3:
                continue
            exprs = [f['expression'] for f in gfactors]
            n = len(exprs)

            # Compute ICIR weights
            weights = _compute_icir_weights_is(pipeline, fc, exprs)

            # Build combo matrix (OOS)
            combined = np.zeros((n_dates, n_stocks), dtype=np.float32)
            ws = np.zeros((n_dates, n_stocks), dtype=np.float32)
            vc = 0
            for i, expr in enumerate(exprs):
                try:
                    factor = parse_expression(expr, pipeline, fc)
                    ft = np.asarray(factor[t0_oos:t1], dtype=np.float32)
                    del factor
                    fm = np.nanmean(ft, axis=1, keepdims=True)
                    fs = np.nanstd(ft, axis=1, keepdims=True) + 1e-10
                    fz = (ft - fm) / fs
                    v = np.isfinite(fz)
                    if np.any(v):
                        w = float(weights[i])
                        combined[v] += w * fz[v]
                        ws[v] += w
                        vc += 1
                    del ft, fz, v, fm, fs
                except Exception:
                    continue

            vw = np.isfinite(ws) & (np.abs(ws) > 1e-12)
            if vc < 2 or not np.any(vw):
                continue
            combined[vw] /= ws[vw]
            combined[~vw] = np.nan
            del ws

            # Evaluate & save to history
            cr = engine.full_evaluation(combined, univ, label=label)
            cm = _compute_metrics_from_result(combined, label, univ, cr)
            cm_clean = {k: v for k, v in cm.items() if k not in ('_factor_array', '_direction')}

            weighted = [f'{round(w,4)}*{e}' for w, e in zip(weights, exprs)]
            combo_expr = f'superalpha[icir](' + ' + '.join(weighted) + ')'
            hid = _add_to_history(combo_expr, cm, 'superalpha')

            # Cache matrix
            if hid:
                cache_path = os.path.join(CACHE_DIR, f'ew_{hid}.npy')
                np.save(cache_path, combined)

            results[gk] = {
                'history_id': hid,
                'expression': combo_expr,
                'n_factors': n,
                'sharpe': cm_clean.get('sharpe', 0),
                'ic': cm_clean.get('pearson_ic', 0),
                'icir': cm_clean.get('icir', 0),
                'fitness': cm_clean.get('fitness', 0),
            }
            print(f"  Layer1 ICIR-{gk} (N={n}): S={cm_clean.get('sharpe',0):.2f} IC={cm_clean.get('pearson_ic',0):.4f} id={hid[:12]}...")
            del combined
            gc.collect()

    return results


def _compute_icir_weights_is(pipeline, fc, expressions):
    """IS-period ICIR weights."""
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
            ft = np.asarray(factor[t0:t1], dtype=np.float32)
            del factor
            daily_ic = []
            for t in range(n_dates):
                fv, lv = ft[t], label[t]
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
            del ft
        except Exception:
            icirs.append(0.1)
    s = sum(icirs)
    return [ic/s for ic in icirs] if s > 0 else [1.0/len(expressions)] * len(expressions)


def compute_nesting_layer2(layer1_results):
    """Layer 2: Cross-style nesting — combo of Layer 1 combos."""
    print(f"\n=== NESTING LAYER 2: Cross-style meta-combo ===")

    with flask_app.app_context():
        pipeline, engine, fc = get_engine()

        date_keys = sorted(pipeline.date_to_idx.keys())
        t0_oos = None
        for d in date_keys:
            if d >= '2023-01-01':
                t0_oos = pipeline.date_to_idx[d]
                break
        t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
        label = pipeline.fields['Label'][t0_oos:t1]
        univ = pipeline.universe_mask[t0_oos:t1]
        n_dates, n_stocks = label.shape

        # Load cached matrices from Layer 1
        style_keys = sorted(layer1_results.keys())
        matrices = []
        labels = []
        for gk in style_keys:
            r = layer1_results[gk]
            if not r or not r.get('history_id'):
                continue
            cache_path = os.path.join(CACHE_DIR, f'ew_{r[\"history_id\"]}.npy')
            if not os.path.exists(cache_path):
                print(f"  WARNING: cache missing for {gk}")
                continue
            matrix = np.load(cache_path)
            if matrix.shape == (n_dates, n_stocks):
                matrices.append(matrix)
                labels.append(gk)
                print(f"  Loaded {gk}: {r['sharpe']:.2f} Sharpe, {matrix.shape}")

        if len(matrices) < 2:
            print(f"  Only {len(matrices)} valid matrices, need >=2")
            return None

        # Equal-weight meta combo
        n = len(matrices)
        combined = np.zeros((n_dates, n_stocks), dtype=np.float32)
        ws = np.zeros((n_dates, n_stocks), dtype=np.float32)
        for i, mat in enumerate(matrices):
            fm = np.nanmean(mat, axis=1, keepdims=True)
            fs = np.nanstd(mat, axis=1, keepdims=True) + 1e-10
            fz = (mat - fm) / fs
            v = np.isfinite(fz)
            w = 1.0 / n
            combined[v] += w * fz[v]
            ws[v] += w
            del fm, fs, fz, v
        vw = np.isfinite(ws) & (np.abs(ws) > 1e-12)
        combined[vw] /= ws[vw]
        combined[~vw] = np.nan
        del ws

        cr = engine.full_evaluation(combined, univ, label=label)
        cm = _compute_metrics_from_result(combined, label, univ, cr)
        cm_clean = {k: v for k, v in cm.items() if k not in ('_factor_array', '_direction')}

        combo_expr = 'superalpha[icir](' + ' + '.join([layer1_results[gk]['expression'] for gk in style_keys if gk in layer1_results]) + ')'
        hid = _add_to_history(combo_expr, cm, 'superalpha')
        if hid:
            np.save(os.path.join(CACHE_DIR, f'ew_{hid}.npy'), combined)

        print(f"\n  ULTIMATE ALPHA: S={cm_clean.get('sharpe',0):.2f} IC={cm_clean.get('pearson_ic',0):.4f} IR={cm_clean.get('icir',0):.2f}")
        print(f"  Styles: {' + '.join(labels)}")
        print(f"  History ID: {hid}")

        del combined
        gc.collect()

        return {
            'history_id': hid,
            'expression': combo_expr,
            'sharpe': cm_clean.get('sharpe', 0),
            'ic': cm_clean.get('pearson_ic', 0),
            'icir': cm_clean.get('icir', 0),
            'fitness': cm_clean.get('fitness', 0),
            'styles': labels,
        }


def main():
    print(f"=== Nesting Experiments — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    layer1 = compute_nesting_layer1()
    if layer1:
        ultimate = compute_nesting_layer2(layer1)
        # Save
        out = os.path.join(OUTPUT_DIR, f'nesting_experiments_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(out, 'w') as f:
            json.dump({'layer1': layer1, 'ultimate': ultimate}, f, indent=2, default=str)
        print(f"\nSaved to {out}")


if __name__ == '__main__':
    main()
