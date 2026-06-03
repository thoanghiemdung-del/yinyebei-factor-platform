"""
Phase 1: Greedy correlation + LGB — inline, no Flask, single pipeline.
"""
import sys,os,json,time,sqlite3,gc
from datetime import datetime
import numpy as np
from scipy import stats as sp_stats

sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'模型'))
from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, _add_to_history, DB_PATH

OUT='D:/yyb/backtest_platform/experiment_results/phase1.json'
os.makedirs(os.path.dirname(OUT),exist_ok=True)

print(f"=== PHASE 1: GREEDY + LGB — {datetime.now().strftime('%H:%M:%S')} ===")

with flask_app.app_context():
    p,e,f=get_engine()
    dk=sorted(p.date_to_idx.keys())
    t0_oos=None
    for d in dk:
        if d>='2023-01-01': t0_oos=p.date_to_idx[d]; break
    t1_oos=min(p.date_to_idx['2023-12-29']+1,p.n_dates)
    lbl=p.fields['Label'][t0_oos:t1_oos]; univ=p.universe_mask[t0_oos:t1_oos]
    nd,ns=lbl.shape

    # Get factors
    c=sqlite3.connect(DB_PATH)
    rows=c.execute("""SELECT id,expression,metrics_json FROM alpha_history
        WHERE json_extract(metrics_json,'$.is_pearson_ic')>0.01 AND (type IS NULL OR type!='superalpha')
        ORDER BY json_extract(metrics_json,'$.is_sharpe') DESC LIMIT 80""").fetchall()
    c.close()
    factors=[{'id':r[0],'expr':r[1],'is_sharpe':json.loads(r[2]).get('is_sharpe',0)} for r in rows]
    print(f'Loaded {len(factors)} factors')

    # Compute OOS PnL for top 60
    print('Computing PnL correlations...')
    top60=factors[:60]
    pnls=[]
    for i,fct in enumerate(top60):
        try:
            fa=parse_expression(fct['expr'],p,f)
            ft=np.asarray(fa[t0_oos:t1_oos],dtype=np.float32)
            pnl=np.nanmean(ft,axis=1); del fa,ft
            pnls.append(pnl)
        except:
            pnls.append(None)
        if (i+1)%20==0: print(f'  {i+1}/60 PnLs'); gc.collect()

    # Greedy selection
    def greedy(max_corr,top_n=10):
        sel=[]; rem=list(range(len(top60)))
        rem.sort(key=lambda i:-top60[i]['is_sharpe'])
        while rem and len(sel)<top_n:
            cand=rem.pop(0)
            if pnls[cand] is None: continue
            too_close=False
            for s in sel:
                v1,v2=pnls[cand],pnls[s]
                vl=~np.isnan(v1)&~np.isnan(v2)
                if vl.sum()<30: continue
                if abs(sp_stats.spearmanr(v1[vl],v2[vl])[0])>max_corr: too_close=True; break
            if not too_close: sel.append(cand)
        return sel

    def compute(exprs,method='equal'):
        cb=np.zeros((nd,ns),dtype=np.float32); ws=np.zeros((nd,ns),dtype=np.float32); vc=0
        for expr in exprs:
            try:
                fa=parse_expression(expr,p,f); ft=np.asarray(fa[t0_oos:t1_oos],dtype=np.float32); del fa
                fm=np.nanmean(ft,axis=1,keepdims=True); fs=np.nanstd(ft,axis=1,keepdims=True)+1e-10
                fz=(ft-fm)/fs; v=np.isfinite(fz)
                if not np.any(v): del ft,fz,v,fm,fs; continue
                w=1.0/len(exprs)
                cb[v]+=w*fz[v]; ws[v]+=w; vc+=1
                del ft,fz,v,fm,fs
            except: continue
        vw=np.isfinite(ws)&(np.abs(ws)>1e-12)
        if vc<2 or not np.any(vw): return None
        cb[vw]/=ws[vw]; cb[~vw]=np.nan; del ws

        # MktCap neutralize
        try:
            adjf=np.clip(np.where(np.isnan(p.fields.get('I_D_ADJFACTOR',np.ones_like(cb[0]))),1.0,
                          p.fields.get('I_D_ADJFACTOR',np.ones_like(cb[0]))),0.01,100)
            m=p.fields['I_D_CLOSE_ORI']*adjf*p.fields.get('I_D_TOTAL_SHARES',
                          p.fields.get('I_D_SHARE_LIQA',np.ones_like(cb[0])))
            mt=np.asarray(m[t0_oos:t1_oos],dtype=np.float64)
            for tt in range(cb.shape[0]):
                vl=~np.isnan(cb[tt])&~np.isnan(mt[tt])
                if vl.sum()<100: continue
                lmc=np.log(np.maximum(mt[tt][vl],1))
                gi=np.floor(np.digitize(lmc,np.percentile(lmc,np.arange(0,101,10)))/10).astype(int)
                cv=cb[tt][vl].copy()
                for g in np.unique(gi):
                    gm=gi==g
                    if gm.sum()>=10: cv[gm]-=np.nanmean(cv[gm])
                cb[tt][vl]=cv
        except: pass

        cr=e.full_evaluation(cb,univ,label=lbl)
        cm=_compute_metrics_from_result(cb,lbl,univ,cr)
        del cb; gc.collect()
        return {k:v for k,v in cm.items() if k not in ('_factor_array','_direction')}

    results=[]

    # 1. GREEDY with different thresholds
    print('\n--- GREEDY CORRELATION ---')
    for th in [0.3,0.5,0.7]:
        sel=greedy(th,top_n=10)
        if len(sel)<3: continue
        exprs=[top60[i]['expr'] for i in sel]
        n=len(exprs)
        print(f'  corr<{th}: {n} factors')
        t0_=time.time()
        m=compute(exprs,'equal')
        t_=time.time()-t0_
        if m:
            entry={'exp':'greedy','corr_th':th,'n':n,'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir'],'fitness':m['fitness']}
            results.append(entry)
            s=m["sharpe"]; ic=m["pearson_ic"]
            print(f"    S={s:.2f} IC={ic:.4f} ({t_:.0f}s)")
            print(f'    S={s:.2f} IC={ic:.4f} ({t_:.0f}s)')
        gc.collect()

    # 2. TOP-SHARPE elite
    print('\n--- TOP-SHARPE ELITE ---')
    ts=sorted(factors,key=lambda x:-x['is_sharpe'])[:15]
    for n in [3,5,8]:
        exprs=[r['expr'] for r in ts[:n]]
        t0_=time.time()
        m=compute(exprs,'equal')
        t_=time.time()-t0_
        if m:
            entry={'exp':'topSharpe','n':n,'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir'],'fitness':m['fitness']}
            results.append(entry)
            s=m["sharpe"]; ic=m["pearson_ic"]
            print(f"  N={n}: S={s:.2f} IC={ic:.4f} ({t_:.0f}s)")
        gc.collect()

    # 3. Rev+Mom hybrids
    print('\n--- REV+MOM HYBRIDS ---')
    _GR=[('reversal',['reversal','rev_','-rank(returns','-returns','-ret_','close_position','close_location']),
         ('momentum',['momentum','mom_','trend','breakout','ret_20','ret_60','ret_120','cumret'])]
    def gk(expr):
        for key,terms in _GR:
            if any(t in expr.lower() for t in terms): return key
        return 'other'
    rev=[f for f in factors if gk(f['expr'])=='reversal'][:8]
    mom=[f for f in factors if gk(f['expr'])=='momentum'][:8]
    print(f'  Rev: {len(rev)}, Mom: {len(mom)}')
    for rn,mn in [(3,2),(5,3),(5,5)]:
        exprs=[r['expr'] for r in rev[:rn]+mom[:mn]]
        t0_=time.time()
        m=compute(exprs,'equal')
        t_=time.time()-t0_
        if m:
            entry={'exp':f'rev{rn}+mom{mn}','n':len(exprs),'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir'],'fitness':m['fitness']}
            results.append(entry)
            s=m["sharpe"]; ic=m["pearson_ic"]
            print(f"  rev{rn}+mom{mn}: S={s:.2f} IC={ic:.4f} ({t_:.0f}s)")
        gc.collect()

    # Save
    with open(OUT,'w') as f: json.dump(results,f,indent=2)

    print('\n=== PHASE 1 COMPLETE: ' + str(len(results)) + ' results ===')
    for r in sorted(results,key=lambda x:-x['sharpe']):
        exp = r.get('exp','?'); n = r.get('n',0); s = r['sharpe']; ic = r['ic']; icir = r['icir']
        print('  {:20s} N={:3d} S={:.2f} IC={:.4f} ICIR={:.2f}'.format(exp, n, s, ic, icir))

print(f'\nSaved: {OUT}')
print('End: ' + datetime.now().strftime('%H:%M:%S'))
