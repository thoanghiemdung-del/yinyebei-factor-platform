#!/usr/bin/env python3
"""
Clean factor mining worker — Flask API backend.
- Avoids duplicate expressions
- Minute + daily field combos with economic logic
- Quality checks: |IC|>0.01, max_corr<0.7, |Sharpe|<50
- Logs to logs/mine.log
"""
import json, sqlite3, time, datetime, urllib.request, urllib.parse, os
from http.cookiejar import CookieJar

API = 'http://127.0.0.1:5000'
DB = os.path.join(os.path.dirname(__file__), 'backtest.db')
LOG = os.path.join(os.path.dirname(__file__), '..', 'logs', 'mine.log')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def opener():
    cj = CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    o.open(urllib.request.Request(f'{API}/login',
        urllib.parse.urlencode({'username':'admin','password':'quant2026'}).encode()))
    return o

def backtest(expr, neut='market_cap'):
    """Run backtest via sync API. Returns metrics dict or None."""
    o = opener()
    data = json.dumps({'expression': expr, 'neutralize': neut}).encode()
    try:
        resp = o.open(urllib.request.Request(f'{API}/api/backtest', data=data,
            {'Content-Type': 'application/json'}), timeout=600)
        r = json.loads(resp.read().decode())
        if 'error' in r:
            return None
        return {
            'ic': r.get('pearson_ic', 0),
            'sh': r.get('sharpe', 0),
            'fit': r.get('fitness', 0),
            'to': r.get('turnover', 0),
            'ae': r.get('annual_excess', 0),
            'dd': r.get('max_drawdown', 0),
            'pnl': r.get('pnl_series', []),
        }
    except Exception as e:
        return None

def load_existing():
    """Load existing single factors with PnL data for correlation check."""
    conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, expression, pnl_json, metrics_json FROM alpha_history"
    ).fetchall()
    conn.close()
    exist = []
    tested = set()
    for row in rows:
        t = row['type'] if 'type' in row.keys() else None
        expr = row['expression'] or ''
        if 'lgb(' in expr or 'superalpha(' in expr:
            continue
        tested.add(expr.strip())
        try:
            pnl_raw = json.loads(row['pnl_json'] or '[]')
            if len(pnl_raw) < 20:
                continue
            dailies = [pnl_raw[i] - pnl_raw[i-1] for i in range(1, len(pnl_raw))]
        except Exception:
            continue
        exist.append({'id': row['id'], 'expr': expr, 'dailies': dailies})
    return exist, tested

def max_correlation(new_dailies, existing_factors):
    """Compute max pairwise correlation of new dailies vs all existing."""
    max_c = 0.0
    for ef in existing_factors:
        a = new_dailies[-min(len(new_dailies), len(ef['dailies'])):]
        b = ef['dailies'][-len(a):]
        valid = (a - a + 1) & (b - b + 1)  # True for finite values
        a_f = [av for av, bv in zip(a, b) if av == av and bv == bv]
        b_f = [bv for av, bv in zip(a, b) if av == av and bv == bv]
        if len(a_f) < 20:
            continue
        import numpy as np
        c = abs(float(np.corrcoef(np.array(a_f), np.array(b_f))[0, 1]))
        if c > max_c:
            max_c = c
    return max_c

def save(expr, metrics):
    """Save a new factor to DB."""
    import uuid
    eid = str(uuid.uuid4())
    ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    name = expr[:40] + ('...' if len(expr) > 40 else '')
    clean = {k: (None if v != v or v == float('inf') or v == float('-inf') else v)
             for k, v in metrics.items() if k != 'pnl'}
    conn = sqlite3.connect(DB)
    conn.execute(
        'INSERT INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json) '
        'VALUES(?,?,?,?,?,?,?,?)',
        (eid, name, expr, ts, 'alpha',
         json.dumps(clean), json.dumps(metrics.get('pnl', [])), json.dumps([])))
    conn.commit(); conn.close()
    return eid

# ---- Factor generators ----
MINUTE = ['intraday_volatility', 'price_efficiency', 'vwap_gap', 'volume_concentration',
          'close_location', 'upper_shadow_pct', 'lower_shadow_pct',
          'morning_return', 'afternoon_return', 'first30min_return', 'last30min_return',
          'body_return', 'am_pm_divergence']

DAILY = ['returns', 'ret_5d', 'ret_20d', 'ret_60d', 'ret_120d_skip5',
         'vol_20d', 'vol_60d', 'downside_vol_60d', 'skewness_60d',
         'sharpe_60d', 'amihud_20d', 'turnover_rate', 'volume_profile_ratio',
         'volume_breakout', 'rsi_14', 'bollinger_pos', 'beta_60d']

PAIRS = [
    # Each pair = (field_a, sign_a, field_b, sign_b, op, description)
    # Multiply pairs
    ('intraday_volatility', '-', 'price_efficiency', '', '×', '低波×高效=低噪趋势'),
    ('intraday_volatility', '-', 'close_location', '', '×', '低波×高位收=买方无阻'),
    ('price_efficiency', '', 'volume_concentration', '', '×', '高效×量集中=机构方向'),
    ('price_efficiency', '', 'volume_concentration', '-', '×', '高效×量分散=散户一致'),
    ('vwap_gap', '', 'volume_concentration', '', '×', 'VWAP溢价×量集中=主动买'),
    ('vwap_gap', '-', 'volume_concentration', '', '×', 'VWAP折价×量集中=压盘吸筹'),
    ('close_location', '', 'lower_shadow_pct', '', '×', '高位收×下影=V型反转'),
    ('close_location', '', 'upper_shadow_pct', '-', '×', '高位收×短上影=控盘'),
    ('first30min_return', '', 'last30min_return', '', '×', '早盘×尾盘=全天买入'),
    ('morning_return', '-', 'afternoon_return', '', '×', '上午弱×下午强=尾盘拉'),
    ('price_efficiency', '', 'close_location', '', '×', '高效×高位收=趋势确认'),
    ('vwap_gap', '', 'first30min_return', '', '×', 'VWAP×早盘=机构开盘买'),
    ('body_return', '', 'close_location', '', '×', '大实体×高位收=方向明确'),
    # Subtract pairs
    ('vwap_gap', '', 'upper_shadow_pct', '-', '-', 'VWAP溢价-上影=去除冲高回落'),
    ('close_location', '', 'upper_shadow_pct', '-', '-', '高位收-短上影=真正的强势'),
    ('price_efficiency', '', 'am_pm_divergence', '-', '-', '高效-背离=信息连续消化'),
    # Cross: minute × daily
    ('close_location', '', 'ret_20d', '', '×', '高位收×动量=趋势延续'),
    ('vwap_gap', '', 'sharpe_60d', '', '×', 'VWAP×夏普=质量资金流'),
    ('intraday_volatility', '-', 'amihud_20d', '-', '×', '低波×高流动性=机构稳定'),
    ('price_efficiency', '', 'turnover_rate', '', '×', '高效×活跃=真实趋势'),
    ('close_location', '', 'skewness_60d', '-', '×', '高位收×负偏回避=安全强势'),
]

def generate_new_expressions(tested_set):
    """Generate new factor expressions not yet tested."""
    new = []
    for a, sa, b, sb, op, desc in PAIRS:
        ae = f"-rank({a})" if sa == '-' else f"rank({a})"
        be = f"-rank({b})" if sb == '-' else f"rank({b})"
        if op == '×':
            expr = f"{ae} * {be}"
        else:
            expr = f"{ae} - {be}"
        if expr not in tested_set:
            tested_set.add(expr)
            new.append((expr, desc))
    return new


def run_round(round_num, target=500):
    """Single mining round. Returns number of new factors saved."""
    existing, tested = load_existing()
    n_exist = len(existing)
    log(f"Round {round_num}: {n_exist}/{target} existing")

    candidates = generate_new_expressions(tested)
    if not candidates:
        log("  No new candidates — all combos tested")
        return 0

    passed = 0
    for expr, desc in candidates:
        m = backtest(expr)
        if m is None:
            continue
        if abs(m['ic']) <= 0.01:
            continue
        if abs(m['sh']) > 50:
            continue

        pnl = m.get('pnl', [])
        if len(pnl) < 50:
            continue

        import numpy as np
        dailies = np.array([pnl[i] - pnl[i-1] for i in range(1, len(pnl))])
        mc = max_correlation(list(dailies), existing)
        if mc > 0.7:
            log(f"  CORR SKIP max_c={mc:.3f} IC={m['ic']:+.04f} | {desc}")
            continue

        eid = save(expr, m)
        existing.append({'id': eid, 'expr': expr, 'dailies': list(dailies)})
        passed += 1
        log(f"  KEPT #{len(existing)} IC={m['ic']:+.04f} S={m['sh']:.2f} "
            f"TO={m['to']:.3f} corr={mc:.2f} | {desc}")

    log(f"  Round result: {passed}/{len(candidates)} passed")
    return passed


if __name__ == '__main__':
    log("=" * 40 + " MINE WORKER START " + "=" * 40)
    for r in range(1, 99999):
        run_round(r, 500)
        time.sleep(3)
