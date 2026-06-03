"""Backfill v2: all logic inline, explicit DB verification after every batch."""
import sys, os, time, json, gc, uuid, datetime, traceback, math
import numpy as np
import sqlite3

sys.path.insert(0, 'D:/yyb/backtest_platform')
sys.path.insert(0, 'D:/yyb/模型')
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

DB = 'D:/yyb/backtest_platform/backtest.db'
QUEUE = 'D:/yyb/backtest_platform/factor_queue.txt'
LOG = 'D:/yyb/logs/backfill_v2.log'

def log(msg):
    t = datetime.datetime.now().strftime('%H:%M:%S')
    line = f'[{t}] {msg}'
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def db_count():
    c = sqlite3.connect(DB)
    n = c.execute('SELECT COUNT(*) FROM alpha_history').fetchone()[0]
    c.close()
    return n

def compute_metrics(factor_arr, label, univ, result, top_pct=0.1):
    n_dates = factor_arr.shape[0]
    daily_excess = []
    daily_top_set = []
    for t in range(n_dates):
        f = factor_arr[t]; l = label[t]
        valid = univ[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100:
            daily_excess.append(None); daily_top_set.append(set())
            continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * top_pct))
        top_idx = (-fv).argsort()[:n_top]
        long_ret = float(np.nanmean(lv[top_idx]))
        mkt_ret = float(np.nanmean(lv))
        daily_excess.append(long_ret - mkt_ret)
        daily_top_set.append(set(np.where(valid)[0][top_idx]))

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

def main():
    log('=== Backfill V2 starting ===')
    t0 = time.time()

    # 1. Load data
    log('Loading engine...')
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
    L = pipeline.fields['Label']; U = pipeline.universe_mask
    log(f'Engine ready. IS:[{tis}:{tie}] OOS:[{tos}:{toe}]')

    # 2. Load queue + existing
    with open(QUEUE, 'r', encoding='utf-8') as f:
        all_exprs = [l.strip().split('|')[0].strip() for l in f if l.strip()]

    c = sqlite3.connect(DB)
    existing = {r[0] for r in c.execute('SELECT expression FROM alpha_history')}
    c.close()
    todo = [(i, e) for i, e in enumerate(all_exprs) if e not in existing]
    log(f'Queue: {len(all_exprs)}, In DB: {len(existing)}, To process: {len(todo)}')

    if not todo:
        log('All done! Exiting.')
        return

    # 3. Process
    done, errors = 0, 0
    n_total = len(todo)
    t_batch = time.time()
    db0 = db_count()
    log(f'Starting DB count: {db0}')

    for idx, expr in todo:
        try:
            fa = parse_expression(expr, pipeline, engine)
            if fa is None:
                errors += 1; continue

            fi = np.asarray(fa[tis:tie], dtype=np.float32)
            ri = engine.full_evaluation(fi, U[tis:tie], label=L[tis:tie])
            mi = compute_metrics(fi, L[tis:tie], U[tis:tie], ri)

            fo = np.asarray(fa[tos:toe], dtype=np.float32)
            ro = engine.full_evaluation(fo, U[tos:toe], label=L[tos:toe])
            mo = compute_metrics(fo, L[tos:toe], U[tos:toe], ro)

            # Merge metrics
            m_merge = {k: v for k, v in mo.items() if k not in ('_factor_array', '_direction')}
            for k in ['pearson_ic', 'sharpe', 'icir', 'fitness', 'annual_excess',
                       'returns', 'max_drawdown', 'turnover', 'margin_bps', 'win_rate', 'pnl_series']:
                v = mi.get(k)
                if v is not None:
                    m_merge['is_' + k] = v
            m_merge['oos_pearson_ic'] = mo.get('pearson_ic')

            # Inline save to DB
            internal = {'_factor_array', '_direction', 'ic_series', 'pnl_series'}
            eid = str(uuid.uuid4())
            ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            mj = json.dumps({k: v for k, v in m_merge.items() if k not in internal})
            pj = json.dumps(m_merge.get('pnl_series', []))
            ij = json.dumps(m_merge.get('ic_series', []))

            conn = sqlite3.connect(DB)
            conn.execute('PRAGMA journal_mode=DELETE')
            conn.execute(
                'INSERT INTO alpha_history (id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (eid, expr[:40], expr, ts, 'alpha', mj, pj, ij))
            conn.commit()
            conn.close()
            done += 1

            del fa, fi, fo, ri, ro, mi, mo, m_merge
        except Exception as e:
            errors += 1
            if errors <= 10:
                log(f'  ERR[{idx}]: {e}')

        # Progress + DB verification every 10
        if (done + errors) % 10 == 0:
            elapsed = time.time() - t0
            pct = (done + errors) / n_total * 100
            rate = (done + errors) / (time.time() - t_batch) if (time.time() - t_batch) > 0 else 0
            db_now = db_count()
            log(f'[{idx+1}/{len(all_exprs)}] {pct:.0f}% done={done} err={errors} '
                f'rate={rate:.1f}/s db={db_now} (+{db_now-db0}) elapsed={elapsed/60:.0f}min')
            t_batch = time.time()
            gc.collect()

    elapsed = time.time() - t0
    db_final = db_count()
    log(f'=== DONE: {done} saved, {errors} errors in {elapsed/60:.0f}min ===')
    log(f'Final DB count: {db_final} (started at {db0}, +{db_final-db0})')

if __name__ == '__main__':
    # Ensure DB is in DELETE mode before we start
    c = sqlite3.connect(DB)
    c.execute('PRAGMA journal_mode=DELETE')
    c.close()
    main()
