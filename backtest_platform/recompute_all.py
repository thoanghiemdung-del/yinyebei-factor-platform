"""Recompute all alpha records with new pure-long-only PnL metrics.
Standalone: imports data pipeline directly, NOT Flask app.py, to avoid DB lock."""
import sys, os, json, math, sqlite3, time
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
sys.path.insert(0, 'D:/yyb/模型')
import numpy as np

# Import underlying modules directly (NOT Flask app)
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from factor_library import FactorComputer
from expression_parser import parse_expression

DB_PATH = os.path.join(script_dir, "backtest.db")

# ---- Copy of _compute_metrics_from_result (pure long-only) ----

def compute_metrics(factor_train, label_train, univ_train, result, top_pct=0.1):
    direction = 1
    n_dates = factor_train.shape[0]
    daily_excess = []  # Top10% - Market average
    daily_top_set = []
    for t in range(n_dates):
        f = factor_train[t]
        l = label_train[t]
        valid = univ_train[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100:
            daily_excess.append(None)
            daily_top_set.append(set())
            continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * top_pct))
        order = np.argsort(fv)
        if direction > 0:
            top_idx = order[-n_top:]
        else:
            top_idx = order[:n_top]
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
        prev = daily_top_set[t-1]; curr = daily_top_set[t]
        if len(prev)>0 and len(curr)>0:
            overlap = len(prev & curr)
            to = 1.0 - overlap / max(len(prev), len(curr))
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
    neg_excess = excess_arr[excess_arr < 0]
    downside_std = float(np.std(neg_excess)) if len(neg_excess) > 0 else excess_std
    sortino = ann_excess / (downside_std * np.sqrt(250) + 1e-10)
    win_rate = float((excess_arr > 0).mean())

    ic_series = result.get('ic_series', np.array([]))
    ic_series_display = [round(float(x), 4) if not np.isnan(x) else None for x in ic_series[-60:]]
    pnl_display = [None if x is None or math.isnan(float(x)) else float(x) for x in cum_pnl]

    def safe_round(val, ndigits):
        try:
            v=float(val)
            return round(v,ndigits) if not math.isnan(v) and not math.isinf(v) else None
        except: return None

    return {
        'pearson_ic': safe_round(result.get('mean_pearson_ic', 0), 4),
        'rank_ic': safe_round(result.get('mean_rank_ic', 0), 4),
        'icir': safe_round(result.get('icir', 0), 3),
        'ic_positive_ratio': safe_round(result.get('ic_positive_ratio', 0), 3),
        'annual_excess': safe_round(ann_excess, 4),
        'sharpe': safe_round(wq_sharpe, 3),
        'fitness': safe_round(wq_fitness, 3),
        'returns': safe_round(ann_excess, 4),
        'max_drawdown': safe_round(max_dd, 4),
        'turnover': safe_round(avg_turnover, 4),
        'margin_bps': safe_round(wq_margin, 1),
        'sortino': safe_round(sortino, 3),
        'win_rate': safe_round(win_rate, 3),
        'n_days': int(result['n_eval_days']) if result.get('n_eval_days') else 0,
        'ic_series': ic_series_display,
        'pnl_series': pnl_display,
    }

# ---- Main ----

print("Loading DataPipeline...")
pipeline = DataPipeline()
print(f"Loaded: {pipeline.n_dates} days x {pipeline.n_stocks} stocks")
engine = BacktestEngine(pipeline)
fc = FactorComputer(pipeline)
print("FactorComputer ready.")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM alpha_history ORDER BY rowid")
rows = cur.fetchall()
print(f"Found {len(rows)} records\n")

for i, row in enumerate(rows):
    expr = row["expression"]
    rec_type = row["type"]
    name = row["name"]
    rid = row["id"]

    print(f"[{i+1}/{len(rows)}] {name} ({rec_type})  ", end="", flush=True)
    t0_p = time.time()

    try:
        factor = parse_expression(expr, pipeline, fc)
    except Exception as e:
        print(f"SKIP: parse error: {e}")
        continue

    t0_d = pipeline.date_to_idx.get('2020-01-02', 0)
    t1_d = min(pipeline.date_to_idx.get('2023-12-29', pipeline.n_dates) + 1, pipeline.n_dates)
    factor_train = factor[t0_d:t1_d]
    label_train = pipeline.fields['Label'][t0_d:t1_d]
    univ_train = pipeline.universe_mask[t0_d:t1_d]

    result = engine.full_evaluation(factor_train, univ_train, label=label_train)
    metrics = compute_metrics(factor_train, label_train, univ_train, result, top_pct=0.1)

    old_json = json.loads(row["metrics_json"] or "{}")
    new_ic = metrics.get("pearson_ic") or 0
    old_ic = old_json.get("pearson_ic") or 0
    new_ex = metrics.get("annual_excess") or 0
    old_ex = old_json.get("annual_excess") or 0

    print(f"IC:{old_ic:.4f}->{new_ic:.4f} Ex:{old_ex:.4f}->{new_ex:.4f} ({time.time()-t0_p:.1f}s)")

    # Build JSONs
    metrics_json = json.dumps({k: v for k, v in metrics.items()
                               if k not in ('ic_series', 'pnl_series')})
    pnl_json = json.dumps(metrics.get('pnl_series', []))
    ic_json = json.dumps(metrics.get('ic_series', []))

    cur.execute("UPDATE alpha_history SET metrics_json=?, pnl_json=?, ic_json=? WHERE id=?",
                (metrics_json, pnl_json, ic_json, rid))
    conn.commit()

conn.close()
print("\nDone.")
