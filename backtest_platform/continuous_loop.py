"""
CONTINUOUS experiment loop — NEVER stops.
Restarts Flask when memory exceeds threshold.
Reports progress every 30 min.
"""
import requests, json, time, os, sys, subprocess, traceback
from datetime import datetime, timedelta

BASE = 'http://127.0.0.1:5000'
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'experiment_results')
os.makedirs(OUTPUT_DIR, exist_ok=True)

PYTHON = r'python'
APP = os.path.join(SCRIPT_DIR, 'app.py')

def restart_flask():
    """Restart only the Flask process, don't kill ourselves."""
    try:
        import psutil
        for p in psutil.process_iter():
            if 'python' in p.name().lower() and p.pid != os.getpid():
                try:
                    cmd = ' '.join(p.cmdline() if p.cmdline() else [])
                    if 'app.py' in cmd:
                        p.kill()
                        print(f'[MEM] Killed Flask PID {p.pid}', flush=True)
                except: pass
    except: pass
    time.sleep(3)
    # Start Flask
    env = os.environ.copy()
    env['DEEPSEEK_API_KEY'] = '<SET_DEEPSEEK_API_KEY_IN_ENV>'
    subprocess.Popen([PYTHON, '-u', APP], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     cwd=SCRIPT_DIR)
    # Wait until ready
    for _ in range(30):
        time.sleep(2)
        try:
            r = requests.get(f'{BASE}/login', timeout=5)
            if r.status_code == 200:
                return True
        except:
            pass
    return False

def get_session():
    s = requests.Session()
    r = s.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'}, allow_redirects=True)
    if r.status_code not in (200, 302):
        raise RuntimeError(f'Login failed: {r.status_code}')
    return s

def fetch_factors(session):
    r = session.get(f'{BASE}/api/alpha/history',
                    params={'min_is_ic': 0.01, 'limit': 2000, 'sort': 'is_pearson_ic', 'order': 'desc'})
    records = [x for x in r.json().get('records', []) if x.get('type') != 'superalpha']
    return records

def run_combo(session, alpha_ids, method='equal', timeout=180):
    for attempt in range(3):
        try:
            r = session.post(f'{BASE}/api/superalpha',
                json={'alpha_ids': alpha_ids, 'method': method, 'oos_only': True, 'neutralize': 'market_cap'},
                timeout=timeout)
            if r.status_code == 503:
                time.sleep(10)
                continue
            data = r.json()
            if data.get('success'):
                m = data.get('combined_metrics', {})
                return {
                    'ok': True,
                    'sharpe': m.get('sharpe', 0), 'ic': m.get('pearson_ic', 0),
                    'icir': m.get('icir', 0), 'fitness': m.get('fitness', 0),
                    'annual_excess': m.get('annual_excess', 0),
                    'max_drawdown': m.get('max_drawdown', 0),
                    'turnover': m.get('turnover', 0),
                    'n_valid': data.get('n_valid_factors', 0),
                    'sub_alphas': data.get('sub_alphas', []),
                }
            err = str(data.get('error', ''))
            if 'Unable to allocate' in err or 'timedelta' in err:
                return {'ok': False, 'error': 'memory', 'fatal': True}
            if '正在处理' in err:
                time.sleep(10)
                continue
            return {'ok': False, 'error': err[:100]}
        except requests.Timeout:
            time.sleep(5)
        except Exception as e:
            time.sleep(5)
    return {'ok': False, 'error': 'timeout/retry exhausted'}

def check_memory():
    try:
        import psutil
        vm = psutil.virtual_memory()
        free_gb = vm.available / (1024**3)
        # Also check Flask process memory
        flask_mem = 0
        for p in psutil.process_iter(['pid', 'name', 'memory_info']):
            if 'python' in p.info['name'].lower():
                flask_mem = max(flask_mem, p.info['memory_info'].rss / (1024**3))
        return free_gb, flask_mem
    except:
        return 99, 0

# Economic groups
_GROUPS = [
    ('momentum', ['momentum','mom_','trend','breakout','ret_20','ret_60','ret_120','cumret','ts_delta','slope','accel','relative_strength','new_high','ma_gap','ema','macd','price_strength']),
    ('reversal', ['reversal','rev_','mean_reversion','overreaction','gap','overnight','rsi','stoch','-rank(returns','-returns','-ret_','close_position','close_location','short_term_reversal']),
    ('volatility', ['volatility','realized_vol','downside','std','atr','range','high_low','skew','kurt','drawdown','max_dd','max_drawdown','beta','risk','entropy','dispersion','boll']),
    ('liquidity', ['turnover','volume','amount','dollar','liquidity','amihud','adv','money_flow','flow','trade_count','volume_profile']),
    ('microstructure', ['minute','intraday','auction','vwap','open_','close_','high_','low_','shadow','wick','body','kline','bar_','smart_money','imbalance','impact']),
]
def gk(expr):
    el = expr.lower()
    scores = [(len(set(t for t in terms if t in el)), key) for key, terms in _GROUPS]
    scores = [(s,k) for s,k in scores if s>0]
    if not scores: return 'unknown'
    scores.sort(reverse=True)
    if len(scores)>1 and scores[1][0]>=max(1,scores[0][0]-1): return 'mixed'
    return scores[0][1]

def generate_experiments(records):
    """Generate an infinite stream of experiments, cycling through different configs."""
    groups = {}
    for rec in records:
        g = gk(rec['expression'])
        if g not in groups: groups[g] = []
        groups[g].append(rec)

    pure = ['reversal','momentum','microstructure','volatility','liquidity']
    clean_all = []
    for g in pure:
        if g in groups: clean_all.extend(groups[g])

    all_by_ic = sorted(records, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
    all_by_sharpe = sorted(records, key=lambda r: r['metrics'].get('is_sharpe',0), reverse=True)

    experiment_sets = []

    # Set 1: Within-style, all sizes
    for gk_name in pure:
        gf = sorted(groups.get(gk_name,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
        for n in [3,4,5,6,7,8,9,10]:
            if n > len(gf): continue
            ids = [r['id'] for r in gf[:n]]
            for method in ['equal','icir','ridge']:
                experiment_sets.append({
                    'ids': ids, 'method': method,
                    'label': f'{method}-{gk_name}-N{n}',
                    'pool': gk_name, 'pool_type': 'within', 'n': n,
                })

    # Set 2: Top-IC (various N)
    for n in [3,4,5,6,7,8,9,10,11]:
        if n > len(all_by_ic): continue
        ids = [r['id'] for r in all_by_ic[:n]]
        for method in ['equal','icir','ridge']:
            experiment_sets.append({
                'ids': ids, 'method': method,
                'label': f'{method}-topIC-N{n}',
                'pool': 'topIC', 'pool_type': 'all', 'n': n,
            })

    # Set 3: Top-Sharpe
    for n in [5,8,10]:
        if n > len(all_by_sharpe): continue
        ids = [r['id'] for r in all_by_sharpe[:n]]
        for method in ['equal','icir','ridge']:
            experiment_sets.append({
                'ids': ids, 'method': method,
                'label': f'{method}-topSharpe-N{n}',
                'pool': 'topSharpe', 'pool_type': 'all', 'n': n,
            })

    # Set 4: Cross-style (greedy, one per group)
    from collections import Counter
    sel = []
    used = Counter()
    for f in sorted(clean_all, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True):
        g = gk(f['expression'])
        if used[g] < 2:
            sel.append(f)
            used[g] += 1
        if len(sel) >= 10: break
    for n in [5,8,10]:
        if n > len(sel): continue
        ids = [r['id'] for r in sel[:n]]
        for method in ['equal','icir','ridge']:
            experiment_sets.append({
                'ids': ids, 'method': method,
                'label': f'{method}-cross_greedy-N{n}',
                'pool': 'cross', 'pool_type': 'cross', 'n': n,
            })

    # Set 5: Clean pool
    clean_sorted = sorted(clean_all, key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
    for n in [8,10,15]:
        if n > len(clean_sorted): continue
        ids = [r['id'] for r in clean_sorted[:n]]
        for method in ['equal','icir','ridge']:
            experiment_sets.append({
                'ids': ids, 'method': method,
                'label': f'{method}-clean-N{n}',
                'pool': 'clean', 'pool_type': 'all_pure', 'n': n,
            })

    # Set 6: Balanced
    for per_g in [1,2,3]:
        bal = []
        for gk_name in pure:
            gf = sorted(groups.get(gk_name,[]), key=lambda r: r['metrics'].get('is_pearson_ic',0), reverse=True)
            bal.extend(gf[:per_g])
        ids = [r['id'] for r in bal]
        for method in ['equal','icir','ridge']:
            experiment_sets.append({
                'ids': ids, 'method': method,
                'label': f'{method}-balanced-x{per_g}',
                'pool': 'balanced', 'pool_type': 'balanced', 'n': len(ids),
            })

    return experiment_sets

def save_results(results, label=''):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f'continuous_{label}_{ts}.json'
    path = os.path.join(OUTPUT_DIR, fname)
    with open(path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    return path

def main():
    print(f"=== CONTINUOUS LOOP — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===", flush=True)

    # Initial restart
    if not restart_flask():
        print("FATAL: Cannot start Flask", flush=True)
        return

    session = get_session()
    records = fetch_factors(session)
    print(f"Loaded {len(records)} factors", flush=True)

    all_experiments = generate_experiments(records)
    print(f"Total experiments in one cycle: {len(all_experiments)}", flush=True)

    results = []
    idx = 0
    cycle = 0
    consecutive_errors = 0
    last_report = datetime.now()
    last_flask_restart = datetime.now()

    while True:
        if idx >= len(all_experiments):
            idx = 0
            cycle += 1
            # Save cycle results
            save_results(results, f'cycle{cycle}')
            print(f"\n=== CYCLE {cycle} COMPLETE: {len(results)} results ===\n", flush=True)

        exp = all_experiments[idx]
        idx += 1

        # Check memory, restart Flask if needed
        free_gb, flask_gb = check_memory()
        if flask_gb > 3.5 or free_gb < 1.0:
            print(f"[MEM] Flask {flask_gb:.1f}GB, free {free_gb:.1f}GB — restarting Flask...", flush=True)
            if not restart_flask():
                print("FATAL: Flask restart failed", flush=True)
                time.sleep(60)
                continue
            session = get_session()
            records = fetch_factors(session)
            all_experiments = generate_experiments(records)
            last_flask_restart = datetime.now()
            consecutive_errors = 0

        # Run experiment
        t0 = time.time()
        result = run_combo(session, exp['ids'], exp['method'])
        elapsed = time.time() - t0

        if result.get('ok'):
            entry = {**exp, 'elapsed': round(elapsed, 1), **{k: v for k, v in result.items() if k != 'ok'}}
            results.append(entry)
            consecutive_errors = 0
            print(f"[{len(results)}] {exp['label']:40s} S={result['sharpe']:7.2f} IC={result['ic']:7.4f} ({elapsed:.0f}s)", flush=True)
        else:
            consecutive_errors += 1
            err = result.get('error', '?')
            print(f"[{len(results)}] {exp['label']:40s} ERR: {err[:80]}", flush=True)

            # If fatal memory error, restart Flask
            if result.get('fatal'):
                print("FATAL memory error, restarting Flask...", flush=True)
                restart_flask()
                session = get_session()
                last_flask_restart = datetime.now()
                consecutive_errors = 0

            # If too many consecutive errors, restart
            if consecutive_errors > 10:
                print(f"Too many errors ({consecutive_errors}), restarting Flask...", flush=True)
                restart_flask()
                session = get_session()
                last_flask_restart = datetime.now()
                consecutive_errors = 0

        # 30-min report
        if (datetime.now() - last_report).total_seconds() >= 1800:
            last_report = datetime.now()
            free_gb, flask_gb = check_memory()
            print(f"\n=== REPORT {datetime.now().strftime('%H:%M:%S')} ===", flush=True)
            print(f"  Results: {len(results)} | Cycle: {cycle} | Errors: {consecutive_errors}", flush=True)
            print(f"  Memory: Flask {flask_gb:.1f}GB, Free {free_gb:.1f}GB", flush=True)
            if results:
                top5 = sorted(results, key=lambda x: -x.get('sharpe', 0))[:5]
                print(f"  Top Sharpe:", flush=True)
                for r in top5:
                    print(f"    {r['label']:40s} S={r.get('sharpe',0):.2f} IC={r.get('ic',0):.4f}", flush=True)
            save_results(results, 'checkpoint')
            print(f"=== END REPORT ===\n", flush=True)

        time.sleep(1)

if __name__ == '__main__':
    main()

