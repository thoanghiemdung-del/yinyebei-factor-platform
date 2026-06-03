"""Final backfill: compute in-process, bulk-import via subprocess to bypass sqlite3 bug."""
import sys, os, time, json, uuid, datetime, math, gc
import numpy as np
import sqlite3 as sq

sys.path.insert(0, 'D:/yyb/backtest_platform')
sys.path.insert(0, 'D:/yyb/模型')
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

DB = 'D:/yyb/backtest_platform/backtest.db'
QUEUE = 'D:/yyb/backtest_platform/factor_queue.txt'
PYTHON = 'python'

def compute_metrics(factor_arr, label, univ, result, top_pct=0.1):
    n_dates = factor_arr.shape[0]
    daily_excess, daily_top_set = [], []
    for t in range(n_dates):
        f = factor_arr[t]; l = label[t]
        valid = univ[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100:
            daily_excess.append(None); daily_top_set.append(set())
            continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * top_pct))
        top_idx = (-fv).argsort()[:n_top]
        daily_excess.append(float(np.nanmean(lv[top_idx])) - float(np.nanmean(lv)))
        daily_top_set.append(set(np.where(valid)[0][top_idx]))

    excess_arr = np.array([x for x in daily_excess if x is not None])
    excess_mean = float(np.mean(excess_arr))
    excess_std = float(np.std(excess_arr))
    ann_excess = excess_mean * 250
    wq_sharpe = ann_excess / (excess_std * np.sqrt(250) + 1e-10)

    turnovers = []
    for t in range(1, len(daily_top_set)):
        prev, curr = daily_top_set[t-1], daily_top_set[t]
        if len(prev) > 0 and len(curr) > 0:
            turnovers.append(1.0 - len(prev & curr) / max(len(prev), len(curr)))
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

def flush_batch(batch, batch_num):
    """Write accumulated results to JSON, import via subprocess."""
    if not batch:
        return 0
    tf = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8',
        dir='D:/yyb/backtest_platform')
    json.dump(batch, tf)
    tf.close()

    importer = f'''
import json, sqlite3
DB = r'{DB}'
with open(r'{tf.name}', 'r', encoding='utf-8') as f:
    batch = json.load(f)
conn = sqlite3.connect(DB)
n = 0
for row in batch:
    conn.execute(
        'INSERT OR IGNORE INTO alpha_history (id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (row['id'], row['name'], row['expression'], row['timestamp'],
         row['type'], row['metrics_json'], row['pnl_json'], row['ic_json']))
    n += 1
conn.commit()
conn.execute('PRAGMA wal_checkpoint(PASSIVE)')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM alpha_history')
actual = cur.fetchone()[0]
conn.close()
print('IMPORTED', n, 'DB_COUNT=', actual, end='')
'''
    result = subprocess.run([PYTHON, '-c', importer], capture_output=True, text=True, timeout=60)
    os.unlink(tf.name)
    if result.returncode != 0:
        print(f'  IMPORT ERROR: {result.stderr}', flush=True)
        return 0
    stdout = result.stdout.strip()
    imported = int(stdout.split()[1])
    return imported

# ===== MAIN =====
print('Loading engine...', flush=True)
t0 = time.time()
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
print(f'Ready. IS:[{tis}:{tie}] OOS:[{tos}:{toe}] in {time.time()-t0:.0f}s', flush=True)

with open(QUEUE, 'r', encoding='utf-8') as f:
    all_exprs = [l.strip().split('|')[0].strip() for l in f if l.strip()]

# Get existing expressions from DB
c = sq.connect(DB)
existing = {r[0] for r in c.execute('SELECT expression FROM alpha_history')}
c.close()

todo = [(i, e) for i, e in enumerate(all_exprs) if e not in existing]
n_todo = len(todo)
print(f'Queue: {len(all_exprs)}, In DB: {len(existing)}, To do: {n_todo}', flush=True)

if n_todo == 0:
    print('ALL DONE!', flush=True)
    sys.exit(0)

done, errors = 0, 0

for idx, expr in todo:
    try:
        fa = parse_expression(expr, pipeline, engine)
        if fa is None: errors += 1; continue

        fi = np.asarray(fa[tis:tie], dtype=np.float32)
        ri = engine.full_evaluation(fi, U[tis:tie], label=L[tis:tie])
        mi = compute_metrics(fi, L[tis:tie], U[tis:tie], ri)

        fo = np.asarray(fa[tos:toe], dtype=np.float32)
        ro = engine.full_evaluation(fo, U[tos:toe], label=L[tos:toe])
        mo = compute_metrics(fo, L[tos:toe], U[tos:toe], ro)

        m_merge = {k: v for k, v in mo.items() if k not in ('_factor_array', '_direction')}
        for k in ['pearson_ic', 'sharpe', 'icir', 'fitness', 'annual_excess',
                   'returns', 'max_drawdown', 'turnover', 'margin_bps', 'win_rate', 'pnl_series']:
            v = mi.get(k)
            if v is not None: m_merge['is_' + k] = v
        m_merge['oos_pearson_ic'] = mo.get('pearson_ic')

        internal = {'_factor_array', '_direction', 'ic_series', 'pnl_series'}
        eid = str(uuid.uuid4())
        ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        mj = json.dumps({k: v for k, v in m_merge.items() if k not in internal})
        pj = json.dumps(m_merge.get('pnl_series', []))
        ij = json.dumps(m_merge.get('ic_series', []))

        conn = sq.connect(DB)
        conn.execute('INSERT INTO alpha_history (id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) '
                     'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                     (eid, expr[:40], expr, ts, 'alpha', mj, pj, ij))
        conn.commit()
        conn.close()
        done += 1

        del fa, fi, fo, ri, ro, mi, mo, m_merge
    except Exception as e:
        errors += 1
        if errors <= 5: print(f'  ERR[{idx}]: {e}', flush=True)

    if (done + errors) % 50 == 0:
        elapsed = time.time() - t0
        now = sq.connect(DB).execute('SELECT COUNT(*) FROM alpha_history').fetchone()[0]
        pct = (done + errors) / n_todo * 100
        print(f'[{done+errors}/{n_todo}] {pct:.0f}% done={done} err={errors} '
              f'db={now} elapsed={elapsed/60:.0f}min', flush=True)
        gc.collect()

elapsed = time.time() - t0
final = sq.connect(DB).execute('SELECT COUNT(*) FROM alpha_history').fetchone()[0]
print(f'DONE: {done} saved, {errors} errors. DB: {final} in {elapsed/60:.0f}min', flush=True)
