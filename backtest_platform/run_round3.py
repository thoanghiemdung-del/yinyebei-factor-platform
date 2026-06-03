"""Run round3 factors."""
import sys, os, json, math, time, sqlite3, uuid, datetime
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir); sys.path.insert(0, 'D:/yyb/模型')
import numpy as np
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression
from round3_factors import ROUND3

DB_PATH = os.path.join(script_dir, "backtest.db")

def compute_metrics(ft, lt, ut, result, top_pct=0.1):
    direction=1; n_dates=ft.shape[0]; daily_excess=[]; daily_top_set=[]
    for t in range(n_dates):
        f=ft[t]; l=lt[t]; v=ut[t]&(~np.isnan(f))&(~np.isnan(l))
        if v.sum()<100: daily_excess.append(None); daily_top_set.append(set()); continue
        fv,lv=f[v],l[v]; n_top=max(1,int(v.sum()*top_pct))
        order=np.argsort(fv); top_idx=order[-n_top:] if direction>0 else order[:n_top]
        daily_excess.append(float(np.nanmean(lv[top_idx]))-float(np.nanmean(lv)))
        daily_top_set.append(set(np.where(v)[0][top_idx]))
    ea=np.array([x for x in daily_excess if x is not None]); em,es=float(np.mean(ea)),float(np.std(ea)); ae=em*250
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
        dd=max(dd,peak-cum); cp.append(float(cum*100))
    mg=float(em/(np.mean(np.abs(ea))+1e-10)*10000)
    neg=ea[ea<0]; ds=float(np.std(neg)) if len(neg)>0 else es
    so=ae/(ds*np.sqrt(250)+1e-10); wr=float((ea>0).mean())
    ics=result.get('ic_series',np.array([])); icd=[round(float(x),4) if not np.isnan(x) else None for x in ics[-60:]]
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

pipeline = DataPipeline()
engine = BacktestEngine(pipeline)
t0_d = pipeline.date_to_idx['2020-01-02']
t1_d = min(pipeline.date_to_idx['2023-12-29']+1, pipeline.n_dates)
label_train = pipeline.fields['Label'][t0_d:t1_d]
univ_train = pipeline.universe_mask[t0_d:t1_d]
print(f"Round 3: {len(ROUND3)} factors. Ready.")

total=0; good=0; skipped=0; failed=0
for expr, neut, rationale in ROUND3:
    db=sqlite3.connect(DB_PATH); c=db.cursor()
    c.execute("SELECT COUNT(*) FROM alpha_history WHERE expression=?",(expr,))
    if c.fetchone()[0]>0: db.close(); skipped+=1; continue
    db.close()

    print(f"[{len(ROUND3)-total-skipped-failed} left] {expr[:55]}... ", end="", flush=True)
    t0=time.time()
    try:
        factor=parse_expression(expr, pipeline, None)
        ft=factor[t0_d:t1_d]
        if neut=='market_cap':
            adjf=np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']),1.0,
                                   pipeline.fields.get('I_D_ADJFACTOR',np.ones_like(ft[0]))),0.01,100)
            mcap=pipeline.fields['I_D_CLOSE_ORI']*adjf*pipeline.fields.get('I_D_TOTAL_SHARES',pipeline.fields.get('I_D_SHARE_LIQA',np.ones_like(ft[0])))
            mcap_train=mcap[t0_d:t1_d]
            for t in range(ft.shape[0]):
                valid=~np.isnan(ft[t])&~np.isnan(mcap_train[t])
                if valid.sum()<100: continue
                log_mcap=np.log(np.maximum(mcap_train[t,valid],1))
                gids=np.floor(np.digitize(log_mcap,np.percentile(log_mcap,np.arange(0,101,10)))/10).astype(int)
                fv=ft[t,valid].copy()
                for g in np.unique(gids):
                    gm=gids==g
                    if gm.sum()>=10: fv[gm]-=np.nanmean(fv[gm])
                ft[t,valid]=fv
        result=engine.full_evaluation(ft, univ_train, label=label_train)
        metrics=compute_metrics(ft, label_train, univ_train, result)
        save(expr, metrics)
        ic=metrics.get('pearson_ic')or 0; ok="OK" if abs(ic)>=0.01 else "LOW"
        print(f"IC={ic:.4f} [{ok}] ({time.time()-t0:.1f}s)", flush=True)
        total+=1
        if abs(ic)>=0.01: good+=1
    except Exception as e:
        print(f"FAIL ({time.time()-t0:.1f}s)", flush=True); failed+=1

db=sqlite3.connect(DB_PATH); c=db.cursor()
c.execute("SELECT COUNT(*) FROM alpha_history WHERE type='alpha'"); ta=c.fetchone()[0]
c.execute('SELECT metrics_json FROM alpha_history WHERE type="alpha"')
tg=sum(1 for (mj,) in c.fetchall() if abs((json.loads(mj or '{}').get('pearson_ic'))or 0)>=0.01)
c.execute('SELECT SUM(CASE WHEN abs(json_extract(metrics_json,"$.pearson_ic"))>=0.02 THEN 1 ELSE 0 END) FROM alpha_history WHERE type="alpha"')
tg02=c.fetchone()[0] or 0
db.close()
print(f"\nDone. New: {total} ({good} OK), skipped: {skipped}, failed: {failed}")
print(f"Total: {ta} alpha, {tg} |IC|>=0.01, {tg02} |IC|>=0.02")
