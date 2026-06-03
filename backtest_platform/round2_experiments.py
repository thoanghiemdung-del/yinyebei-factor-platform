"""
Round 2 — fill gaps, add LGB, nesting, deeper analysis.
Longer timeouts, smarter retries.
"""
import requests, json, time, os, sys
from datetime import datetime

BASE = 'http://127.0.0.1:5000'
OUTPUT_DIR = r'D:\yyb\backtest_platform\experiment_results'
os.makedirs(OUTPUT_DIR, exist_ok=True)
TIMEOUT = 300

session = requests.Session()
r = session.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'}, allow_redirects=True)
assert r.status_code in (200, 302), f'Login: {r.status_code}'

r = session.get(f'{BASE}/api/alpha/history', params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_pearson_ic', 'order': 'desc'})
records = [r for r in r.json().get('records', []) if r.get('type') != 'superalpha']
print(f'{len(records)} factors')

_GROUPS = [
    ('momentum', ['momentum','mom_','trend','breakout','ret_20','ret_60','ret_120','cumret','ts_delta','slope','accel','relative_strength','new_high','ma_gap','ema','macd','price_strength']),
    ('reversal', ['reversal','rev_','mean_reversion','overreaction','gap','overnight','rsi','stoch','-rank(returns','-returns','-ret_','close_position','close_location','short_term_reversal']),
    ('volatility', ['volatility','realized_vol','downside','std','atr','range','high_low','skew','kurt','drawdown','max_dd','max_drawdown','beta','risk','entropy','dispersion','boll']),
    ('liquidity', ['turnover','volume','amount','dollar','liquidity','amihud','adv','money_flow','flow','trade_count','volume_profile']),
    ('microstructure', ['minute','intraday','auction','vwap','open_','close_','high_','low_','shadow','wick','body','kline','bar_','smart_money','imbalance','impact']),
    ('size', ['market_cap','mcap','float_cap','size','ln_cap','log_cap']),
    ('fundamental', ['roe','roa','profit','margin','debt','asset','liability','book','eps','sales','revenue','cash','earning','earnings','growth','pe','pb','bp','value']),
]

def gk(expr):
    el = expr.lower()
    scores = [(len(set(t for t in terms if t in el)), key) for key, terms in _GROUPS]
    scores = [(s,k) for s,k in scores if s>0]
    if not scores: return 'unknown'
    scores.sort(reverse=True)
    if len(scores)>1 and scores[1][0]>=max(1,scores[0][0]-1): return 'mixed'
    return scores[0][1]

groups = {}
for rec in records:
    g = gk(rec['expression'])
    if g not in groups: groups[g] = []
    groups[g].append(rec)

print(f'Groups: {dict((k,len(v)) for k,v in sorted(groups.items(), key=lambda x:-len(x[1])))}')

pure_groups = ['liquidity','microstructure','reversal','momentum','volatility']
clean_all = []
for g in pure_groups:
    if g in groups: clean_all.extend(groups[g])

all_results = []
total = 0

def call(ids, method, timeout=TIMEOUT):
    for attempt in range(3):
        try:
            r = session.post(f'{BASE}/api/superalpha',
                json={'alpha_ids': ids, 'method': method, 'oos_only': True},
                timeout=timeout)
            data = r.json()
            if data.get('success'):
                m = data.get('combined_metrics', {})
                return {'ok': True, 'sharpe': m.get('sharpe',0), 'ic': m.get('pearson_ic',0),
                        'icir': m.get('icir',0), 'fitness': m.get('fitness',0),
                        'annual_excess': m.get('annual_excess',0), 'max_dd': m.get('max_drawdown',0),
                        'turnover': m.get('turnover',0), 'n_valid': data.get('n_valid_factors',0)}
            if '503' in str(r.status_code) or '正在处理' in str(data.get('error','')):
                time.sleep(10); continue
            return {'ok': False, 'error': str(data.get('error','?'))[:100]}
        except requests.Timeout:
            time.sleep(5)
        except Exception as e:
            time.sleep(5)
    return {'ok': False, 'error': 'timeout'}

def run(ids, method, label, pool, ptype, n, avg_ic):
    global total
    total += 1
    t0 = time.time()
    result = call(ids, method)
    t = time.time()-t0
    if result.get('ok'):
        entry = {'label':label,'method':method,'pool':pool,'pool_type':ptype,
                 'n_factors':n,'avg_is_ic':round(avg_ic,4),'elapsed':round(t,1),**result}
        all_results.append(entry)
        print(f'[{total}] {label:45s} S={result["sharpe"]:7.2f} IC={result["ic"]:7.4f} ({t:.0f}s)')
    else:
        print(f'[{total}] {label:45s} ERR: {result.get("error","?")}')
    if total % 5 == 0:
        out = os.path.join(OUTPUT_DIR, f'round2_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        with open(out,'w') as f: json.dump({'total':total,'results':all_results}, f, indent=2, default=str)
    time.sleep(1.5)

t0_global = datetime.now()
print(f'\n=== ROUND 2 — {t0_global.strftime("%H:%M:%S")} ===\n')

# ==== A. Best groups deep dive (momentum, reversal showed high Sharpe) ====
print('--- A. Deep dive: momentum, reversal ---')
for gk in ['momentum','reversal','microstructure']:
    gf = sorted(groups.get(gk,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
    for n in [6,7,9,12,18,min(22,len(gf))]:
        if n>len(gf): continue
        ids = [r['id'] for r in gf[:n]]
        ai = sum(r['metrics'].get('is_pearson_ic',0) for r in gf[:n])/n
        for m in ['equal','icir','ridge']:
            run(ids, m, f'{m}-{gk}-N{n}', gk, 'within', n, ai)

# ==== B. Cross-style best-of-each ====
print('\n--- B. Best-of-each cross-style ---')
best_each = []
for gk in pure_groups:
    gf = sorted(groups.get(gk,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
    if gf: best_each.extend(gf[:3])
ids_be = [r['id'] for r in sorted(best_each, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)]
for n in [5,8,10,15]:
    if n>len(ids_be): continue
    ai = sum(r['metrics'].get('is_pearson_ic',0) for r in ids_be[:n])/n
    for m in ['equal','icir','ridge']:
        run(ids_be[:n], m, f'{m}-best_each-N{n}', 'best_each', 'cross', n, ai)

# ==== C. Mid-size winners (N=8-15 from different pools) ====
print('\n--- C. Mid-size combos ---')
clean_by_ic = sorted(clean_all, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
mixed_by_ic = sorted(groups.get('mixed',[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
all_by_ic = sorted(records, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
all_by_sharpe = sorted(records, key=lambda r: r['metrics'].get('is_sharpe',0), reverse=True)

for label, pool, sizes in [
    ('clean', clean_by_ic, [8,12,15,25,40,75]),
    ('mixed', mixed_by_ic, [8,15,25,40,75]),
    ('topIC', all_by_ic, [8,12,20,40,60,150,250]),
    ('topSharpe', all_by_sharpe, [8,15,25,40,75]),
]:
    for n in sizes:
        if n>len(pool): continue
        ids = [r['id'] for r in pool[:n]]
        ai = sum(r['metrics'].get('is_pearson_ic',0) for r in pool[:n])/n
        for m in ['equal','icir','ridge']:
            run(ids, m, f'{m}-{label}-N{n}', label, 'all', n, ai)

# ==== D. Small precision combos (N=3-7, best IC factors) ====
print('\n--- D. Small precision ---')
for n in [3,4,5,6,7]:
    ids = [r['id'] for r in all_by_ic[:n]]
    ai = sum(r['metrics'].get('is_pearson_ic',0) for r in all_by_ic[:n])/n
    for m in ['equal','icir','ridge']:
        run(ids, m, f'{m}-precision-N{n}', 'precision', 'all', n, ai)

# ==== E. Style-balanced with different per-group counts ====
print('\n--- E. Style-balanced ---')
for per_g in [2,4,6]:
    bal = []
    for gk in pure_groups:
        gf = sorted(groups.get(gk,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
        bal.extend(gf[:per_g])
    if len(bal)<5: continue
    ids = [r['id'] for r in bal]
    n = len(ids)
    ai = sum(r['metrics'].get('is_pearson_ic',0) for r in bal)/n
    for m in ['equal','icir','ridge']:
        run(ids, m, f'{m}-balanced-x{per_g}', 'balanced', 'balanced', n, ai)

# Save final
out = os.path.join(OUTPUT_DIR, f'round2_final_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
with open(out,'w') as f: json.dump({'total':total,'results':all_results}, f, indent=2, default=str)

t1 = datetime.now()
print(f'\n=== ROUND 2 DONE: {total} experiments, {len(all_results)} ok, {(t1-t0_global).total_seconds()/60:.1f}min ===')

# Top 10
print('\nTop 10 by Sharpe:')
for r in sorted(all_results, key=lambda x: -x.get('sharpe',0))[:10]:
    print(f'  {r["label"]:45s} S={r.get("sharpe",0):.2f} IC={r.get("ic",0):.4f}')
