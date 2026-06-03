"""
Re-backtest ALL single factors with market cap neutralization — inline, no subprocess overhead.
Pipeline loaded once, all factors processed sequentially.
Saves both IS and OOS metrics with _neutralize='market_cap' tag.
"""
import sys, os, json, time, sqlite3, gc, traceback, math
from datetime import datetime
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, _add_to_history, DB_PATH

print(f"=== Single Factor Refill with Market Cap Neutralization ===")
print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

with flask_app.app_context():
    pipeline, engine, fc = get_engine()
    date_keys = sorted(pipeline.date_to_idx.keys())

    # IS boundaries
    t0_is = pipeline.date_to_idx['2020-01-02']
    t1_is = None
    for d in reversed(date_keys):
        if d < '2023-01-01':
            t1_is = pipeline.date_to_idx[d] + 1
            break

    # OOS boundaries
    t0_oos = None
    for d in date_keys:
        if d >= '2023-01-01':
            t0_oos = pipeline.date_to_idx[d]
            break
    t1_oos = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)

    label = pipeline.fields['Label']
    univ = pipeline.universe_mask

    # Market cap data (pre-load)
    adjf = np.clip(np.where(np.isnan(pipeline.fields.get('I_D_ADJFACTOR', np.ones(pipeline.n_dates))), 1.0,
                          pipeline.fields.get('I_D_ADJFACTOR', np.ones(pipeline.n_dates))), 0.01, 100)
    mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES',
                    pipeline.fields.get('I_D_SHARE_LIQA', np.ones(pipeline.n_dates)))

    def apply_mcap_neutralize(f_period, mcap_period):
        """Cross-sectional residual: f_neutral = f - beta*log(mcap) per day."""
        f_out = np.asarray(f_period, dtype=np.float32).copy()
        for t in range(f_out.shape[0]):
            valid = ~np.isnan(f_out[t]) & ~np.isnan(mcap_period[t])
            if valid.sum() < 30:
                continue
            from scipy import stats
            resid = stats.linregress(np.log(np.maximum(mcap_period[t][valid], 1)), f_out[t][valid])[1]
            f_out[t][valid] = np.float32(resid)
        return f_out

    # Get ALL single factor expressions
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT expression FROM alpha_history
        WHERE type IS NULL OR type != 'superalpha'
    """).fetchall()
    conn.close()

    expressions = [r[0] for r in rows]
    total = len(expressions)
    print(f"Total factors to re-backtest: {total}")
    print(f"Estimated: {total * 10 / 60:.0f} min (10s per factor)\n")

    success = 0
    errors = 0
    t_start = datetime.now()

    for i, expr in enumerate(expressions):
        try:
            # Parse factor
            factor_arr = parse_expression(expr, pipeline, fc)
            if factor_arr is None:
                errors += 1
                continue

            # IS evaluation with neutralization
            f_is_raw = np.asarray(factor_arr[t0_is:t1_is], dtype=np.float32)
            mcap_is = np.asarray(mcap[t0_is:t1_is], dtype=np.float64)
            f_is = apply_mcap_neutralize(f_is_raw, mcap_is)
            del f_is_raw

            res_is = engine.full_evaluation(f_is, univ[t0_is:t1_is], label=label[t0_is:t1_is])
            m_is = _compute_metrics_from_result(f_is, label[t0_is:t1_is], univ[t0_is:t1_is], res_is)

            # OOS evaluation with neutralization
            f_oos_raw = np.asarray(factor_arr[t0_oos:t1_oos], dtype=np.float32)
            mcap_oos = np.asarray(mcap[t0_oos:t1_oos], dtype=np.float64)
            f_oos = apply_mcap_neutralize(f_oos_raw, mcap_oos)
            del f_oos_raw

            res_oos = engine.full_evaluation(f_oos, univ[t0_oos:t1_oos], label=label[t0_oos:t1_oos])
            m_oos = _compute_metrics_from_result(f_oos, label[t0_oos:t1_oos], univ[t0_oos:t1_oos], res_oos)

            # Merge metrics
            metrics = {k: v for k, v in m_oos.items() if k not in ('_factor_array', '_direction')}
            for k in ['pearson_ic','sharpe','icir','fitness','annual_excess','returns','max_drawdown',
                       'turnover','margin_bps','win_rate','pnl_series']:
                v = m_is.get(k)
                if v is not None:
                    metrics['is_' + k] = v
            metrics['oos_pearson_ic'] = m_oos.get('pearson_ic')
            metrics['_neutralize'] = 'market_cap'

            _add_to_history(expr, metrics, 'alpha', name=expr[:40])

            del factor_arr, f_is, f_oos, mcap_is, mcap_oos
            success += 1

        except Exception as e:
            errors += 1
            if errors <= 5:
                traceback.print_exc()

        if (i + 1) % 50 == 0:
            elapsed = (datetime.now() - t_start).total_seconds()
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate / 60
            gc.collect()
            print(f'[{i+1}/{total}] OK:{success} ERR:{errors} Rate:{rate:.1f}/s ETA:{eta:.0f}min | {datetime.now().strftime("%H:%M:%S")}', flush=True)

    elapsed = (datetime.now() - t_start).total_seconds()
    print(f'\n=== DONE: {success}/{total} OK, {errors} ERR in {elapsed/60:.1f}min ===')
    print(f'End: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
