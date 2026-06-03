"""
Phase 1 FAST — uses DB pnl_json directly, no parse_expression.
Greedy correlation + Top-Sharpe combos inline.
"""
import sys,os,json,time,sqlite3,gc
from datetime import datetime
import numpy as np
from scipy import stats as sp_stats

sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'模型'))
from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, DB_PATH

OUT='D:/yyb/backtest_platform/experiment_results/phase1_fast.json'
os.makedirs(os.path.dirname(OUT),exist_ok=True)

t_start=datetime.now()
print('=== PHASE1 FAST ' + t_start.strftime('%H:%M:%S') + ' ===')

# Load PnL from DB
c=sqlite3.connect(DB_PATH)
rows=c.execute("""SELECT id, expression, pnl_json, metrics_json FROM alpha_history
    WHERE json_extract(metrics_json,'$.is_pearson_ic')>0.01
      AND (type IS NULL OR type!='superalpha')
      AND pnl_json IS NOT NULL AND length(pnl_json)>100
    ORDER BY json_extract(metrics_json,'$.is_sharpe') DESC LIMIT 80""").fetchall()
c.close()

factors=[]; pnls_db=[]
for r in rows:
    pnl=json.loads(r[2])
    if isinstance(pnl,list) and len(pnl)>100:
        m=json.loads(r[3])
        factors.append({'id':r[0],'expr':r[1],'is_sharpe':m.get('is_sharpe',0),'is_ic':m.get('is_pearson_ic',0)})
        pnls_db.append(np.array(pnl,dtype=np.float64))
print(f'Loaded {len(factors)} factors with DB PnL')

# Greedy selection
top=min(60,len(factors))
def greedy(max_corr,top_n=10):
    sel=[]; rem=list(range(top))
    rem.sort(key=lambda i:-factors[i]['is_sharpe'])
    while rem and len(sel)<top_n:
        cand=rem.pop(0)
        too_close=False
        for s in sel:
            v1,v2=pnls_db[cand],pnls_db[s]
            vl=~np.isnan(v1)&~np.isnan(v2)
            if vl.sum()<30: continue
            if abs(sp_stats.spearmanr(v1[vl],v2[vl])[0])>max_corr: too_close=True; break
        if not too_close: sel.append(cand)
    return sel

# Now compute combos inline
with flask_app.app_context():
    p,e,f=get_engine()
    dk=sorted(p.date_to_idx.keys())
    t0_os=None
    for d in dk:
        if d>='2023-01-01': t0_os=p.date_to_idx[d]; break
    t1_os=min(p.date_to_idx['2023-12-29']+1,p.n_dates)
    lbl=p.fields['Label'][t0_os:t1_os]; univ=p.universe_mask[t0_os:t1_os]
    nd,ns=lbl.shape

    def compute(exprs):
        cb=np.zeros((nd,ns),dtype=np.float32); ws=np.zeros((nd,ns),dtype=np.float32); vc=0
        for expr in exprs:
            try:
                fa=parse_expression(expr,p,f); ft=np.asarray(fa[t0_os:t1_os],dtype=np.float32); del fa
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
        # MktCap neutral
        try:
            adjf=np.clip(np.where(np.isnan(p.fields.get('I_D_ADJFACTOR',np.ones_like(cb[0]))),1.0,
                          p.fields.get('I_D_ADJFACTOR',np.ones_like(cb[0]))),0.01,100)
            m=p.fields['I_D_CLOSE_ORI']*adjf*p.fields.get('I_D_TOTAL_SHARES',p.fields.get('I_D_SHARE_LIQA',np.ones_like(cb[0])))
            mt=np.asarray(m[t0_os:t1_os],dtype=np.float64)
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

    # 1. Greedy
    print('\n--- GREEDY ---')
    for th in [0.3,0.5,0.7]:
        sel=greedy(th,top_n=10)
        if len(sel)<3: continue
        exprs=[factors[i]['expr'] for i in sel]
        n=len(exprs)
        gcount={}
        for i in sel:
            e=factors[i]['expr'].lower()
            if any(t in e for t in ['rev','-rank(returns','-returns','-ret_']): g='rev'
            elif any(t in e for t in ['mom','trend','ret_20','ret_60']): g='mom'
            elif any(t in e for t in['micro','intraday','vwap','shadow','wick']): g='micro'
            elif any(t in e for t in['volatil','downside','std','drawdown','beta']): g='vol'
            elif any(t in e for t in['turnover','volume','liquidity','amihud']): g='liq'
            else: g='other'
            gcount[g]=gcount.get(g,0)+1
        print('  corr<{}: {} factors, groups={}'.format(th,n,gcount))
        t0_=time.time()
        m=compute(exprs)
        t_=time.time()-t0_
        if m:
            entry={'exp':'greedy_cr'+str(int(th*10)),'n':n,'sharpe':m['sharpe'],'ic':m['pearson_ic'],'icir':m['icir'],'fitness':m['fitness'],'groups':gcount,'time_s':int(t_)}
            results.append(entry)
            s=m['sharpe']; ic=m['pearson_ic']
            print('    S={:.2f} IC={:.4f} ({:.0f}s)'.format(s,ic,t_))
        gc.collect()

    # 2. Top-Sharpe elite
    print('\n--- TOP-SHARPE ---')
    for n in [3,5,8]:
        exprs=[f['expr'] for f in factors[:n]]
        t0_=time.time()
        m=compute(exprs)
        t_=time.time()-t0_
        if m:
            s=m['sharpe']; ic=m['pearson_ic']
            entry={'exp':'topSharpe_N'+str(n),'n':n,'sharpe':s,'ic':ic,'icir':m['icir'],'fitness':m['fitness'],'time_s':int(t_)}
            results.append(entry)
            print('  N={}: S={:.2f} IC={:.4f} ({:.0f}s)'.format(n,s,ic,t_))
        gc.collect()

    # 3. Rev+Mom
    print('\n--- REV+MOM ---')
    rev=[f for f in factors if any(t in f['expr'].lower() for t in ['rev','-rank(returns','-ret_','close_position'])][:8]
    mom=[f for f in factors if any(t in f['expr'].lower() for t in ['mom','trend','ret_20','ret_60','ret_120','cumret'])][:8]
    print('  Rev: {}, Mom: {}'.format(len(rev),len(mom)))
    for rn,mn in [(3,2),(5,3),(5,5)]:
        exprs=[f['expr'] for f in rev[:rn]+mom[:mn]]
        t0_=time.time()
        m=compute(exprs)
        t_=time.time()-t0_
        if m:
            s=m['sharpe']; ic=m['pearson_ic']
            entry={'exp':'rev'+str(rn)+'+mom'+str(mn),'n':len(exprs),'sharpe':s,'ic':ic,'icir':m['icir'],'fitness':m['fitness'],'time_s':int(t_)}
            results.append(entry)
            print('  rev{}+mom{}: S={:.2f} IC={:.4f} ({:.0f}s)'.format(rn,mn,s,ic,t_))
        gc.collect()

    # 4. Cross-style best-of-each
    print('\n--- CROSS-STYLE ---')
    groups={'rev':[],'mom':[],'micro':[],'vol':[],'liq':[]}
    for f in factors:
        e=f['expr'].lower()
        if any(t in e for t in['rev','-rank(returns','-ret_','close_position']): groups['rev'].append(f)
        elif any(t in e for t in['mom','trend','ret_20','ret_60']): groups['mom'].append(f)
        elif any(t in e for t in['micro','intraday','vwap','shadow','wick']): groups['micro'].append(f)
        elif any(t in e for t in['volatil','downside','std']): groups['vol'].append(f)
        elif any(t in e for t in['turnover','volume','liquidity']): groups['liq'].append(f)
    sel=[]
    for g in ['rev','mom','micro','vol','liq']:
        if groups[g]: sel.append(groups[g][0])
    exprs=[f['expr'] for f in sel]
    t0_=time.time()
    m=compute(exprs)
    t_=time.time()-t0_
    if m:
        s=m['sharpe']; ic=m['pearson_ic']
        entry={'exp':'cross_1per','n':len(exprs),'sharpe':s,'ic':ic,'icir':m['icir'],'fitness':m['fitness'],'time_s':int(t_)}
        results.append(entry)
        print('  cross 1-per-group: S={:.2f} IC={:.4f} ({:.0f}s)'.format(s,ic,t_))

# Save
with open(OUT,'w') as f: json.dump(results,f,indent=2,default=str)

elapsed=(datetime.now()-t_start).total_seconds()
print('\n=== PHASE1 DONE: {} results in {:.0f}s ==='.format(len(results),elapsed))
for r in sorted(results,key=lambda x:-x['sharpe']):
    print('  {:20s} N={:3d} S={:.2f} IC={:.4f} ICIR={:.2f}'.format(r['exp'],r['n'],r['sharpe'],r['ic'],r['icir']))
print('Saved: '+OUT)
