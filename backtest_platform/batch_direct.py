"""Direct backtest runner — bypasses Flask API for speed."""
import sys, os, json, math, time, sqlite3, uuid, datetime
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
sys.path.insert(0, 'D:/yyb/模型')
import numpy as np

from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

QUEUE_FILE = os.path.join(script_dir, "factor_queue.txt")
DB_PATH = os.path.join(script_dir, "backtest.db")

# Same compute_metrics as recompute_all.py (pure long-only)
def compute_metrics(factor_train, label_train, univ_train, result, top_pct=0.1):
    direction = 1
    n_dates = factor_train.shape[0]
    daily_excess = []
    daily_top_set = []
    for t in range(n_dates):
        f = factor_train[t]; l = label_train[t]
        valid = univ_train[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100:
            daily_excess.append(None); daily_top_set.append(set()); continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * top_pct))
        order = np.argsort(fv)
        top_idx = order[-n_top:] if direction > 0 else order[:n_top]
        long_ret = float(np.nanmean(lv[top_idx]))
        mkt_ret = float(np.nanmean(lv))
        daily_excess.append(long_ret - mkt_ret)
        global_idx = np.where(valid)[0][top_idx]
        daily_top_set.append(set(global_idx))

    excess_arr = np.array([x for x in daily_excess if x is not None])
    excess_mean = float(np.mean(excess_arr)); excess_std = float(np.std(excess_arr))
    ann_excess = excess_mean * 250
    wq_sharpe = ann_excess / (excess_std * np.sqrt(250) + 1e-10)

    turnovers = []
    for t in range(1, len(daily_top_set)):
        prev = daily_top_set[t-1]; curr = daily_top_set[t]
        if len(prev)>0 and len(curr)>0:
            overlap = len(prev & curr)
            turnovers.append(1.0 - overlap / max(len(prev), len(curr)))
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
    neg_excess = excess_arr[excess_arr < 0]
    downside_std = float(np.std(neg_excess)) if len(neg_excess) > 0 else excess_std
    sortino = ann_excess / (downside_std * np.sqrt(250) + 1e-10)
    win_rate = float((excess_arr > 0).mean())
    ic_series = result.get('ic_series', np.array([]))
    ic_display = [round(float(x),4) if not np.isnan(x) else None for x in ic_series[-60:]]
    pnl_display = [None if x is None or math.isnan(float(x)) else float(x) for x in cum_pnl]

    def sr(v, n):
        try: vv=float(v); return round(vv,n) if not math.isnan(vv) and not math.isinf(vv) else None
        except: return None

    return {
        'pearson_ic': sr(result.get('mean_pearson_ic',0),4),
        'rank_ic': sr(result.get('mean_rank_ic',0),4),
        'icir': sr(result.get('icir',0),3),
        'ic_positive_ratio': sr(result.get('ic_positive_ratio',0),3),
        'annual_excess': sr(ann_excess,4),
        'sharpe': sr(wq_sharpe,3),
        'fitness': sr(wq_fitness,3),
        'returns': sr(ann_excess,4),
        'max_drawdown': sr(max_dd,4),
        'turnover': sr(avg_turnover,4),
        'margin_bps': sr(wq_margin,1),
        'sortino': sr(sortino,3),
        'win_rate': sr(win_rate,3),
        'n_days': int(result['n_eval_days']) if result.get('n_eval_days') else 0,
        'ic_series': ic_display,
        'pnl_series': pnl_display,
    }

def save_to_db(expression, metrics):
    name = expression[:40] + ('...' if len(expression) > 40 else '')
    eid = str(uuid.uuid4())
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    metrics_json = json.dumps({k:v for k,v in metrics.items() if k not in ('ic_series','pnl_series')})
    pnl_json = json.dumps(metrics.get('pnl_series',[]))
    ic_json = json.dumps(metrics.get('ic_series',[]))
    db = sqlite3.connect(DB_PATH)
    db.execute('INSERT INTO alpha_history (id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) VALUES (?,?,?,?,?,?,?,?)',
               (eid, name, expression, ts, 'alpha', metrics_json, pnl_json, ic_json))
    db.commit(); db.close()

def already_done(expr):
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.execute("SELECT COUNT(*) FROM alpha_history WHERE type='alpha' AND expression=?", (expr,))
    n = c.fetchone()[0]; db.close()
    return n > 0

# ---- MAIN ----
print("Loading pipeline...", flush=True)
pipeline = DataPipeline()
engine = BacktestEngine(pipeline)
print("Ready.", flush=True)

t0_d = pipeline.date_to_idx['2020-01-02']
t1_d = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
label_train = pipeline.fields['Label'][t0_d:t1_d]
univ_train = pipeline.universe_mask[t0_d:t1_d]

while True:
    lines = [l.strip() for l in open(QUEUE_FILE, encoding='utf-8').readlines() if l.strip()]
    if not lines:
        print("Queue empty!")
        break

    line = lines[0]
    parts = line.split("|")
    expr = parts[0].strip()
    neut = parts[1].strip() if len(parts) > 1 else "none"

    if already_done(expr):
        print(f"[SKIP] {expr[:50]}")
        open(QUEUE_FILE,'w',encoding='utf-8').writelines(l+'\n' for l in lines[1:])
        continue

    print(f"[{len(lines)} left] {expr[:60]}... ", end="", flush=True)
    t0 = time.time()
    try:
        factor = parse_expression(expr, pipeline, None)
        ft = factor[t0_d:t1_d]

        if neut == 'market_cap':
            adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                     pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(ft[0]))), 0.01, 100)
            mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES', pipeline.fields.get('I_D_SHARE_LIQA', np.ones_like(ft[0])))
            mcap_train = mcap[t0_d:t1_d]
            for t in range(ft.shape[0]):
                valid = ~np.isnan(ft[t]) & ~np.isnan(mcap_train[t])
                if valid.sum() < 100: continue
                log_mcap = np.log(np.maximum(mcap_train[t, valid], 1))
                group_ids = np.floor(np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0,101,10))) / 10).astype(int)
                fv = ft[t, valid].copy()
                for g in np.unique(group_ids):
                    gmask = group_ids == g
                    if gmask.sum() >= 10: fv[gmask] = fv[gmask] - np.nanmean(fv[gmask])
                ft[t, valid] = fv

        result = engine.full_evaluation(ft, univ_train, label=label_train)
        metrics = compute_metrics(ft, label_train, univ_train, result)
        save_to_db(expr, metrics)

        ic = metrics.get('pearson_ic') or 0
        ex = metrics.get('annual_excess') or 0
        sh = metrics.get('sharpe') or 0
        ok = "OK" if abs(ic) >= 0.01 else "LOW"
        print(f"IC={ic:.4f} Ex={ex:.4f} Sh={sh:.2f} [{ok}] ({time.time()-t0:.1f}s)", flush=True)

        open(QUEUE_FILE,'w',encoding='utf-8').writelines(l+'\n' for l in lines[1:])

    except Exception as e:
        print(f"ERROR: {e}", flush=True)
        open(QUEUE_FILE,'w',encoding='utf-8').writelines(l+'\n' for l in lines[1:])

print("All done.")
