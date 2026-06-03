"""Generate and backtest clean factors using only daily fields (close/volume/returns).
No minute data, no FactorComputer. Each factor has a distinct economic rationale."""
import sys, os, json, math, time, sqlite3, uuid, datetime
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
sys.path.insert(0, 'D:/yyb/模型')
import numpy as np
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression

DB_PATH = os.path.join(script_dir, "backtest.db")

# ---- compute_metrics (pure long-only) ----
def compute_metrics(ft, lt, ut, result, top_pct=0.1):
    direction=1; n_dates=ft.shape[0]
    daily_excess=[]; daily_top_set=[]
    for t in range(n_dates):
        f=ft[t]; l=lt[t]; v=ut[t]&(~np.isnan(f))&(~np.isnan(l))
        if v.sum()<100: daily_excess.append(None); daily_top_set.append(set()); continue
        fv,lv=f[v],l[v]; n_top=max(1,int(v.sum()*top_pct))
        order=np.argsort(fv); top_idx=order[-n_top:] if direction>0 else order[:n_top]
        daily_excess.append(float(np.nanmean(lv[top_idx]))-float(np.nanmean(lv)))
        daily_top_set.append(set(np.where(v)[0][top_idx]))
    ea=np.array([x for x in daily_excess if x is not None])
    em,es=float(np.mean(ea)),float(np.std(ea)); ae=em*250
    sh=ae/(es*np.sqrt(250)+1e-10)
    tos=[]
    for t in range(1,len(daily_top_set)):
        p,c=daily_top_set[t-1],daily_top_set[t]
        if len(p)>0 and len(c)>0: tos.append(1.0-len(p&c)/max(len(p),len(c)))
    at=float(np.mean(tos)) if tos else 0.0
    fit=sh*np.sqrt(abs(ae)/max(at,0.125)) if ae!=0 else 0.0
    cum=0.0;peak=0.0;dd=0.0;cp=[]
    for r in daily_excess:
        if r is not None: cum+=r
        if cum>peak: peak=cum
        dd=max(dd,peak-cum)
        cp.append(float(cum*100))
    mg=float(em/(np.mean(np.abs(ea))+1e-10)*10000)
    neg=ea[ea<0]; ds=float(np.std(neg)) if len(neg)>0 else es
    so=ae/(ds*np.sqrt(250)+1e-10); wr=float((ea>0).mean())
    ics=result.get('ic_series',np.array([]))
    icd=[round(float(x),4) if not np.isnan(x) else None for x in ics[-60:]]
    pd=[None if x is None or math.isnan(float(x)) else float(x) for x in cp]
    def sr(v,n):
        try: vv=float(v); return round(vv,n) if not math.isnan(vv) and not math.isinf(vv) else None
        except: return None
    return {'pearson_ic':sr(result.get('mean_pearson_ic',0),4),'rank_ic':sr(result.get('mean_rank_ic',0),4),
            'icir':sr(result.get('icir',0),3),'ic_positive_ratio':sr(result.get('ic_positive_ratio',0),3),
            'annual_excess':sr(ae,4),'sharpe':sr(sh,3),'fitness':sr(fit,3),'returns':sr(ae,4),
            'max_drawdown':sr(dd,4),'turnover':sr(at,4),'margin_bps':sr(mg,1),'sortino':sr(so,3),
            'win_rate':sr(wr,3),'n_days':int(result.get('n_eval_days',0)),'ic_series':icd,'pnl_series':pd}

def save(expr,metrics):
    name=expr[:40]+('...' if len(expr)>40 else '')
    eid=str(uuid.uuid4()); ts=datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    mj=json.dumps({k:v for k,v in metrics.items() if k not in('ic_series','pnl_series')})
    pj=json.dumps(metrics.get('pnl_series',[])); ij=json.dumps(metrics.get('ic_series',[]))
    db=sqlite3.connect(DB_PATH)
    db.execute('INSERT INTO alpha_history(id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json) VALUES(?,?,?,?,?,?,?,?)',
               (eid,name,expr,ts,'alpha',mj,pj,ij))
    db.commit();db.close()

# ---- 50 factors with distinct economic rationales ----
FACTORS = [
    # Momentum variants
    ("-rank(ts_delta(close,5))", "market_cap", "5日动量：短期趋势追随"),
    ("-rank(ts_delta(close,10))", "market_cap", "10日动量：双周趋势"),
    ("-rank(ts_delta(close,3))", "market_cap", "3日动量：超短期趋势"),
    ("-rank(ts_delta(close,30))", "market_cap", "30日动量：月度趋势"),
    ("-rank(ts_delta(close,90))", "market_cap", "90日动量：季度趋势"),
    ("-rank(ts_delta(close,120))", "market_cap", "120日动量：半年趋势"),
    ("-rank(ts_delta(close,250))", "market_cap", "250日动量：年度趋势"),

    # Reversal variants
    ("rank(ts_delta(close,1))", "market_cap", "1日反转：日间反转异象"),
    ("rank(ts_delta(close,2))", "market_cap", "2日反转：短期反转"),
    ("rank(close/open-1)", "market_cap", "日内反转：盘中涨幅预示次日反转"),
    ("-rank(ts_delta(close,1))", "market_cap", "1日动量（非反转）：短期延续"),

    # Multi-window momentum averages (stable trend measure)
    ("-rank(ts_delta(close,5)+ts_delta(close,20)+ts_delta(close,60))", "market_cap", "多周期动量加和：趋势共振"),
    ("-rank(ts_delta(close,5)*0.5+ts_delta(close,20)*0.3+ts_delta(close,60)*0.2)", "market_cap", "多周期动量加权：近端优先"),

    # Volatility-based
    ("-rank(ts_std(close/open-1,5))", "market_cap", "5日波动率反转：低波异象（低波动=高收益）"),
    ("-rank(ts_std(close/open-1,10))", "market_cap", "10日波动率反转：双周低波"),
    ("-rank(ts_std(close/open-1,30))", "market_cap", "30日波动率反转：月度低波"),
    ("rank(ts_std(close/open-1,5)/ts_std(close/open-1,60))", "market_cap", "波动率爆发：短期/长期波动比"),

    # Volume-based
    ("-rank(ts_mean(volume,5)/ts_mean(volume,60))", "market_cap", "量比反转：放量后反转（量比<1做多）"),
    ("rank(ts_mean(volume,5)/ts_mean(volume,60))", "market_cap", "量比动量：放量伴随趋势"),
    ("-rank(ts_delta(volume,5))", "market_cap", "量增反转：成交量突增预示反转"),
    ("rank(ts_std(volume,5)/ts_mean(volume,20))", "market_cap", "量波动率：成交量不稳定=风险"),

    # Price-volume interaction
    ("-rank(ts_delta(close,5)/ts_std(close/open-1,20))", "market_cap", "夏普动量：风险调整后动量"),
    ("-rank(ts_delta(close,10)/ts_std(close/open-1,60))", "market_cap", "长期夏普动量"),
    ("-rank(ts_delta(close,20)*(ts_mean(volume,5)/ts_mean(volume,60)))", "market_cap", "量价共振：量价同时放大"),

    # Mean reversion (close vs moving average)
    ("rank(close/ts_mean(close,5)-1)", "market_cap", "5日均线偏离反转：超买回落"),
    ("rank(close/ts_mean(close,10)-1)", "market_cap", "10日均线偏离反转"),
    ("rank(close/ts_mean(close,20)-1)", "market_cap", "20日均线偏离反转"),
    ("rank(close/ts_mean(close,60)-1)", "market_cap", "60日均线偏离反转"),
    ("-rank(close/ts_mean(close,5)-1)", "market_cap", "5日均线偏离动量：突破后延续"),

    # Signed power (non-linear, amplifies strong signals)
    ("-rank(signed_power(ts_delta(close,5),2))", "market_cap", "动量平方：放大强动量信号"),
    ("-rank(signed_power(ts_delta(close,20),1.5))", "market_cap", "动量1.5次方：温和放大"),
    ("rank(signed_power(close/ts_mean(close,20)-1,2))", "market_cap", "偏离平方反转：放大极端偏离"),

    # Spread / gap
    ("-rank(high/low-1)", "market_cap", "振幅动量：高振幅日伴随趋势"),
    ("rank(high/low-1)", "market_cap", "振幅反转：高振幅后反转"),

    # Cross-sectional rank combos
    ("-rank(ts_delta(close,5))-rank(ts_mean(volume,5)/ts_mean(volume,60))", "market_cap", "动量+量比组合"),
    ("-rank(ts_delta(close,10))-rank(ts_std(close/open-1,10))", "market_cap", "动量+低波组合"),
    ("-rank(ts_delta(close,20))-rank(close/ts_mean(close,20)-1)", "market_cap", "动量+趋势组合"),

    # Returns-based (using returns = close/open-1 daily returns)
    ("-rank(ts_sum(close/open-1,5))", "market_cap", "5日累积收益动量"),
    ("-rank(ts_sum(close/open-1,10))", "market_cap", "10日累积收益动量"),
    ("rank(ts_sum(close/open-1,5))", "market_cap", "5日累积收益反转"),

    # Volatility trend
    ("-rank(ts_mean(close/open-1,5)/ts_std(close/open-1,60))", "market_cap", "收益/波动效率比：高Sharpe=继续走高"),

    # Price path dependent
    ("-rank(ts_max(close,20)/close-1)", "market_cap", "距20日高点距离：接近高点=强势"),
    ("rank(ts_max(close,60)/close-1)", "market_cap", "距60日高点距离反转：远离高点=超跌"),
    ("-rank(1-close/ts_max(close,20))", "market_cap", "新高接近度动量"),
    ("rank(ts_min(close,20)/close-1)", "market_cap", "距20日低点距离：接近低点=弱势"),
    ("-rank(ts_min(close,60)/close-1)", "market_cap", "距60日低点距离反转"),

    # Decay linear (recent returns weighted more)
    ("-rank(ts_decay_linear(close/open-1,5))", "market_cap", "5日衰减动量：近端权重更高"),
    ("-rank(ts_decay_linear(close/open-1,10))", "market_cap", "10日衰减动量"),
    ("rank(ts_decay_linear(close/open-1,20))", "market_cap", "20日衰减反转"),

    # Rank-based stability
    ("-rank(ts_rank(close,60))", "market_cap", "60日rank动量：截面排名稳定性"),
]

print(f"Total factors: {len(FACTORS)}")

print("Loading pipeline...", flush=True)
pipeline = DataPipeline()
engine = BacktestEngine(pipeline)
print("Ready.", flush=True)

t0_d = pipeline.date_to_idx['2020-01-02']
t1_d = min(pipeline.date_to_idx['2023-12-29']+1, pipeline.n_dates)
label_train = pipeline.fields['Label'][t0_d:t1_d]
univ_train = pipeline.universe_mask[t0_d:t1_d]

total = 0; good = 0; good02 = 0
for expr, neut, rationale in FACTORS:
    # Skip if already done
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.execute("SELECT COUNT(*) FROM alpha_history WHERE type='alpha' AND expression=?", (expr,))
    if c.fetchone()[0] > 0:
        db.close()
        print(f"[SKIP] {expr[:50]}")
        continue
    db.close()

    print(f"[{len(FACTORS)-total} left] {expr[:55]}... ", end="", flush=True)
    t0 = time.time()
    try:
        factor = parse_expression(expr, pipeline, None)
        ft = factor[t0_d:t1_d]

        # Market cap neutralization
        if neut == 'market_cap':
            adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                     pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(ft[0]))), 0.01, 100)
            mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES', pipeline.fields.get('I_D_SHARE_LIQA', np.ones_like(ft[0])))
            mcap_train = mcap[t0_d:t1_d]
            for t in range(ft.shape[0]):
                valid = ~np.isnan(ft[t]) & ~np.isnan(mcap_train[t])
                if valid.sum()<100: continue
                log_mcap = np.log(np.maximum(mcap_train[t,valid],1))
                gids = np.floor(np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0,101,10)))/10).astype(int)
                fv = ft[t,valid].copy()
                for g in np.unique(gids):
                    gm = gids==g
                    if gm.sum()>=10: fv[gm] -= np.nanmean(fv[gm])
                ft[t,valid] = fv

        result = engine.full_evaluation(ft, univ_train, label=label_train)
        metrics = compute_metrics(ft, label_train, univ_train, result)
        save(expr, metrics)

        ic = metrics.get('pearson_ic') or 0
        ex = metrics.get('annual_excess') or 0
        ok = "OK" if abs(ic)>=0.01 else "LOW"
        print(f"IC={ic:.4f} Ex={ex:.4f} [{ok}] ({time.time()-t0:.1f}s) [{rationale[:40]}]", flush=True)
        total += 1
        if abs(ic)>=0.01: good += 1
        if abs(ic)>=0.02: good02 += 1

    except Exception as e:
        print(f"FAIL: {e}", flush=True)

# Final report
db = sqlite3.connect(DB_PATH)
c = db.cursor()
c.execute("SELECT COUNT(*) FROM alpha_history WHERE type='alpha'")
all_alpha = c.fetchone()[0]
c.execute('SELECT metrics_json FROM alpha_history WHERE type="alpha"')
all_good = sum(1 for (mj,) in c.fetchall() if abs((json.loads(mj or '{}').get('pearson_ic'))or 0)>=0.01)
c.execute('SELECT SUM(CASE WHEN abs(json_extract(metrics_json,"$.pearson_ic"))>=0.02 THEN 1 ELSE 0 END) FROM alpha_history WHERE type="alpha"')
all_good02 = c.fetchone()[0] or 0
db.close()

print(f"\n=== DONE ===")
print(f"This run: {total} completed, {good} |IC|>=0.01, {good02} |IC|>=0.02")
print(f"Total DB: {all_alpha} alpha, {all_good} |IC|>=0.01, {all_good02} |IC|>=0.02")
