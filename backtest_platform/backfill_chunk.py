"""Process a range of expressions from factor_queue.txt. Called in parallel with --start/--end."""
import sys, os, time, json, gc, uuid, datetime, traceback, argparse
import numpy as np
import sqlite3 as sq

sys.path.insert(0, 'D:/yyb/backtest_platform')
sys.path.insert(0, 'D:/yyb/模型')
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

DB = 'D:/yyb/backtest_platform/backtest.db'
QUEUE = 'D:/yyb/backtest_platform/factor_queue.txt'

def compute_metrics(factor_arr, label, univ, result, top_pct=0.1):
    import math
    n_dates = factor_arr.shape[0]
    daily_excess = []
    daily_top_set = []
    for t in range(n_dates):
        f = factor_arr[t]
        l = label[t]
        valid = univ[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100:
            daily_excess.append(None)
            daily_top_set.append(set())
            continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * top_pct))
        top_idx = (-fv).argsort()[:n_top]  # descending = buy high factor values
        long_ret = float(np.nanmean(lv[top_idx]))
        mkt_ret = float(np.nanmean(lv))
        daily_excess.append(long_ret - mkt_ret)
        global_idx = np.where(valid)[0][top_idx]
        daily_top_set.append(set(global_idx))

    excess_arr = np.array([x for x in daily_excess if x is not None])
    excess_mean = float(np.mean(excess_arr))
    excess_std = float(np.std(excess_arr))
    ann_excess = excess_mean * 250
    wq_sharpe = ann_excess / (excess_std * np.sqrt(250) + 1e-10)

    turnovers = []
    for t in range(1, len(daily_top_set)):
        prev, curr = daily_top_set[t - 1], daily_top_set[t]
        if len(prev) > 0 and len(curr) > 0:
            to = 1.0 - len(prev & curr) / max(len(prev), len(curr))
            turnovers.append(to)
    avg_turnover = float(np.mean(turnovers)) if turnovers else 0.0

    fitness_denom = max(avg_turnover, 0.125)
    wq_fitness = wq_sharpe * np.sqrt(abs(ann_excess) / fitness_denom) if ann_excess != 0 else 0.0

    cum = 0.0; peak = 0.0; max_dd = 0.0; cum_pnl = []
    for r in daily_excess:
        if r is not None:
            cum += r
            if cum > peak: peak = cum
            dd = peak - cum
            if dd > max_dd: max_dd = dd
        cum_pnl.append(float(cum * 100))

    wq_margin = float(excess_mean / (np.mean(np.abs(excess_arr)) + 1e-10) * 10000)
    win_rate = float((excess_arr > 0).mean())

    ic_series = result.get('ic_series', np.array([]))
    ic_display = [round(float(x), 4) if not np.isnan(x) else None for x in ic_series[-60:]]
    pnl_display = [None if x is None or math.isnan(float(x)) else float(x) for x in cum_pnl]

    def sr(val, ndigits):
        try:
            v = float(val)
            return round(v, ndigits) if not math.isnan(v) and not math.isinf(v) else None
        except: return None

    return {
        'pearson_ic': sr(result.get('mean_pearson_ic', 0), 4),
        'icir': sr(result.get('icir', 0), 3),
        'ic_positive_ratio': sr(result.get('ic_positive_ratio', 0), 3),
        'annual_excess': sr(ann_excess, 4), 'sharpe': sr(wq_sharpe, 3),
        'fitness': sr(wq_fitness, 3), 'returns': sr(ann_excess, 4),
        'max_drawdown': sr(max_dd, 4), 'turnover': sr(avg_turnover, 4),
        'margin_bps': sr(wq_margin, 1), 'win_rate': sr(win_rate, 3),
        'n_days': int(result['n_eval_days']) if result.get('n_eval_days') else 0,
        'ic_series': ic_display, 'pnl_series': pnl_display,
        '_factor_array': factor_arr, '_direction': 1,
    }

def save_to_db(expr, metrics):
    internal = {'_factor_array', '_direction', 'ic_series', 'pnl_series'}
    name = expr[:40]
    eid = str(uuid.uuid4())
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    mj = json.dumps({k: v for k, v in metrics.items() if k not in internal})
    pj = json.dumps(metrics.get('pnl_series', []))
    ij = json.dumps(metrics.get('ic_series', []))

    for attempt in range(5):
        try:
            conn = sq.connect(DB)
            conn.execute('PRAGMA journal_mode=DELETE')
            conn.execute('PRAGMA busy_timeout=5000')
            conn.execute(
                'INSERT INTO alpha_history (id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (eid, name, expr, ts, 'alpha', mj, pj, ij))
            conn.commit()
            conn.close()
            return True
        except sq.IntegrityError:
            # Duplicate expression — already saved by previous attempt
            conn.close()
            return False
        except sq.OperationalError as e:
            conn.close()
            if 'locked' in str(e).lower() and attempt < 4:
                time.sleep(2 ** attempt)
            else:
                raise

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', type=int, required=True)
    ap.add_argument('--end', type=int, required=True)
    ap.add_argument('--worker-id', type=int, default=0)
    args = ap.parse_args()

    t0 = time.time()
    tag = f'[W{args.worker_id}]'

    # Load data
    pipeline = DataPipeline()
    engine = BacktestEngine(pipeline)
    dk = sorted(pipeline.date_to_idx.keys())
    tis = pipeline.date_to_idx['2020-01-02']
    tie = None
    for d in reversed(dk):
        if d < '2023-01-01': tie = pipeline.date_to_idx[d] + 1; break
    tos = None
    for d in dk:
        if d >= '2023-01-01': tos = pipeline.date_to_idx[d]; break
    toe = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
    L = pipeline.fields['Label']
    U = pipeline.universe_mask

    # Load queue
    with open(QUEUE, 'r', encoding='utf-8') as f:
        all_exprs = [l.strip().split('|')[0].strip() for l in f if l.strip()]

    my_exprs = all_exprs[args.start:args.end]
    done, errors, skipped = 0, 0, 0
    t_batch = time.time()
    batch_done = 0

    for i, expr in enumerate(my_exprs):
        try:
            fa = parse_expression(expr, pipeline, engine)
            if fa is None:
                skipped += 1; continue

            fi = np.asarray(fa[tis:tie], dtype=np.float32)
            ri = engine.full_evaluation(fi, U[tis:tie], label=L[tis:tie])
            mi = compute_metrics(fi, L[tis:tie], U[tis:tie], ri)

            fo = np.asarray(fa[tos:toe], dtype=np.float32)
            ro = engine.full_evaluation(fo, U[tos:toe], label=L[tos:toe])
            mo = compute_metrics(fo, L[tos:toe], U[tos:toe], ro)

            m = {k: v for k, v in mo.items() if k not in ('_factor_array', '_direction')}
            for k in ['pearson_ic', 'sharpe', 'icir', 'fitness', 'annual_excess',
                       'returns', 'max_drawdown', 'turnover', 'margin_bps', 'win_rate', 'pnl_series']:
                v = mi.get(k)
                if v is not None: m['is_' + k] = v
            m['oos_pearson_ic'] = mo.get('pearson_ic')

            if save_to_db(expr, m):
                done += 1; batch_done += 1
            del fa, fi, fo, ri, ro, mi, mo, m

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f'{tag} ERR[{args.start+i}]: {e}', flush=True)

        if batch_done >= 5:
            elapsed = time.time() - t_batch
            total_elapsed = time.time() - t0
            pct = (i + 1) / len(my_exprs) * 100
            rate = batch_done / elapsed if elapsed > 0 else 0
            print(f'{tag} [{args.start+i+1}/{args.end}] {pct:.0f}% done={done} err={errors} '
                  f'rate={rate:.1f}/s total_elapsed={total_elapsed/60:.0f}min', flush=True)
            gc.collect()
            t_batch = time.time()
            batch_done = 0

    total = time.time() - t0
    print(f'{tag} DONE range=[{args.start}:{args.end}] saved={done} errors={errors} in {total/60:.0f}min', flush=True)

if __name__ == '__main__':
    main()
