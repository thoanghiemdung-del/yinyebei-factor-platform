"""Single-process backfill: read factor_queue.txt, evaluate each, write to SQLite.
Resumes automatically — skips expressions already in DB.
P0: Fixes the two-process conflict and silent error swallowing from the previous attempt.
"""
import sys, os, time, json, gc, uuid, datetime, traceback
import numpy as np
import sqlite3 as sq

sys.path.insert(0, 'D:/yyb/backtest_platform')
sys.path.insert(0, 'D:/yyb/模型')
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

DB = 'D:/yyb/backtest_platform/backtest.db'
QUEUE = 'D:/yyb/backtest_platform/factor_queue.txt'
LOG = 'D:/yyb/logs/backfill.log'

def log(msg):
    t = datetime.datetime.now().strftime('%H:%M:%S')
    line = f'[{t}] {msg}'
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def get_existing_exprs():
    """Return set of expressions already in DB (for resume)."""
    conn = sq.connect(DB)
    rows = conn.execute('SELECT expression FROM alpha_history').fetchall()
    conn.close()
    return {r[0] for r in rows}

def load_queue():
    exprs = []
    with open(QUEUE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            expr = line.split('|')[0].strip()
            if expr:
                exprs.append(expr)
    return exprs

def compute_metrics(factor_arr, label, univ, result, top_pct=0.1):
    """Mirror of app._compute_metrics_from_result, standalone so we don't need Flask."""
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
        order = np.argsort(fv)
        top_idx = order[-n_top:]
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
        prev = daily_top_set[t - 1]
        curr = daily_top_set[t]
        if len(prev) > 0 and len(curr) > 0:
            overlap = len(prev & curr)
            to = 1.0 - overlap / max(len(prev), len(curr))
            turnovers.append(to)
    avg_turnover = float(np.mean(turnovers)) if turnovers else 0.0

    fitness_denom = max(avg_turnover, 0.125)
    wq_fitness = wq_sharpe * np.sqrt(abs(ann_excess) / fitness_denom) if ann_excess != 0 else 0.0

    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    cum_pnl = []
    for r in daily_excess:
        if r is not None:
            cum += r
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        cum_pnl.append(float(cum * 100))

    wq_margin = float(excess_mean / (np.mean(np.abs(excess_arr)) + 1e-10) * 10000)
    win_rate = float((excess_arr > 0).mean())

    ic_series = result.get('ic_series', np.array([]))
    ic_series_display = [round(float(x), 4) if not np.isnan(x) else None
                         for x in ic_series[-60:]]
    pnl_display = [None if x is None or math.isnan(float(x)) else float(x) for x in cum_pnl]

    def safe_round(val, ndigits):
        try:
            v = float(val)
            return round(v, ndigits) if not math.isnan(v) and not math.isinf(v) else None
        except Exception:
            return None

    return {
        'pearson_ic': safe_round(result.get('mean_pearson_ic', 0), 4),
        'icir': safe_round(result.get('icir', 0), 3),
        'ic_positive_ratio': safe_round(result.get('ic_positive_ratio', 0), 3),
        'annual_excess': safe_round(ann_excess, 4),
        'sharpe': safe_round(wq_sharpe, 3),
        'fitness': safe_round(wq_fitness, 3),
        'returns': safe_round(ann_excess, 4),
        'max_drawdown': safe_round(max_dd, 4),
        'turnover': safe_round(avg_turnover, 4),
        'margin_bps': safe_round(wq_margin, 1),
        'win_rate': safe_round(win_rate, 3),
        'n_days': int(result['n_eval_days']) if result.get('n_eval_days') else 0,
        'ic_series': ic_series_display,
        'pnl_series': pnl_display,
        '_factor_array': factor_arr,
        '_direction': 1,
    }

def save_to_db(expr, metrics):
    internal_keys = {'_factor_array', '_direction', 'ic_series', 'pnl_series'}
    name = expr[:40]
    entry_id = str(uuid.uuid4())
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    metrics_json = json.dumps({k: v for k, v in metrics.items() if k not in internal_keys})
    pnl_json = json.dumps(metrics.get('pnl_series', []))
    ic_json = json.dumps(metrics.get('ic_series', []))

    conn = sq.connect(DB)
    conn.execute(
        'INSERT INTO alpha_history (id, name, expression, timestamp, type, '
        'metrics_json, pnl_json, ic_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (entry_id, name, expr, ts, 'alpha', metrics_json, pnl_json, ic_json)
    )
    conn.commit()
    conn.close()

# ===== Main =====
if __name__ == '__main__':
    log('=== Backfill runner starting ===')

    # 1. Load data engine
    log('Loading DataPipeline + BacktestEngine...')
    pipeline = DataPipeline()
    engine = BacktestEngine(pipeline)
    log('Engine ready.')

    # 2. Date boundaries
    dk = sorted(pipeline.date_to_idx.keys())
    tis = pipeline.date_to_idx['2020-01-02']
    tie = None
    for d in reversed(dk):
        if d < '2023-01-01':
            tie = pipeline.date_to_idx[d] + 1
            break
    tos = None
    for d in dk:
        if d >= '2023-01-01':
            tos = pipeline.date_to_idx[d]
            break
    toe = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
    log(f'IS: [{tis}:{tie}] OOS: [{tos}:{toe}]')

    L = pipeline.fields['Label']
    U = pipeline.universe_mask

    # 3. Load queue and filter already-done
    all_exprs = load_queue()
    log(f'Queue: {len(all_exprs)} expressions')
    existing = get_existing_exprs()
    todo = [(i, e) for i, e in enumerate(all_exprs) if e not in existing]
    log(f'Already in DB: {len(existing)}, Remaining: {len(todo)}')

    if not todo:
        log('Nothing to do. Exiting.')
        sys.exit(0)

    # 4. Process
    done, errors = 0, 0
    t_start = time.time()
    conn = sq.connect(DB)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.close()

    for idx, expr in todo:
        try:
            fa = parse_expression(expr, pipeline, engine)
            if fa is None:
                errors += 1
                if errors <= 5:
                    log(f'  SKIP[{idx}]: parse_expression returned None: {expr[:60]}')
                continue

            fi = np.asarray(fa[tis:tie], dtype=np.float32)
            ri = engine.full_evaluation(fi, U[tis:tie], label=L[tis:tie])
            mi = compute_metrics(fi, L[tis:tie], U[tis:tie], ri)

            fo = np.asarray(fa[tos:toe], dtype=np.float32)
            ro = engine.full_evaluation(fo, U[tos:toe], label=L[tos:toe])
            mo = compute_metrics(fo, L[tos:toe], U[tos:toe], ro)

            # Merge: OOS metrics as base, IS metrics with is_ prefix
            m = {k: v for k, v in mo.items() if k not in ('_factor_array', '_direction')}
            for k in ['pearson_ic', 'sharpe', 'icir', 'fitness', 'annual_excess',
                       'returns', 'max_drawdown', 'turnover', 'margin_bps', 'win_rate', 'pnl_series']:
                v = mi.get(k)
                if v is not None:
                    m['is_' + k] = v
            m['oos_pearson_ic'] = mo.get('pearson_ic')

            save_to_db(expr, m)
            done += 1
            del fa, fi, fo, ri, ro, mi, mo, m

        except Exception as e:
            errors += 1
            if errors <= 10:
                log(f'  ERR[{idx}]: {e}')
                traceback.print_exc()

        # Progress every 10
        if (done + errors) % 10 == 0:
            elapsed = time.time() - t_start
            rate = (done + errors) / elapsed if elapsed > 0 else 0
            eta = (len(todo) - done - errors) / rate if rate > 0 else 0
            log(f'[{done+errors}/{len(todo)}] saved={done} errs={errors} '
                f'rate={rate:.1f}/s ETA={eta/60:.0f}min mem={gc.get_count()}')
            gc.collect()

    elapsed = time.time() - t_start
    log(f'=== DONE: {done} saved, {errors} errors in {elapsed/60:.1f}min ===')
