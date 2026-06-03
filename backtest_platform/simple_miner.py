#!/usr/bin/env python3
"""Factor miner. Test economically whitelisted expressions, save if |IC|>0.01."""
import urllib.request, urllib.parse, json, sqlite3, datetime, time, os, uuid, socket, ctypes
import re
from http.cookiejar import CookieJar
import numpy as np
from yyb_factor_policy import eligible_expr

API = 'http://127.0.0.1:5000'
TARGET = 1000
DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DIR, 'backtest.db')
LOG = os.path.join(DIR, '..', 'logs', 'simple_miner.log')
SEEN_FILE = os.path.join(DIR, '..', 'logs', 'simple_miner_seen.txt')
os.makedirs(os.path.dirname(LOG), exist_ok=True)

_seen = set()
_db_exprs = None
_start = time.time()
_none_streak = 0
FAST_ONLY = os.environ.get('YYB_FAST_ONLY', '1') != '0'
DIVERSIFY_FIELDS = os.environ.get('YYB_DIVERSIFY_FIELDS', '1') != '0'
HEAVY_OPS = ('ts_corr(', 'ts_rank(', 'ts_mean(', 'ts_delta(', 'ts_decay_linear(', 'ts_delay(', 'winsorize(')
CORR_THRESHOLD = 0.7
MIN_FREE_GB = float(os.environ.get('YYB_MINER_MIN_FREE_GB', '2.0'))
LOW_MEM_SLEEP = int(os.environ.get('YYB_MINER_LOW_MEM_SLEEP', '60'))

MINUTE_CORE = ['intraday_volatility','price_efficiency','vwap_gap','volume_concentration',
               'close_location','upper_shadow_pct','lower_shadow_pct','morning_return',
               'afternoon_return','first30min_return','last30min_return','body_return',
               'am_pm_divergence']

# Diversify mode shifts new work away from the saturated pure-minute pool.
LIQUIDITY_FAST = ['volume_profile_ratio', 'turnover_rate', 'volume_breakout',
                  'turnover_5d', 'turnover_change', 'amihud_20d', 'log_dollar_vol']
MOM_REV_FAST = ['ret_5d', 'ret_20d', 'ret_60d', 'ret_120d_skip5',
                'rev_1d', 'rev_5d',
                'rev_overnight', 'abnormal_vol_rev']
VOL_TECH_FAST = ['vol_20d', 'vol_60d', 'vol_ratio', 'downside_vol_60d',
                 'max_dd_60d', 'rsi_14',
                 'bollinger_pos', 'beta_60d', 'market_cap_rank']
PATTERN_FAST = ['auction_return', 'gap_up', 'upper_shadow', 'lower_shadow',
                'body_ratio', 'close_vs_high_20d']
# Keep the active fast pool on daily/technical/liquidity fields. Minute-heavy
# microstructure fields are reintroduced manually after the server is stable.
MICRO_FAST = []
CROSS_FAST = ['mom_vol_conf', 'mom_liquidity_adj', 'rev_vol_conf']

M = (LIQUIDITY_FAST + MOM_REV_FAST + VOL_TECH_FAST + PATTERN_FAST + MICRO_FAST + CROSS_FAST) if DIVERSIFY_FIELDS else MINUTE_CORE

FLOW = ['volume_profile_ratio', 'turnover_rate', 'amihud_20d',
        'log_dollar_vol'] if DIVERSIFY_FIELDS else [
        'vwap_gap', 'volume_concentration', 'close_location', 'price_efficiency']
RETURN = ['ret_5d', 'ret_20d', 'ret_60d', 'rev_1d', 'rev_5d',
          'rev_overnight', 'abnormal_vol_rev'] if DIVERSIFY_FIELDS else [
          'morning_return', 'afternoon_return', 'first30min_return',
          'last30min_return', 'body_return', 'am_pm_divergence']
SHAPE = ['vol_20d', 'vol_60d', 'vol_ratio', 'downside_vol_60d',
         'rsi_14', 'bollinger_pos'] if DIVERSIFY_FIELDS else [
         'intraday_volatility', 'upper_shadow_pct', 'lower_shadow_pct']

MICRO = ['first30_mom', 'last30_mom', 'intraday_mom', 'realized_vol',
         'vol_skew', 'close_vs_vwap', 'vwap_trend', 'volume_hhi',
         'open_vol_ratio', 'close_vol_ratio', 'smart_money_vol',
         'amihud_min', 'large_trade_ratio', 'roll_spread',
         'close_manipulation', 'triple_confirm', 'wat',
         'large_trade_signal', 'smart_money_vwap', 'vol_conc_mom']

LIQUIDITY = ['volume_profile_ratio', 'turnover_rate', 'volume_trend_20d',
             'amount_volatility', 'volume_price_corr', 'amihud_20d',
             'mom_liquidity_adj', 'liquidity_premium']

VOL_RISK = ['vol_5d', 'vol_10d', 'vol_20d', 'vol_40d', 'downside_vol_60d',
            'down_up_vol_ratio', 'vol_ratio', 'vol_ratio_20_60',
            'skewness_20d', 'skewness_60d', 'kurtosis_60d',
            'max_ret_20d', 'min_ret_20d']

TREND_REV = ['ret_10d', 'ret_20d', 'ret_40d', 'cumret_5d',
             'rev_5d', 'rev_10d', 'rev_20d', 'rev_vol_regime',
             'rsi_14', 'bollinger_pos', 'gap_down', 'gap_up',
             'close_vs_low_20d', 'doji_score']

CROSS_MODAL = ['mom_vol_conf', 'rev_vol_conf', 'intraday_ret5d',
               'vwap_close_mom', 'smart_money_rev', 'volume_price_div',
               'gap_momentum']

SLOW_FAST_FIELDS = set(MICRO) | set(LIQUIDITY) | set(VOL_RISK) | set(TREND_REV) | set(CROSS_MODAL)
FAST_ALLOWED_EXTRA_FIELDS = (
    set(LIQUIDITY_FAST) | set(MOM_REV_FAST) | set(VOL_TECH_FAST) |
    set(PATTERN_FAST) | set(MICRO_FAST) | set(CROSS_FAST)
)

PAIR_THEMES = [
    ('intraday_volatility', 'price_efficiency'),
    ('intraday_volatility', 'vwap_gap'),
    ('intraday_volatility', 'volume_concentration'),
    ('intraday_volatility', 'close_location'),
    ('intraday_volatility', 'morning_return'),
    ('intraday_volatility', 'last30min_return'),
    ('price_efficiency', 'vwap_gap'),
    ('price_efficiency', 'volume_concentration'),
    ('price_efficiency', 'close_location'),
    ('price_efficiency', 'body_return'),
    ('vwap_gap', 'volume_concentration'),
    ('vwap_gap', 'close_location'),
    ('vwap_gap', 'morning_return'),
    ('vwap_gap', 'last30min_return'),
    ('vwap_gap', 'body_return'),
    ('volume_concentration', 'close_location'),
    ('volume_concentration', 'first30min_return'),
    ('volume_concentration', 'last30min_return'),
    ('close_location', 'upper_shadow_pct'),
    ('close_location', 'lower_shadow_pct'),
    ('close_location', 'morning_return'),
    ('close_location', 'afternoon_return'),
    ('close_location', 'last30min_return'),
    ('upper_shadow_pct', 'morning_return'),
    ('upper_shadow_pct', 'last30min_return'),
    ('lower_shadow_pct', 'morning_return'),
    ('lower_shadow_pct', 'body_return'),
    ('morning_return', 'afternoon_return'),
    ('first30min_return', 'last30min_return'),
    ('body_return', 'am_pm_divergence'),
]

if DIVERSIFY_FIELDS:
    PAIR_THEMES = [
        ('volume_profile_ratio', 'ret_20d'),
        ('volume_profile_ratio', 'rev_5d'),
        ('turnover_rate', 'abnormal_vol_rev'),
        ('volume_breakout', 'rev_overnight'),
        ('turnover_change', 'ret_5d'),
        ('amihud_20d', 'ret_60d'),
        ('log_dollar_vol', 'market_cap_rank'),
        ('vol_20d', 'ret_20d'),
        ('vol_60d', 'ret_60d'),
        ('downside_vol_60d', 'rev_5d'),
        ('max_dd_60d', 'rev_overnight'),
        ('rsi_14', 'rev_5d'),
        ('bollinger_pos', 'ret_20d'),
        ('large_trade_ratio', 'turnover_change'),
        ('mom_liquidity_adj', 'amihud_20d'),
        ('liquidity_premium', 'market_cap_rank'),
    ]

ALLOWED_NAMES = set(M) | {
    'rank', 'ts_delta', 'ts_rank', 'ts_mean', 'ts_corr', 'signed_power',
    'abs', 'winsorize', 'ts_delay', 'ts_decay_linear',
}


def minute_only(expr):
    return eligible_expr(expr)


def load_seen():
    try:
        if not os.path.exists(SEEN_FILE):
            return
        with open(SEEN_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    _seen.add(line)
    except Exception as e:
        log(f"seen load failed: {e}")


def save_seen():
    try:
        with open(SEEN_FILE, 'w', encoding='utf-8') as f:
            for expr in sorted(_seen):
                f.write(expr + '\n')
    except Exception as e:
        log(f"seen save failed: {e}")


def load_db_exprs():
    global _db_exprs
    if _db_exprs is not None:
        return _db_exprs
    try:
        c = sqlite3.connect(DB, timeout=10)
        rows = c.execute("SELECT trim(expression) FROM alpha_history").fetchall()
        c.close()
        _db_exprs = {r[0] for r in rows if r and r[0]}
    except Exception as e:
        log(f"db expr cache failed: {e}")
        _db_exprs = set()
    return _db_exprs

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def free_memory_gb():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong),
            ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong),
            ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong),
            ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong),
            ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullAvailPhys / (1024 ** 3)
    except Exception:
        return None
    return None


def wait_for_memory():
    if MIN_FREE_GB <= 0:
        return
    while True:
        free = free_memory_gb()
        if free is None or free >= MIN_FREE_GB:
            return
        log(f"low memory free={free:.2f}GB < {MIN_FREE_GB:.2f}GB; sleep {LOW_MEM_SLEEP}s before backtest")
        time.sleep(LOW_MEM_SLEEP)

def opener():
    cj = CookieJar()
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    o.open(urllib.request.Request(f'{API}/login',
        urllib.parse.urlencode({'username': 'admin', 'password': 'quant2026'}).encode()))
    return o

def bt(expr, timeout=None):
    try:
        wait_for_memory()
        o = opener()
        data = json.dumps({
            'expression': expr,
            'neutralize': 'market_cap',
            'save_history': False,
        }).encode()
        req = urllib.request.Request(f'{API}/api/backtest', data=data,
                                     headers={'Content-Type': 'application/json'})
        if timeout is None:
            timeout = 240 if any(op in expr for op in ['ts_corr', 'ts_rank']) else 180
        return json.loads(o.open(req, timeout=timeout).read().decode())
    except Exception as e:
        log(f"bt exception {type(e).__name__}: {str(e)[:100]} | {expr[:80]}")
        return None

def in_db(expr):
    key = expr.strip()
    if key in _seen: return True
    db_exprs = load_db_exprs()
    if key in db_exprs:
        _seen.add(key)
        return True
    return False


def score_metrics(metrics):
    ic = metrics.get('pearson_ic') or 0.0
    sharpe = metrics.get('sharpe') or 0.0
    fitness = metrics.get('fitness') or 0.0
    try:
        return abs(float(ic)) * max(abs(float(sharpe)), 1e-6) + 0.01 * abs(float(fitness))
    except Exception:
        return 0.0


def daily_from_cum(values):
    try:
        arr = np.array(values or [], dtype=float)
    except Exception:
        return np.array([], dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) <= 2:
        return np.array([], dtype=float)
    return np.diff(arr)


def corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return float('nan')
    x = a[-n:]
    y = b[-n:]
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return float('nan')
    x = x[m]
    y = y[m]
    if np.nanstd(x) <= 1e-12 or np.nanstd(y) <= 1e-12:
        return float('nan')
    return float(np.corrcoef(x, y)[0, 1])


def correlation_gate(expr, metrics, pnl_series):
    cand_daily = daily_from_cum(pnl_series)
    if len(cand_daily) < 30:
        return False, "short_pnl"
    cand_score = score_metrics(metrics)
    try:
        c = sqlite3.connect(DB, timeout=10)
        c.row_factory = sqlite3.Row
        rows = c.execute(
            "SELECT rowid, expression, metrics_json, pnl_json FROM alpha_history "
            "WHERE ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01 "
            "AND pnl_json IS NOT NULL AND length(pnl_json)>5"
        ).fetchall()
        losers = []
        for row in rows:
            old_expr = row['expression']
            if not eligible_expr(old_expr):
                continue
            try:
                old_metrics = json.loads(row['metrics_json'] or '{}')
                old_daily = daily_from_cum(json.loads(row['pnl_json'] or '[]'))
            except Exception:
                continue
            cval = corr(cand_daily, old_daily)
            if not np.isfinite(cval) or abs(cval) <= CORR_THRESHOLD:
                continue
            old_score = score_metrics(old_metrics)
            if cand_score <= old_score:
                c.close()
                return False, f"corr={abs(cval):.3f} <= existing_score={old_score:.5f}"
            losers.append((row['rowid'], abs(cval), old_score, old_expr[:70]))
        if losers:
            if len(losers) > 1:
                loser_sum = sum(old_score for _, _, old_score, _ in losers)
                if cand_score <= loser_sum:
                    c.close()
                    return False, (
                        f"multi_corr={len(losers)} cand_score={cand_score:.5f} "
                        f"<= loser_sum={loser_sum:.5f}"
                    )
            c.executemany("DELETE FROM alpha_history WHERE rowid=?", [(rowid,) for rowid, _, _, _ in losers])
            c.commit()
            log("replace_corr " + " | ".join(f"{cv:.3f}:{ex}" for _, cv, _, ex in losers[:3]))
        c.close()
        return True, ""
    except Exception as e:
        log(f"corr_gate_error {type(e).__name__}: {str(e)[:100]}")
        return True, ""

def save(expr, r):
    try:
        eid = str(uuid.uuid4())
        ts = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        cl = {}
        for k in [
            'pearson_ic', 'rank_ic', 'icir', 'ic_positive_ratio',
            'annual_excess', 'returns', 'sharpe', 'turnover', 'fitness',
            'max_drawdown', 'margin_bps', 'sortino', 'win_rate', 'n_days'
        ]:
            v = r.get(k, 0)
            cl[k] = None if isinstance(v, float) and (v != v or v in [float('inf'), float('-inf')]) else v
        ok, reason = correlation_gate(expr, cl, r.get('pnl_series', []))
        if not ok:
            log(f"skip corr | {reason} | {expr[:90]}")
            return False
        c = sqlite3.connect(DB, timeout=5)
        c.execute("INSERT OR IGNORE INTO alpha_history (id,name,expression,timestamp,type,metrics_json,pnl_json,ic_json,max_corr,neutralization) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (eid, expr[:40], expr, ts, 'alpha', json.dumps(cl),
                   json.dumps(r.get('pnl_series', [])), json.dumps([]), 0.0, 'market_cap'))
        c.commit(); c.close()
        load_db_exprs().add(expr.strip())
        return True
    except sqlite3.IntegrityError:
        return False

def count():
    try:
        c = sqlite3.connect(DB, timeout=5)
        rows = c.execute(
            "SELECT expression FROM alpha_history "
            "WHERE ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01 "
            "AND pnl_json IS NOT NULL AND length(pnl_json)>5"
        ).fetchall()
        c.close()
        return sum(1 for (expr,) in rows if minute_only(expr))
    except Exception:
        return -1


def flask_ok():
    try:
        urllib.request.urlopen(f'{API}/api/fields', timeout=5)
        return True
    except Exception:
        return False


def api_port_open():
    try:
        with socket.create_connection(('127.0.0.1', 5000), timeout=2):
            return True
    except Exception:
        return False


def expr_timeout(expr):
    if 'ts_corr' in expr:
        return 300
    if any(op in expr for op in ['ts_rank', 'ts_decay_linear', 'ts_mean']):
        return 240
    if FAST_ONLY:
        return 180
    return 180

def build():
    exprs = []; s = set()
    def is_heavy(e):
        return any(op in e for op in HEAVY_OPS)

    def add(e):
        e = e.strip()
        if FAST_ONLY and is_heavy(e):
            return
        if FAST_ONLY and '/' in e:
            return
        if FAST_ONLY:
            ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", e))
            slow_ids = ids & SLOW_FAST_FIELDS
            if slow_ids and not (DIVERSIFY_FIELDS and slow_ids <= FAST_ALLOWED_EXTRA_FIELDS):
                return
        if e not in s and e not in _seen and not in_db(e):
            s.add(e); exprs.append(e)

    if DIVERSIFY_FIELDS:
        for anchor in ['ret_20d', 'rev_5d', 'vol_20d', 'amihud_20d',
                       'turnover_rate', 'rsi_14', 'volume_breakout',
                       'turnover_change']:
            for context in ['market_cap_rank', 'vol_ratio', 'volume_profile_ratio',
                            'downside_vol_60d', 'bollinger_pos']:
                for e in [
                    f"rank({anchor}) - rank({context})",
                    f"-rank({anchor}) + rank({context})",
                    f"zscore({anchor}) * rank({context})",
                    f"-zscore({anchor}) * rank({context})",
                    f"rank(abs(zscore({anchor}) - zscore({context})))",
                    f"-rank(abs(zscore({anchor}) - zscore({context})))",
                ]:
                    add(e)

    # Existing fast cross-sectional patterns.
    for i,a in enumerate(M):
        for b in M[i+1:]:
            for e in [f"-rank({a}) * rank({b})", f"-rank({a}) - rank({b})",
                      f"rank({a}) + rank({b})", f"-rank({a}) - rank({b})"]:
                add(e)
    for f in M:
        for e in [
            f"-signed_power(rank({f}), 2)",
            f"-signed_power(rank({f}), 3)",
            f"signed_power(rank({f}), 2)",
            f"-rank(abs({f}))",
            f"rank(abs({f}))",
        ]:
            add(e)
    for f in M:
        add(f"-rank({f})")
        add(f"rank({f})")

    # More low-cost cross-sectional variants on pure minute fields.
    # These avoid slow time-series operators while expanding beyond simple enumeration.
    for f in M:
        for e in [
            f"-zscore({f})",
            f"zscore({f})",
            f"-rank(abs(zscore({f})))",
            f"rank(abs(zscore({f})))",
            f"-signed_power(zscore({f}), 2)",
            f"signed_power(zscore({f}), 2)",
            f"-rank(abs(demean({f})))",
            f"rank(abs(demean({f})))",
        ]:
            add(e)

    for i, a in enumerate(M):
        for b in M[i+1:]:
            for e in [
                f"zscore({a}) - zscore({b})",
                f"zscore({b}) - zscore({a})",
                f"-rank(abs(zscore({a}) - zscore({b})))",
                f"rank(abs(zscore({a}) - zscore({b})))",
                f"-signed_power(zscore({a}) - zscore({b}), 2)",
                f"-zscore({a}) * zscore({b})",
                f"zscore({a}) * zscore({b})",
                f"rank(abs({a} - {b}))",
                f"-rank(abs({a} - {b}))",
            ]:
                add(e)

    # Second-layer cross-sectional combinations. These keep computation cheap
    # but express richer economic spreads/confirmations among minute fields.
    for i, a in enumerate(M):
        for b in M[i+1:]:
            for e in [
                f"rank(zscore({a}) + zscore({b}))",
                f"-rank(zscore({a}) + zscore({b}))",
                f"rank(zscore({a}) - zscore({b}))",
                f"-rank(zscore({a}) - zscore({b}))",
                f"rank(zscore({b}) - zscore({a}))",
                f"-rank(zscore({b}) - zscore({a}))",
                f"zscore({a} + {b})",
                f"-zscore({a} + {b})",
                f"zscore({a} - {b})",
                f"-zscore({a} - {b})",
                f"zscore({b} - {a})",
                f"-zscore({b} - {a})",
                f"zscore({a}) * rank({b})",
                f"-zscore({a}) * rank({b})",
                f"zscore({b}) * rank({a})",
                f"-zscore({b}) * rank({a})",
                f"rank({a}) * zscore({b})",
                f"-rank({a}) * zscore({b})",
                f"signed_power(zscore({a}) + zscore({b}), 2)",
                f"-signed_power(zscore({a}) + zscore({b}), 2)",
                f"signed_power(zscore({a}) - zscore({b}), 2)",
                f"-signed_power(zscore({a}) - zscore({b}), 2)",
            ]:
                add(e)

    # Three-leg economic confirmations: flow/liquidity evidence, return impulse,
    # and candlestick shape. This is still pure minute-derived and fast.
    for a in FLOW:
        for b in RETURN:
            for c in SHAPE:
                for e in [
                    f"zscore({a}) * zscore({b}) * zscore({c})",
                    f"-zscore({a}) * zscore({b}) * zscore({c})",
                    f"rank({a}) * zscore({b}) * rank({c})",
                    f"-rank({a}) * zscore({b}) * rank({c})",
                    f"zscore({a}) * rank({b}) * zscore({c})",
                    f"-zscore({a}) * rank({b}) * zscore({c})",
                    f"rank(abs(zscore({a}) + zscore({b}) - zscore({c})))",
                    f"-rank(abs(zscore({a}) + zscore({b}) - zscore({c})))",
                    f"rank(abs(zscore({a}) - zscore({b}) + zscore({c})))",
                    f"-rank(abs(zscore({a}) - zscore({b}) + zscore({c})))",
                    f"signed_power(zscore({a}) - zscore({b}), 2) * zscore({c})",
                    f"-signed_power(zscore({a}) - zscore({b}), 2) * zscore({c})",
                ]:
                    add(e)

    # Smoothing and persistence on minute-derived fields only.
    for f in M:
        for w in [3, 5, 10, 20]:
            add(f"-rank(ts_delta({f}, {w}))")
        for w in [5, 10, 20]:
            add(f"-rank(ts_rank({f}, {w}))")
        for w in [5, 10]:
            add(f"-rank(ts_mean({f}, {w}))")
        add(f"-rank(ts_delay({f}, 1))")
        add(f"-rank(winsorize({f}, 3))")

    # Economically themed pair interactions: flow/shape/return confirmation.
    for a, b in PAIR_THEMES:
        add(f"-rank(ts_corr({a}, {b}, 10))")
        add(f"-rank(ts_corr({a}, {b}, 20))")
        add(f"-rank({a} / (abs({b}) + 1e-10))")
        add(f"rank({b}) - rank({a})")
        add(f"rank({a}) - rank({b})")
        add(f"rank({a}) * rank({b})")
        add(f"-signed_power(rank({a}), 2) * rank({b})")
        add(f"-rank({a}) * signed_power(rank({b}), 2)")

    # Three-leg confirmations using one flow, one return, one shape dimension.
    for a in FLOW:
        for b in RETURN:
            for c in SHAPE:
                add(f"-rank({a}) * rank({b}) * rank({c})")

    # Recent weighted behavior, constrained to minute-derived fields.
    for f in FLOW + RETURN:
        for w in [5, 10]:
            add(f"-rank(ts_decay_linear({f}, {w}))")

    # Broader economic fields from the platform registry, guided by WQ factor families:
    # microstructure, liquidity, volatility risk, reversal/momentum, and cross-modal confirmation.
    if not FAST_ONLY:
        for f in MICRO:
            add(f"-rank({f})")
            add(f"-rank(ts_delta({f}, 5))")
            add(f"-rank(ts_rank({f}, 10))")

    for f in LIQUIDITY:
        add(f"-rank({f})")
        add(f"-rank(ts_delta({f}, 5))")

    for f in VOL_RISK:
        add(f"-rank({f})")
        add(f"-rank(ts_rank({f}, 10))")

    for f in TREND_REV:
        add(f"-rank({f})")
        add(f"rank(ts_rank({f}, 10)) - rank({f})")

    for f in CROSS_MODAL:
        add(f"-rank({f})")
        add(f"-signed_power(rank({f}), 2)")

    for a in ['vwap_gap', 'close_location', 'volume_concentration', 'smart_money_vol',
              'close_vs_vwap', 'amihud_min']:
        for b in ['ret_20d', 'rev_10d', 'vol_20d', 'downside_vol_60d',
                  'volume_trend_20d', 'market_cap_rank']:
            add(f"-rank({a}) * rank({b})")
            add(f"-rank(ts_corr({a}, {b}, 10))")

    for a, b in [
        ('mom_vol_conf', 'volume_price_corr'),
        ('rev_vol_conf', 'downside_vol_60d'),
        ('intraday_ret5d', 'vwap_gap'),
        ('smart_money_rev', 'amihud_20d'),
        ('liquidity_premium', 'market_cap_rank'),
        ('rsi_14', 'bollinger_pos'),
        ('gap_momentum', 'close_location'),
    ]:
        add(f"-rank({a}) + rank({b})")
        add(f"-signed_power(rank({a}), 2) * rank({b})")
    return exprs


def main():
    load_seen()
    exprs = build()
    log(
        f"Pool: {len(exprs)} | Start: {count()}/{TARGET} eligible | "
        f"Seen: {len(_seen)} | fast_only={FAST_ONLY} | diversify={DIVERSIFY_FIELDS}"
    )

    idx = 0; last_cnt = count(); last_ts = time.time()
    while True:
        try:
            n = count()
            if n >= TARGET:
                log(f"DONE: {n}/{TARGET} eligible"); save_seen(); time.sleep(60); continue

            if idx >= len(exprs):
                log("Pool done, rebuilding...")
                save_seen()
                exprs = build(); idx = 0
                log(f"Rebuilt: {len(exprs)}")
                if len(exprs) == 0: time.sleep(300)
                continue

            expr = exprs[idx]; idx += 1
            if in_db(expr): continue

            r = bt(expr, timeout=expr_timeout(expr))
            if r is None:
                global _none_streak
                _none_streak += 1
                if not flask_ok():
                    if api_port_open():
                        log("Flask API slow; port alive, leaving restart to guardian")
                    else:
                        log("Flask DOWN, restarting...")
                        import subprocess
                        subprocess.Popen(['python', 'app.py'], cwd=DIR,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(30)
                else:
                    log(f"bt None streak={_none_streak} | {expr[:80]}")
                    _seen.add(expr.strip())
                    if len(_seen) % 25 == 0:
                        save_seen()
                    if _none_streak >= 3:
                        log("Backtest slow streak; cooling down 180s to avoid piling Flask threads")
                        save_seen()
                        time.sleep(180)
                        _none_streak = 0
                    time.sleep(5)
                continue

            _none_streak = 0
            _seen.add(expr.strip())
            if 'error' in r:
                if len(_seen) % 25 == 0: save_seen()
                continue

            ic = r.get('pearson_ic', 0) or 0
            if abs(ic) <= 0.01:
                if len(_seen) % 25 == 0: save_seen()
                continue

            saved = save(expr, r)
            sh = r.get('sharpe', 0); to = r.get('turnover', 0)
            if saved:
                log(f"+ IC={ic:+.04f} S={sh:.2f} TO={to:.2f} | {expr[:90]}")

            if time.time() - last_ts > 300:
                n = count(); delta = n - last_cnt
                elapsed = (time.time() - _start) / 60
                log(f"=== 5min: {last_cnt}>{n} (+{delta}) | {n}/{TARGET} ({n*100//TARGET}%) | {elapsed:.0f}min ===")
                last_ts = time.time(); last_cnt = n
                save_seen()

            time.sleep(8)
        except Exception as e:
            import traceback
            log(f"CRASH: {e}")
            log(traceback.format_exc()[-300:])
            save_seen()
            time.sleep(10)


if __name__ == '__main__':
    main()
