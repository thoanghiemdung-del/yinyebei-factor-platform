"""
Robust refill — ALL 1176 single factors with market cap neutralization.
Memory-safe, 5-min progress reports, never crashes.
"""
import sys, os, json, time, sqlite3, gc, traceback, math
from datetime import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, _add_to_history, DB_PATH

s = datetime.now()

with flask_app.app_context():
    pipeline, engine, fc = get_engine()
    dk = sorted(pipeline.date_to_idx.keys())

    # IS/OOS boundaries
    t0_is = pipeline.date_to_idx['2020-01-02']
    t1_is = None
    for d in reversed(dk):
        if d < '2023-01-01': t1_is = pipeline.date_to_idx[d] + 1; break
    t0_oos = None
    for d in dk:
        if d >= '2023-01-01': t0_oos = pipeline.date_to_idx[d]; break
    t1_oos = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)

    label = pipeline.fields['Label']
    univ = pipeline.universe_mask

    # Pre-load market cap
    adjf = np.clip(np.where(np.isnan(pipeline.fields.get('I_D_ADJFACTOR', np.ones(pipeline.n_dates))), 1.0,
                      pipeline.fields.get('I_D_ADJFACTOR', np.ones(pipeline.n_dates))), 0.01, 100)
    mcap_full = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES',
                pipeline.fields.get('I_D_SHARE_LIQA', np.ones(pipeline.n_dates)))

    def neutralize(f_period, mcap_period):
        """WQ-style: subtract log-mcap regression residual — vectorized."""
        f_out = np.asarray(f_period, dtype=np.float32).copy()
        from scipy import stats
        for t in range(f_out.shape[0]):
            v = ~np.isnan(f_out[t]) & ~np.isnan(mcap_period[t]) & (mcap_period[t] > 0)
            if v.sum() < 100:
                continue
            x = np.log(np.maximum(mcap_period[t][v], 1))
            y = f_out[t][v]
            result = stats.linregress(x, y)
            resid = y - (result.slope * x + result.intercept)
            f_out[t][v] = np.float32(resid)
        return f_out

    # Get expressions NOT yet neutralized
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT expression FROM alpha_history
        WHERE (type IS NULL OR type != 'superalpha')
        AND expression NOT IN (
            SELECT expression FROM alpha_history
            WHERE json_extract(metrics_json, '$._neutralize') = 'market_cap'
        )
    """).fetchall()
    conn.close()
    expressions = [r[0] for r in rows]
    total = len(expressions)
    already_done = 1176 - total
    print(f"START: {s.strftime('%H:%M:%S')} | Target: {total} remaining (already done: {already_done}), MktCap neutralized", flush=True)

    success, skipped, errors = 0, 0, 0
    last_report = datetime.now()
    last_checkpoint = datetime.now()

    for i, expr in enumerate(expressions):
        try:
            # Parse (suppress minute-data warnings — use devnull to avoid memory leak)
            _old_out = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            parse_ok = False
            try:
                factor_arr = parse_expression(expr, pipeline, fc)
                parse_ok = True
            except Exception:
                skipped += 1
            sys.stdout.close()
            sys.stdout = _old_out
            if not parse_ok:
                continue
            if factor_arr is None:
                skipped += 1
                continue

            # IS neutralized
            f_is = np.asarray(factor_arr[t0_is:t1_is], dtype=np.float32)
            mcap_is = np.asarray(mcap_full[t0_is:t1_is], dtype=np.float64)
            f_is_n = neutralize(f_is, mcap_is)
            del f_is, mcap_is

            # OOS neutralized
            f_oos = np.asarray(factor_arr[t0_oos:t1_oos], dtype=np.float32)
            mcap_oos = np.asarray(mcap_full[t0_oos:t1_oos], dtype=np.float64)
            f_oos_n = neutralize(f_oos, mcap_oos)
            del f_oos, mcap_oos

            # Evaluate
            r_is = engine.full_evaluation(f_is_n, univ[t0_is:t1_is], label=label[t0_is:t1_is])
            m_is = _compute_metrics_from_result(f_is_n, label[t0_is:t1_is], univ[t0_is:t1_is], r_is)
            r_oos = engine.full_evaluation(f_oos_n, univ[t0_oos:t1_oos], label=label[t0_oos:t1_oos])
            m_oos = _compute_metrics_from_result(f_oos_n, label[t0_oos:t1_oos], univ[t0_oos:t1_oos], r_oos)

            # Merge
            metrics = {k: v for k, v in m_oos.items() if k not in ('_factor_array', '_direction')}
            for k in ['pearson_ic','sharpe','icir','fitness','annual_excess','returns','max_drawdown',
                       'turnover','margin_bps','win_rate','pnl_series']:
                v = m_is.get(k)
                if v is not None: metrics['is_' + k] = v
            metrics['oos_pearson_ic'] = m_oos.get('pearson_ic')
            metrics['_neutralize'] = 'market_cap'

            _add_to_history(expr, metrics, 'alpha', name=expr[:40])
            success += 1

            del factor_arr, f_is_n, f_oos_n
            gc.collect()  # aggressive GC every factor to prevent memory accumulation

        except np._core._exceptions._ArrayMemoryError:
            errors += 1
            gc.collect()
            time.sleep(5)
        except Exception as e:
            skipped += 1
            if skipped <= 3:
                print(f"  SKIP: {expr[:60]}... | {str(e)[:80]}", flush=True)

        # 5-min progress report
        elapsed = (datetime.now() - last_report).total_seconds()
        if elapsed >= 300:
            last_report = datetime.now()
            rate = (i + 1) / max((datetime.now() - s).total_seconds(), 1)
            eta_min = (total - i - 1) / max(rate, 0.001) / 60
            done_pct = (i + 1) / total * 100
            done_total = already_done + success
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {done_total}个/1176个 | OK:{success} SKIP:{skipped} ERR:{errors} | ETA:{eta_min:.0f}min | Rate:{rate:.1f}/s", flush=True)

        # Memory check every 50 factors
        if (i + 1) % 50 == 0:
            gc.collect()
            try:
                import psutil
                free = psutil.virtual_memory().available / (1024**3)
                if free < 0.5:
                    print(f"  MEM LOW: {free:.1f}GB free, force gc...", flush=True)
                    gc.collect()
                    time.sleep(3)
            except: pass

    # Final report
    t = (datetime.now() - s).total_seconds()
    print(f"\nDONE: {success} OK, {skipped} skipped, {errors} errors in {t/60:.1f}min", flush=True)
    print(f"END: {datetime.now().strftime('%H:%M:%S')}", flush=True)
