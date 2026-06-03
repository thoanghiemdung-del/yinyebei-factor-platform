#!/usr/bin/env python3
"""Direct mining — bypass Flask, access pipeline directly. 10x faster."""
import sys, os, json, sqlite3, time, datetime, gc, numpy as np
sys.path.insert(0, 'D:/yyb/模型'); sys.path.insert(0, 'D:/yyb/backtest_platform')
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from factor_library import FactorComputer
from expression_parser import parse_expression

DB = os.path.join(os.path.dirname(__file__), 'backtest.db')
LOG = os.path.join(os.path.dirname(__file__), '..', 'logs', 'direct_mine.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)
    with open(LOG, 'a', encoding='utf-8') as f: f.write(f"[{ts}] {msg}\n")

# Init once
log("Init pipeline...")
p = DataPipeline()
e = BacktestEngine(p)
fc = FactorComputer(p)
t0 = p.date_to_idx['2020-01-02']
t1 = min(p.date_to_idx['2023-12-29'] + 1, p.n_dates)
lt = p.fields['Label'][t0:t1]
ut = p.universe_mask[t0:t1]
log(f"Ready: {p.n_dates}d x {p.n_stocks}s, train={t1-t0}d")

# MCAP neutralization data
adjf = np.clip(np.where(np.isnan(p.fields.get('I_D_ADJFACTOR', np.ones((p.n_dates, p.n_stocks)))), 1.0, p.fields.get('I_D_ADJFACTOR', np.ones((p.n_dates, p.n_stocks)))), 0.01, 100)
mcap = p.fields['I_D_CLOSE_ORI'] * adjf * p.fields.get('I_D_TOTAL_SHARES', np.ones((p.n_dates, p.n_stocks)))
mcap_train = mcap[t0:t1]
log("MCAP ready")

def evaluate(expr):
    try: factor = parse_expression(expr, p, fc)
    except: return None
    gc.collect()
    ft = factor[t0:t1]
    if np.isfinite(ft).sum() < 970*100: return None
    if np.nanstd(ft[np.isfinite(ft)]) < 1e-8: return None

    # Neutralize
    for t in range(ft.shape[0]):
        valid = ~np.isnan(ft[t]) & ~np.isnan(mcap_train[t])
        if valid.sum() < 100: continue
        lm = np.log(np.maximum(mcap_train[t, valid], 1))
        gi = np.floor(np.digitize(lm, np.percentile(lm, np.arange(0, 101, 10))) / 10).astype(int)
        fv = ft[t, valid].copy()
        for g in np.unique(gi):
            gm = gi == g
            if gm.sum() >= 10: fv[gm] -= np.nanmean(fv[gm])
        ft[t, valid] = fv

    try: result = e.full_evaluation(ft, ut, lt)
    except: return None

    ic = float(result.get('mean_pearson_ic', 0))
    if abs(ic) <= 0.01: return None

    # Daily excess
    de = []; dt = []
    for t in range(ft.shape[0]):
        f, l = ft[t], lt[t]
        valid = ut[t] & (~np.isnan(f)) & (~np.isnan(l))
        if valid.sum() < 100: de.append(None); dt.append(set()); continue
        fv, lv = f[valid], l[valid]
        n_top = max(1, int(valid.sum() * 0.1))
        ti = np.argsort(fv)[-n_top:]
        de.append(float(np.nanmean(lv[ti]) - np.nanmean(lv)))
        dt.append(set(np.where(valid)[0][ti]))

    ea = np.array([x for x in de if x is not None])
    if len(ea) < 100: return None
    es = float(np.std(ea)); ae = float(np.mean(ea)) * 250
    sh = ae / (es * np.sqrt(250) + 1e-10)
    if abs(sh) > 50: return None

    ts = []
    for t in range(1, len(dt)):
        p, c = dt[t-1], dt[t]
        if len(p) > 0 and len(c) > 0: ts.append(1.0 - len(p & c) / max(len(p), len(c)))
    at = float(np.mean(ts)) if ts else 0.0
    if at < 0.01: return None

    cp = []; cum = 0.0
    for r in de:
        if r is not None: cum += r
        cp.append(float(cum * 100))

    return {'ic': ic, 'sh': sh, 'to': at, 'ae': ae, 'pnl': cp}

def load_existing():
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id,expression,pnl_json FROM alpha_history WHERE (type='alpha' OR type IS NULL) AND CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL) > 0.01").fetchall()
    conn.close()
    exist, tested = [], set()
    for row in rows:
        tested.add(row['expression'].strip())
        try:
            pnl = json.loads(row['pnl_json'] or '[]')
            if len(pnl) < 20: continue
        except: continue
        d = [pnl[i]-pnl[i-1] for i in range(1, len(pnl))]
        exist.append({'id': row['id'], 'dailies': np.array(d)})
    return exist, tested

def save(expr, m):
    import uuid
    eid = str(uuid.uuid4()); ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    clean = {}
    for k, v in [('pearson_ic', m['ic']), ('sharpe', m['sh']), ('turnover', m['to']),
                 ('annual_excess', m['ae']), ('max_drawdown', 0.0), ('fitness', 0.0)]:
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)): v = None
        clean[k] = v
    conn = sqlite3.connect(DB)
    conn.execute('INSERT INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json,max_corr) VALUES(?,?,?,?,?,?,?,?,?)',
        (eid, expr[:40], expr, ts, 'alpha', json.dumps(clean), json.dumps(m['pnl']), json.dumps([]), 0.0))
    conn.commit(); conn.close()
    return eid

# Factor batch — hand-crafted, each unique economic mechanism
# Using successful patterns from the early runs that reached IC>0.01
BATCH = []
def add(e, d): BATCH.append((e, d))

# --- DAILY SINGLE-FIELD (simple, proven to work) ---
for f, sign, desc in [
    ('ret_20d', '', '月动量'),
    ('ret_60d', '', '季动量'),
    ('ret_120d_skip5', '', '长期动量'),
    ('ret_5d', '-', '周反转'),
    ('ret_20d', '-', '月反转'),
    ('ret_60d', '-', '季反转'),
    ('vol_20d', '-', '低月波'),
    ('vol_60d', '-', '低季波'),
    ('downside_vol_60d', '-', '低下行波'),
    ('sharpe_60d', '', '高夏普'),
    ('max_dd_60d', '-', '低回撤'),
    ('skewness_60d', '-', '负偏规避'),
    ('kurtosis_60d', '-', '低峰度'),
    ('amihud_20d', '-', '高流动性'),
    ('turnover_rate', '-', '低换手'),
    ('log_dollar_vol', '-', '低成交额'),
    ('volume_profile_ratio', '', '放量'),
    ('volume_breakout', '', '量突破'),
    ('volume_trend_20d', '-', '量萎缩'),
    ('turnover_change', '', '换手加速'),
    ('amount_volatility', '-', '额稳定'),
    ('hit_rate_20d', '', '高短胜率'),
    ('hit_rate_60d', '', '高长胜率'),
    ('close_vs_high_20d', '', '近高点'),
    ('mom_vol_adj', '', '纯动量'),
    ('cumret_5d', '', '累积收益'),
    ('rsi_14', '-', 'RSI超卖'),
    ('bollinger_pos', '-', '布林下轨'),
    ('beta_60d', '-', '低Beta'),
    ('max_ret_20d', '-', '无彩票型'),
    ('min_ret_20d', '-', '高最差收益'),
    ('auction_return', '', '隔夜跳空正'),
    ('auction_return', '-', '隔夜跳空负'),
    ('rev_5d', '', '周反转因子'),
    ('rev_overnight', '', '隔夜反转'),
    ('upside_vol_60d', '', '高上行波'),
    ('market_cap_rank', '-', '小市值'),
    ('dollar_volume', '-', '低成交额2'),
]:
    add(f"{sign}rank({f})", desc)

# --- TS on raw returns (different time scales = different economic effects) ---
for w, sign, desc in [
    (3, '-', '3日反转'), (5, '-', '5日反转'), (8, '-', '8日反转'),
    (15, '-', '15日反转'), (5, '', '5日动量'), (20, '', '20日动量'),
    (40, '', '40日动量'), (3, '', '3日惯性'),
]:
    add(f"{sign}rank(ts_delta(close/open-1, {w}))", f"ts_delta({w})={desc}")

for w, sign, desc in [
    (5, '-', '5日均反转'), (10, '-', '10日均反转'),
    (20, '', '20日均动量'), (40, '', '40日均动量'),
]:
    add(f"{sign}rank(ts_mean(close/open-1, {w}))", f"ts_mean({w})={desc}")

for w in [10, 20, 30]:
    add(f"-rank(ts_std(close/open-1, {w}))", f"ts_std({w})=收益稳定")

# --- Volume TS ---
for w in [4, 8, 15]:
    add(f"-rank(ts_delta(volume, {w}))", f"ts_delta_vol({w})=缩量")

# --- Info ratio combos (proven pattern) ---
for r, v, desc in [
    ('ret_20d', 'vol_20d', '月信息比'),
    ('ret_60d', 'vol_60d', '季信息比'),
    ('sharpe_60d', 'vol_20d', '夏普/波'),
    ('ret_20d', 'downside_vol_60d', '动量/下行波'),
]:
    add(f"rank({r}) / (rank({v}) + 0.01)", f"信息比={desc}")

# --- Quality combos ---
for a, b, desc in [
    ('sharpe_60d', 'max_dd_60d', '夏普-回撤'),
    ('ret_20d', 'hit_rate_20d', '动量+胜率'),
    ('hit_rate_60d', 'kurtosis_60d', '高胜率+低峰度'),
    ('ret_60d', 'skewness_60d', '动量-负偏'),
]:
    add(f"rank({a}) * (-rank({b}))", desc)

# --- Volume-confirmed reversal/momentum ---
for a, b, desc in [
    ('rev_5d', 'volume_profile_ratio', '周反转+放量'),
    ('rev_5d', 'volume_breakout', '周反转+量突破'),
    ('ret_20d', 'volume_profile_ratio', '动量+放量'),
    ('ret_20d', 'volume_breakout', '动量+量突破'),
]:
    add(f"rank({a}) * rank({b})", desc)

# --- Minute x Daily cross (low corr by construction) ---
pairs = [
    ('vwap_gap', 'r20', 'ret_20d', 'VWAPx动量'),
    ('vwap_gap', 'sh', 'sharpe_60d', 'VWAPx夏普'),
    ('close_location', 'r20', 'ret_20d', '收盘位x动量'),
    ('close_location', 'sh', 'sharpe_60d', '收盘位x夏普'),
    ('close_location', 'hr', 'hit_rate_60d', '收盘位x胜率'),
    ('price_efficiency', 'sh', 'sharpe_60d', '效率x夏普'),
    ('lower_shadow_pct', 'rv', 'rev_5d', '下影x反转'),
    ('first30min_return', 'r20', 'ret_20d', '开盘x动量'),
]
for mf_tag, df_tag, df_name, desc in pairs:
    for sm in ['', '-']:
        for sd in ['', '-']:
            mf_name = mf_tag if mf_tag not in ['r20','sh','hr','rv'] else df_name
            ae = f"-rank({mf_tag})" if sm == '-' else f"rank({mf_tag})"
            be = f"-rank({df_name})" if sd == '-' else f"rank({df_name})"
            add(f"{ae} * {be}", f"{sm}{mf_tag}x{sd}{df_tag}={desc}")

log(f"Total factors: {len(BATCH)}")

# Main loop
existing, tested = load_existing()
candidates = [(e, d) for e, d in BATCH if e not in tested]
log(f"Existing: {len(existing)} | New to test: {len(candidates)}")

target = 300
passed = 0
for i, (expr, desc) in enumerate(candidates):
    m = evaluate(expr)
    if m is None:
        if i % 20 == 0: log(f"  [{i}] ...")
        continue
    ic = m['ic']

    # Check correlation
    nd = np.array([m['pnl'][i]-m['pnl'][i-1] for i in range(1, len(m['pnl']))])
    max_c = 0.0
    for ef in existing:
        a = nd[-min(len(nd), len(ef['dailies'])):]
        b = ef['dailies'][-len(a):]
        vc = np.isfinite(a) & np.isfinite(b)
        if vc.sum() < 20: continue
        c = abs(float(np.corrcoef(a[vc], b[vc])[0,1]))
        if np.isfinite(c) and c > max_c: max_c = c
    if max_c > 0.7:
        log(f"  CORR SKIP max_c={max_c:.3f} IC={ic:+.04f} | {desc}")
        continue

    eid = save(expr, m)
    existing.append({'id': eid, 'dailies': nd})
    passed += 1
    log(f"  KEPT #{len(existing)}/{target} IC={ic:+.04f} S={m['sh']:.2f} TO={m['to']:.3f} corr={max_c:.2f} | {desc}")

log(f"DONE: +{passed} | {len(existing)}/{target}")
