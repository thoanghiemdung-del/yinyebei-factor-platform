"""Flask backtest platform — login, expression input, metrics dashboard."""
import sys, os, uuid, threading, time, datetime, json, sqlite3, math, subprocess, tempfile
import numpy as np
import requests


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalar and array types."""
    def default(self, obj):
        if isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            v = float(obj)
            return None if math.isnan(v) or math.isinf(v) else v
        if isinstance(obj, (np.integer, np.bool_)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        try:
            return float(obj)
        except (TypeError, ValueError):
            pass
        return super().default(obj)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'model'))
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from data_pipeline import DataPipeline
from backtest_framework import BacktestEngine
from expression_parser import parse_expression, FIELDS_METADATA

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-me')
app.jinja_env.auto_reload = True  # pick up template changes without restart

# USERS supports both username keys (backward compat) and email keys (registration).
# Value is always the password string.
USERS = {'admin': 'quant2026', 'guest': 'backtest'}

# Map email -> display name (set during registration, used for dashboard greeting)
USER_DISPLAY_NAMES = {}

def _is_valid_email(s: str) -> bool:
    """Simple email validation — must contain @ and . with something on each side."""
    s = (s or '').strip()
    return '@' in s and '.' in s and s.rfind('.') > s.find('@') > 0

pipeline = None
engine = None
factor_computer = None

# ---- Task 1: Async backtest task queue ----
_tasks = {}            # task_id -> {status, progress, result, error, created_at}
_tasks_lock = threading.Lock()
_engine_lock = threading.Lock()
_superalpha_lock = threading.Lock()  # prevent concurrent combo computations

# ---- Task 4: Alpha history (legacy in-memory, migrated to SQLite on startup) ----
_alpha_history = []    # list of dicts — only used for one-time migration to SQLite
_alpha_history_lock = threading.Lock()

# ---- Community forum (legacy in-memory, migrated to SQLite on startup) ----
_community_posts = []  # list of dicts — only used for one-time migration to SQLite
_community_posts_lock = threading.Lock()

# ---- SQLite persistence ----
DB_PATH = os.path.join(os.path.dirname(__file__), 'backtest.db')

# ---- Simulation settings (global, reset on restart) ----
_sim_settings = {
    "universe": "csi800",
    "start_date": "2020-01-02",
    "end_date": "2023-12-29",
    "top_pct": 0.1,
    "delay_days": 1,
    "neutralize": "none"
}


def _init_db():
    """Create tables and migrate legacy in-memory data to SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=DELETE')
    conn.execute('''CREATE TABLE IF NOT EXISTS alpha_history (
        id TEXT PRIMARY KEY, name TEXT, expression TEXT,
        timestamp TEXT, type TEXT, metrics_json TEXT,
        pnl_json TEXT, ic_json TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY, password_hash TEXT, created_at TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS community_posts (
        id TEXT PRIMARY KEY, author TEXT, expression TEXT,
        name TEXT, description TEXT, timestamp TEXT, alpha_id TEXT,
        likes INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS post_comments (
        id TEXT PRIMARY KEY, post_id TEXT, author TEXT,
        content TEXT, timestamp TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS post_likes (
        post_id TEXT, user_email TEXT, PRIMARY KEY(post_id, user_email))''')
    # Migrations: add columns that may not exist in older DBs
    for stmt in [
        'ALTER TABLE users ADD COLUMN nickname TEXT',
        'ALTER TABLE community_posts ADD COLUMN alpha_id TEXT',
        'ALTER TABLE community_posts ADD COLUMN likes INTEGER DEFAULT 0',
        'ALTER TABLE alpha_history ADD COLUMN max_corr REAL',
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists
    # Seed default users
    from werkzeug.security import generate_password_hash
    for email, pw in [('admin', 'quant2026'), ('guest', 'backtest')]:
        conn.execute('INSERT OR IGNORE INTO users(email, password_hash) VALUES(?,?)',
                     (email, generate_password_hash(pw)))
    conn.commit()

    # Migration: if DB is empty and in-memory lists have data, migrate them
    alpha_count = conn.execute('SELECT COUNT(*) FROM alpha_history').fetchone()[0]
    if alpha_count == 0:
        with _alpha_history_lock:
            if _alpha_history:
                for rec in _alpha_history:
                    conn.execute(
                        'INSERT OR IGNORE INTO alpha_history '
                        '(id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (rec['id'], rec.get('name', rec['expression'][:40]),
                         rec['expression'],
                         rec.get('timestamp', ''), rec.get('type', 'alpha'),
                         json.dumps(rec.get('metrics', {})),
                         json.dumps(rec.get('pnl_series', [])),
                         json.dumps(rec.get('ic_series', [])))
                    )
                conn.commit()
                _alpha_history.clear()

    posts_count = conn.execute('SELECT COUNT(*) FROM community_posts').fetchone()[0]
    if posts_count == 0:
        with _community_posts_lock:
            if _community_posts:
                for post in _community_posts:
                    conn.execute(
                        'INSERT OR IGNORE INTO community_posts '
                        '(id, author, expression, name, description, timestamp) '
                        'VALUES (?, ?, ?, ?, ?, ?)',
                        (post['id'], post.get('author', ''),
                         post.get('expression', ''),
                         post.get('name', post.get('expression', '')[:40]),
                         post.get('description', ''),
                         post.get('timestamp', ''))
                    )
                conn.commit()
                _community_posts.clear()

    conn.close()


def _row_to_record(row, include_pnl=False):
    """Convert a sqlite3.Row to the legacy dict format with parsed JSON fields.
    Skip records with |IC| <= 0.01 (final safety net)."""
    rec = dict(row)
    # Parse metrics, replacing NaN with None
    try:
        import re
        raw = rec.pop('metrics_json')
        raw = re.sub(r'\bNaN\b', 'null', raw)
        rec['metrics'] = json.loads(raw)
    except Exception:
        rec['metrics'] = {}
    # Safety net: skip low-IS_IC records. Prefer IS to avoid OOS leakage at display level.
    ic = rec['metrics'].get('is_pearson_ic', rec['metrics'].get('pearson_ic'))
    if ic is not None and isinstance(ic, (int, float)) and abs(ic) <= 0.01:
        return None
    if include_pnl:
        try:
            raw = rec.pop('pnl_json'); raw = re.sub(r'\bNaN\b', 'null', raw)
            rec['pnl_series'] = json.loads(raw)
        except Exception: rec['pnl_series'] = []
        try:
            raw = rec.pop('ic_json'); raw = re.sub(r'\bNaN\b', 'null', raw)
            rec['ic_series'] = json.loads(raw)
        except Exception: rec['ic_series'] = []
    else:
        rec.pop('pnl_json', None)
        rec.pop('ic_json', None)
    return rec


# Initialize DB at module load time
_init_db()


def _cleanup_old_tasks():
    """Remove tasks older than 1 hour."""
    while True:
        time.sleep(300)  # every 5 minutes
        now = time.time()
        with _tasks_lock:
            expired = [tid for tid, t in _tasks.items()
                       if now - t.get('created_at', now) > 3600]
            for tid in expired:
                del _tasks[tid]


# Start cleanup daemon thread
_cleanup_thread = threading.Thread(target=_cleanup_old_tasks, daemon=True)
_cleanup_thread.start()


def _to_json_safe(obj):
    """Recursively convert numpy types to Python native types for JSON serialization."""
    import numpy as np, math
    if isinstance(obj, (np.integer, np.bool_)): return int(obj)
    if isinstance(obj, (np.floating,)): v=float(obj); return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, float): return None if math.isnan(obj) or math.isinf(obj) else obj
    if isinstance(obj, np.ndarray): return obj.tolist()
    if isinstance(obj, dict): return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_to_json_safe(v) for v in obj]
    try:
        return float(obj)
    except (TypeError, ValueError):
        pass
    return obj


def _safe_float(value):
    try:
        if value is None:
            return None
        v = float(value)
        return v if math.isfinite(v) else None
    except Exception:
        return None


_ECONOMIC_GROUPS = [
    ('momentum', '动量', [
        'momentum', 'mom_', 'trend', 'breakout', 'ret_20', 'ret_60', 'ret_120',
        'cumret', 'ts_delta', 'slope', 'accel', 'relative_strength', 'new_high',
        'ma_gap', 'ema', 'macd', 'price_strength'
    ]),
    ('reversal', '反转', [
        'reversal', 'rev_', 'mean_reversion', 'overreaction', 'gap', 'overnight',
        'rsi', 'stoch', '-rank(returns', '-returns', '-ret_', 'close_position',
        'close_location', 'short_term_reversal'
    ]),
    ('volatility', '波动率', [
        'volatility', 'realized_vol', 'downside', 'std', 'atr', 'range',
        'high_low', 'skew', 'kurt', 'drawdown', 'max_dd', 'max_drawdown',
        'beta', 'risk', 'entropy', 'dispersion', 'boll'
    ]),
    ('liquidity', '流动性', [
        'turnover', 'volume', 'amount', 'dollar', 'liquidity', 'amihud', 'adv',
        'money_flow', 'flow', 'trade_count', 'volume_profile'
    ]),
    ('microstructure', '微观结构', [
        'minute', 'intraday', 'auction', 'vwap', 'open_', 'close_', 'high_',
        'low_', 'shadow', 'wick', 'body', 'kline', 'bar_', 'smart_money',
        'imbalance', 'impact'
    ]),
    ('size', '规模', [
        'market_cap', 'mcap', 'float_cap', 'size', 'ln_cap', 'log_cap'
    ]),
    ('fundamental', '基本面', [
        'roe', 'roa', 'profit', 'margin', 'debt', 'asset', 'liability', 'book',
        'eps', 'sales', 'revenue', 'cash', 'earning', 'earnings', 'growth',
        'pe', 'pb', 'bp', 'value'
    ]),
    ('sentiment', '情绪/分析师', [
        'news', 'sentiment', 'social', 'analyst', 'revision', 'rating',
        'recommend', 'estimate', 'forecast'
    ]),
]


def _economic_group(expression, alpha_type='alpha'):
    """Conservatively label single alphas by economic meaning.

    Clear mixed signals are marked as mixed/excluded so they do not silently enter
    group-based research filters.
    """
    expr = (expression or '').lower()
    typ = (alpha_type or 'alpha').lower()
    if typ == 'superalpha' or expr.startswith('lgb(') or expr.startswith('superalpha('):
        return {
            'group': '组合',
            'group_key': 'combo',
            'group_excluded': False,
            'group_reason': '组合因子',
        }

    scores = []
    for key, label, terms in _ECONOMIC_GROUPS:
        hits = []
        for term in terms:
            if term in expr:
                hits.append(term)
        if hits:
            scores.append((len(set(hits)), key, label, sorted(set(hits))[:5]))

    if not scores:
        return {
            'group': '未分组',
            'group_key': 'unknown',
            'group_excluded': True,
            'group_reason': '未识别出单一稳定经济含义',
        }

    scores.sort(reverse=True)
    top_score, top_key, top_label, top_hits = scores[0]
    secondary = [x for x in scores[1:] if x[0] > 0]
    if secondary:
        second_score, second_key, second_label, second_hits = secondary[0]
        if second_score >= max(1, top_score - 1):
            labels = [top_label, second_label]
            return {
                'group': '混合/剔除',
                'group_key': 'mixed',
                'group_excluded': True,
                'group_reason': ' + '.join(labels) + ' 信号混合',
            }

    return {
        'group': top_label,
        'group_key': top_key,
        'group_excluded': False,
        'group_reason': '命中: ' + ', '.join(top_hits),
    }


def _history_metric_value(rec, metric):
    metric = (metric or 'abs_ic').lower()
    m = rec.get('metrics') or {}
    aliases = {
        'annual': 'annual_excess',
        'annual_return': 'annual_excess',
        'returns': 'annual_excess',
        'excess': 'annual_excess',
        'maxdd': 'max_drawdown',
        'drawdown': 'max_drawdown',
        'corr': 'max_corr',
        'maxcorr': 'max_corr',
    }
    metric = aliases.get(metric, metric)
    # Prefer IS metrics (no OOS leakage for screening)
    pref = m.get('is_' + metric)
    if pref is not None:
        pref_float = _safe_float(pref)
        if pref_float is not None:
            if metric == 'abs_ic':
                return abs(pref_float)
            if metric == 'max_drawdown':
                return abs(pref_float)
            return pref_float
    if metric == 'abs_ic':
        v = _safe_float(m.get('pearson_ic'))
        return abs(v) if v is not None else None
    if metric == 'ic':
        return _safe_float(m.get('is_pearson_ic', m.get('pearson_ic')))
    if metric == 'annual_excess':
        return (_safe_float(m.get('is_annual_excess')) or
                _safe_float(m.get('annual_excess')) or
                _safe_float(m.get('annual_return')) or
                _safe_float(m.get('returns')))
    if metric == 'max_drawdown':
        v = _safe_float(m.get('is_max_drawdown', m.get('max_drawdown')))
        return abs(v) if v is not None else None
    if metric == 'max_corr':
        v = _safe_float(rec.get('max_corr'))
        if v is not None and v > 0:
            return v
        v = _safe_float(m.get('max_corr'))
        return v if v is not None and v > 0 else None
    if metric == 'timestamp':
        try:
            return datetime.datetime.fromisoformat((rec.get('timestamp') or '').replace('Z', '')).timestamp()
        except Exception:
            return None
    return _safe_float(m.get(metric))


def _strip_balanced_parens(s):
    while s.startswith('(') and s.endswith(')'):
        depth = 0
        balanced = True
        for i, ch in enumerate(s):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0 and i != len(s) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        s = s[1:-1]
    return s


def _signed_expression_key(expression):
    """Return (sign, canonical_expression) for exact sign-flipped expressions."""
    import re
    s = re.sub(r'\s+', '', (expression or '').lower())
    s = _strip_balanced_parens(s)
    sign = 1
    changed = True
    while changed and s:
        changed = False
        s = _strip_balanced_parens(s)
        for prefix in ('-1*', '(-1)*', '-1.0*', '(-1.0)*'):
            if s.startswith(prefix):
                sign *= -1
                s = s[len(prefix):]
                changed = True
                break
        if changed:
            continue
        if s.startswith('-'):
            sign *= -1
            s = s[1:]
            changed = True
            continue
        for suffix in ('*-1', '*(-1)', '*-1.0', '*(-1.0)'):
            if s.endswith(suffix):
                sign *= -1
                s = s[:-len(suffix)]
                changed = True
                break
    return sign, _strip_balanced_parens(s)


def _filter_negative_mirror_records(records):
    """When exact opposite expressions both exist, keep the positive-IC side."""
    buckets = {}
    for rec in records:
        if (rec.get('type') or 'alpha') != 'alpha':
            continue
        sign, key = _signed_expression_key(rec.get('expression'))
        if key:
            buckets.setdefault(key, []).append((sign, rec))

    drop_ids = set()
    for items in buckets.values():
        if len({sign for sign, _ in items}) < 2:
            continue
        has_positive_side = any((_history_metric_value(rec, 'ic') or 0) > 0 for _, rec in items)
        if not has_positive_side:
            continue
        for _, rec in items:
            if (_history_metric_value(rec, 'ic') or 0) < 0:
                drop_ids.add(rec.get('id'))

    if not drop_ids:
        return records, 0
    return [rec for rec in records if rec.get('id') not in drop_ids], len(drop_ids)


def _finite_pnl_array(values):
    try:
        arr = np.array([np.nan if v is None else float(v) for v in (values or [])], dtype=float)
    except Exception:
        return np.array([], dtype=float)
    return arr[np.isfinite(arr)]


def _daily_returns_from_cum_pct(values):
    """Stored PnL is cumulative percent; return daily fractional returns."""
    arr = _finite_pnl_array(values)
    if len(arr) < 2:
        return np.array([], dtype=float)
    daily_pct = np.diff(np.concatenate(([0.0], arr)))
    return daily_pct / 100.0


def _max_drawdown_from_cum_pct(values):
    arr = _finite_pnl_array(values)
    if len(arr) < 2:
        return None
    peak = 0.0
    max_dd_pct = 0.0
    for v in arr:
        if v > peak:
            peak = float(v)
        max_dd_pct = max(max_dd_pct, peak - float(v))
    return max_dd_pct / 100.0


def _normalize_history_metrics(rec):
    """Repair legacy/miner rows whose metrics_json lacks annual return/drawdown."""
    metrics = rec.setdefault('metrics', {}) or {}
    daily = _daily_returns_from_cum_pct(rec.get('pnl_series', []))
    ann = None
    if len(daily) >= 2:
        ann = float(np.nanmean(daily) * 250)
    if ann is None:
        ann = (_safe_float(metrics.get('annual_excess')) or
               _safe_float(metrics.get('annual_return')) or
               _safe_float(metrics.get('returns')))
    if ann is not None:
        ann = round(float(ann), 4)
        metrics['annual_excess'] = ann
        metrics['annual_return'] = ann
        metrics['returns'] = ann

    dd = _max_drawdown_from_cum_pct(rec.get('pnl_series', []))
    if dd is None:
        dd = _safe_float(metrics.get('max_drawdown'))
    if dd is not None:
        metrics['max_drawdown'] = round(abs(float(dd)), 4)
    rec['metrics'] = metrics
    return rec


def _history_max_corrs(records):
    """Compute max absolute PnL correlation for history rows in one vectorized pass."""
    ids = []
    daily_rows = []
    for rec in records:
        expr = rec.get('expression') or ''
        typ = rec.get('type') or 'alpha'
        if typ == 'superalpha' or expr.startswith('lgb(') or expr.startswith('superalpha('):
            continue
        daily = _daily_returns_from_cum_pct(rec.get('pnl_series', []))
        if len(daily) >= 30:
            ids.append(rec.get('id'))
            daily_rows.append(daily)
    if len(daily_rows) < 2:
        return {}

    min_len = min(len(x) for x in daily_rows)
    if min_len < 30:
        return {}
    x = np.vstack([row[-min_len:] for row in daily_rows]).astype(float)
    finite = np.isfinite(x)
    counts = finite.sum(axis=1)
    valid = counts >= 30
    if valid.sum() < 2:
        return {}
    x = x[valid]
    finite = finite[valid]
    kept_ids = [ids[i] for i, ok in enumerate(valid) if ok]
    sums = np.where(finite, x, 0.0).sum(axis=1)
    means = sums / finite.sum(axis=1)
    centered = np.where(finite, x - means[:, None], 0.0)
    norms = np.sqrt((centered * centered).sum(axis=1))
    ok = norms > 1e-12
    if ok.sum() < 2:
        return {}
    centered = centered[ok]
    norms = norms[ok]
    kept_ids = [kept_ids[i] for i, keep in enumerate(ok) if keep]
    corr = centered @ centered.T / (norms[:, None] * norms[None, :])
    corr = np.nan_to_num(np.abs(corr), nan=0.0, posinf=0.0, neginf=0.0)
    np.fill_diagonal(corr, 0.0)
    return {aid: round(float(corr[i].max()), 4) for i, aid in enumerate(kept_ids)}


def _abs_corr_aligned(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return None
    x = np.asarray(a[-n:], dtype=float)
    y = np.asarray(b[-n:], dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < 30:
        return None
    x = x[mask]
    y = y[mask]
    if np.nanstd(x) <= 1e-12 or np.nanstd(y) <= 1e-12:
        return None
    c = float(np.corrcoef(x, y)[0, 1])
    return abs(c) if math.isfinite(c) else None


def get_engine():
    global pipeline, engine, factor_computer
    if pipeline is None:
        with _engine_lock:
            if pipeline is None:  # double-checked locking
                pipeline = DataPipeline()
                engine = BacktestEngine(pipeline)
                from factor_library import FactorComputer
                factor_computer = FactorComputer(pipeline)
                print('[Init] DataPipeline + BacktestEngine + FactorComputer ready.')
    return pipeline, engine, factor_computer


def _load_cached_lgb(expr):
    """Look up cached LGB prediction matrix by expression string.
    If cache is missing (from older LGB runs), recompute on-the-fly."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute('SELECT id FROM alpha_history WHERE expression=?', (expr,)).fetchone()
    conn.close()
    if not row:
        raise ValueError('LGB结果未在历史记录中找到，请先运行LGB组合')
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', f'lgb_{row[0]}.npy')
    if not os.path.exists(cache_path):
        # Backfill: re-run LGB training to generate cache
        print(f'[Cache] Backfilling LGB cache for {row[0][:12]}...', flush=True)
        try:
            # Parse expression to extract base expressions
            inner = expr[expr.index(';') + 1:].strip().rstrip(')')
            base_exprs = [e.strip() for e in inner.split(', ') if e.strip()]
            if base_exprs:
                data = {'expressions': base_exprs, 'n_estimators': 80, 'max_train_samples': 500000,
                        'max_lgb_features': 300, 'train_matrix_budget_mb': 128,
                        'predict_matrix_budget_mb': 8, 'sub_alpha_limit': 8,
                        'oos_cache_feature_limit': 60, 'purge_days': 5}
                _do_lgb_training(data)  # This saves the cache via history_id
        except Exception as e:
            print(f'[Cache] Backfill failed: {e}', flush=True)
    if not os.path.exists(cache_path):
        raise ValueError('LGB缓存生成失败，请重新运行该LGB组合')
    pred = np.load(cache_path)
    pipeline, engine, fc = get_engine()
    # Find first trading day of 2023 (Jan 1 is a holiday)
    date_keys = sorted(pipeline.date_to_idx.keys())
    oos_start = None
    for d in date_keys:
        if d >= '2023-01-01':
            oos_start = pipeline.date_to_idx[d]
            break
    if oos_start is None:
        raise ValueError('No trading data after 2023-01-01')
    full = np.full((pipeline.n_dates, pipeline.n_stocks), np.nan, dtype=np.float32)
    full[oos_start:oos_start + pred.shape[0]] = pred
    return full


def release_engine_cache():
    """Drop large data/factor caches after heavy background jobs."""
    global pipeline, engine, factor_computer
    pipeline = None
    engine = None
    factor_computer = None
    try:
        import expression_parser as ep
        if hasattr(ep, '_derived_cache'):
            ep._derived_cache.clear()
        if hasattr(ep, '_minute_batch_cache'):
            ep._minute_batch_cache = None
    except Exception:
        pass
    try:
        import gc
        gc.collect()
    except Exception:
        pass



def _add_to_history(expression: str, metrics: dict, alpha_type: str = 'alpha', name: str = None):
    """Persist a backtest result to SQLite alpha history."""
    # All factors saved - filtering done at query level via IS_IC
    _internal_keys = {'_factor_array', '_direction', 'ic_series', 'pnl_series'}
    if name is None:
        name = expression[:40] + ('...' if len(expression) > 40 else '')

    entry_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    metrics_json = json.dumps({k: v for k, v in metrics.items() if k not in _internal_keys})
    pnl_json = json.dumps(metrics.get('pnl_series', []))
    ic_json = json.dumps(metrics.get('ic_series', []))

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO alpha_history (id, name, expression, timestamp, type, '
        'metrics_json, pnl_json, ic_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (entry_id, name, expression, timestamp, alpha_type, metrics_json, pnl_json, ic_json)
    )
    conn.commit()
    conn.close()
    return entry_id



def _resolve_display_name(email_or_name: str) -> str:
    """Look up nickname from users table; fall back to email prefix if no nickname."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute('SELECT nickname FROM users WHERE email=?', (email_or_name,)).fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    if '@' in (email_or_name or ''):
        return email_or_name.split('@')[0]
    return email_or_name or '匿名'


def _build_post_dict(row: dict, include_author_raw: bool = False) -> dict:
    """Convert a community_posts row (possibly with JOINed alpha columns) into a response dict.

    Handles alpha_ref construction from joined alpha_history columns.
    Looks up display nickname for author if stored as email.
    """
    post = dict(row)
    # Build alpha_ref from joined alpha_history data
    alpha_id = post.get('alpha_id')
    alpha_expr = post.pop('ref_expr', None)
    alpha_metrics_raw = post.pop('ref_metrics', None)
    if alpha_id and alpha_expr:
        metrics = {}
        if alpha_metrics_raw:
            try:
                metrics = json.loads(alpha_metrics_raw) if isinstance(alpha_metrics_raw, str) else alpha_metrics_raw
            except Exception:
                pass
        ref_pnl_raw = post.pop('ref_pnl', None)
        pnl_series = []
        if ref_pnl_raw:
            try:
                pnl_series = json.loads(ref_pnl_raw) if isinstance(ref_pnl_raw, str) else ref_pnl_raw
            except Exception: pass
        post['alpha_ref'] = {
            'expression': alpha_expr,
            'metrics': {k: metrics.get(k) for k in
                        ('pearson_ic', 'annual_excess', 'sharpe', 'fitness', 'turnover', 'max_drawdown')},
            'pnl_series': pnl_series,
        }
    # Resolve display name
    raw_author = post.get('author', '')
    post['author_display'] = _resolve_display_name(raw_author)
    return post

# ======================== ROUTES ========================

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        from werkzeug.security import check_password_hash
        # Check SQLite users table first
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute('SELECT password_hash FROM users WHERE email=?', (username,)).fetchone()
        conn.close()
        if row and check_password_hash(row[0], password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='用户名/邮箱或密码错误')
    return render_template('login.html', error=None)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        from werkzeug.security import generate_password_hash

        if not _is_valid_email(email):
            return render_template('login.html', error='邮箱格式不正确', mode='register')
        conn = sqlite3.connect(DB_PATH)
        existing = conn.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone()
        conn.close()
        if existing:
            return render_template('login.html', error='该邮箱已注册', mode='register')
        if len(password) < 6:
            return render_template('login.html', error='密码至少6位', mode='register')
        if password != confirm:
            return render_template('login.html', error='两次密码不一致', mode='register')

        nickname = request.form.get('nickname', '').strip()

        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO users(email,password_hash,created_at,nickname) VALUES(?,?,?,?)',
                     (email, generate_password_hash(password), datetime.datetime.now().isoformat(), nickname or None))
        conn.commit()
        conn.close()
        session['user'] = email
        return redirect(url_for('dashboard'))

    return render_template('login.html', error=None, mode='register')


@app.route('/dashboard_v2')
def dashboard_v2():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard_v2.html')
    
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    raw_user = session['user']
    display_name = _resolve_display_name(raw_user)
    return render_template('dashboard.html', username=display_name)


@app.route('/alpha_history')
def alpha_history_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('alpha_history.html')


@app.route('/data_fields')
def data_fields_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('data_fields.html')


@app.route('/operators')
def operators_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('operators.html')


@app.route('/correlation')
def correlation_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('correlation.html')


@app.route('/compare')
def compare_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('compare.html')


# ---- Settings endpoints ----

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    """Return current simulation settings."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    return jsonify(_sim_settings)


@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    """Update simulation settings."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': '请求体为空'}), 400
    for key in ('start_date', 'end_date', 'top_pct', 'delay_days', 'neutralize'):
        if key in data:
            _sim_settings[key] = data[key]
    return jsonify({'success': True, 'settings': _sim_settings})


# ---- Task 1: Async backtest (start + status) ----

@app.route('/api/debug/minute', methods=['GET'])
def api_debug_minute():
    """Debug endpoint: verify minute-derived field computation."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    import expression_parser as ep
    import numpy as np
    pipeline, engine, fc = get_engine()
    r = ep._compute_all_minute_derived(pipeline)
    cl = r['close_location']
    n_valid = np.isfinite(cl).sum()
    t0 = pipeline.date_to_idx['2020-01-02']
    t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
    cl_train = cl[t0:t1]
    valid_days = sum(1 for t in range(cl_train.shape[0]) if np.isfinite(cl_train[t]).sum() >= 100)
    return jsonify({
        'file': ep.__file__,
        'total_valid_cells': int(n_valid),
        'valid_days_2020_2023': valid_days,
        'total_days_2020_2023': t1 - t0,
        'cached': ep._minute_batch_cache is not None,
    })


@app.route('/api/backtest', methods=['POST'])
def api_backtest_legacy():
    """Synchronous backtest — runs in subprocess to guarantee memory release."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    expression = data.get('expression', '')
    if not expression:
        return jsonify({'error': '表达式不能为空'}), 400

    try:
        result = _run_compute_subprocess('backtest', data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'回测失败: {str(e)}'}), 500


def _run_compute_subprocess(kind, data):
    """Run a computation in a subprocess — guarantees memory release on exit."""
    task_id = str(uuid.uuid4())
    task_file = os.path.join(tempfile.gettempdir(), f'task_{task_id}.json')
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump({'task_id': task_id, 'kind': kind, 'data': data}, f, cls=_NumpyEncoder)
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'compute_worker.py')
    proc = subprocess.Popen([sys.executable, worker, task_file],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Poll for result (timeout depends on computation type)
    timeout = 600 if kind == 'superalpha' else 120
    result_file = task_file.replace('.json', '_result.json')
    try:
        for _ in range(timeout):
            time.sleep(1)
            if os.path.exists(result_file):
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        r = json.load(f)
                    if r.get('status') == 'done':
                        return r.get('result', {})
                    elif r.get('status') == 'error':
                        raise RuntimeError(r.get('error', '未知错误'))
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
        raise TimeoutError('计算超时（2分钟）')
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


@app.route('/api/backtest/start', methods=['POST'])
def api_backtest_start():
    """Start an async backtest. Returns {task_id} immediately.

    Accepts optional 'neutralize' field in JSON body:
      - "none" (default): no neutralization
      - "market_cap": cross-sectional market cap neutralization
    """
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    expression = data.get('expression', '')
    if not expression:
        return jsonify({'error': '表达式不能为空'}), 400

    neutralize = data.get('neutralize', 'none')
    if neutralize not in ('none', 'market_cap'):
        return jsonify({'error': f'不支持的中性化方式: {neutralize}'}), 400

    start_date = data.get('start_date')
    end_date = data.get('end_date')
    top_pct = data.get('top_pct')

    task_id = _start_backtest_task(expression, neutralize, start_date, end_date, top_pct)
    return jsonify({'task_id': task_id, 'neutralize': neutralize})


@app.route('/api/backtest/status/<task_id>', methods=['GET'])
def api_backtest_status(task_id):
    """Poll backtest status. Returns {status, progress, result, error}."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    with _tasks_lock:
        task = _tasks.get(task_id)

    if task is None:
        return jsonify({'error': '任务不存在或已过期'}), 404

    # For subprocess LGB tasks, check the result file
    if task.get('kind') == 'lgb_superalpha' and task.get('task_file'):
        result_file = task['task_file'].replace('.json', '_result.json')
        if os.path.exists(result_file):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    r = json.load(f)
                task['status'] = r.get('status', task['status'])
                task['progress'] = r.get('progress', task['progress'])
                if r.get('status') == 'done':
                    task['result'] = r.get('result')
                elif r.get('status') == 'error':
                    task['error'] = r.get('error')
            except Exception:
                pass

    resp = {
        'task_id': task_id,
        'status': task['status'],
        'progress': task['progress'],
    }
    if task['status'] == 'done':
        resp['result'] = task.get('result')
    elif task['status'] == 'error':
        resp['error'] = task.get('error')
    return jsonify(resp)


@app.route('/api/backtest/cancel/<task_id>', methods=['POST'])
def api_backtest_cancel(task_id):
    """Cancel a running backtest."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task:
            task['status'] = 'error'
            task['error'] = '用户取消'
    return jsonify({'status': 'cancelled'})


def _start_backtest_task(expression: str, neutralize: str = 'none',
                         start_date: str = None, end_date: str = None,
                         top_pct: float = None) -> str:
    """Create a new backtest task and spawn a background thread. Returns task_id."""
    task_id = str(uuid.uuid4())
    with _tasks_lock:
        _tasks[task_id] = {
            'status': 'running',
            'progress': 0,
            'result': None,
            'error': None,
            'created_at': time.time(),
            'neutralize': neutralize,
            'start_date': start_date or _sim_settings['start_date'],
            'end_date': end_date or _sim_settings['end_date'],
            'top_pct': top_pct if top_pct is not None else _sim_settings['top_pct'],
        }

    thread = threading.Thread(
        target=_run_backtest_task, args=(task_id, expression, neutralize), daemon=True
    )
    thread.start()
    return task_id


def _run_backtest_task(task_id: str, expression: str, neutralize: str = 'none'):
    """Background worker that runs the backtest and updates _tasks."""
    try:
        # Progress: parse expression
        _update_task(task_id, 'running', 5)

        pipeline, engine, fc = get_engine()
        _update_task(task_id, 'running', 15)

        # Progress: compute factor + evaluate
        factor = parse_expression(expression, pipeline, fc)
        _update_task(task_id, 'running', 20)

        # Read custom settings from task dict
        with _tasks_lock:
            task_cfg = _tasks.get(task_id, {})
        start_date = task_cfg.get('start_date', '2020-01-02')
        end_date = task_cfg.get('end_date', '2023-12-29')
        top_pct = task_cfg.get('top_pct', 0.1)

        t0 = pipeline.date_to_idx[start_date]
        t1 = min(pipeline.date_to_idx[end_date] + 1, pipeline.n_dates)
        factor_train = factor[t0:t1]
        label_train = pipeline.fields['Label'][t0:t1]
        univ_train = pipeline.universe_mask[t0:t1]

        # ---- Market cap neutralization (WQ-style: subtract group mean) ----
        if neutralize == 'market_cap':
            adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                    pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(factor_train[0]))), 0.01, 100)
            mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES', pipeline.fields.get('I_D_SHARE_LIQA', np.ones_like(factor_train[0])))
            mcap_train = mcap[t0:t1]
            # Bucket stocks into market cap groups per day
            for t in range(factor_train.shape[0]):
                valid = ~np.isnan(factor_train[t]) & ~np.isnan(mcap_train[t])
                if valid.sum() < 100:
                    continue
                # Group by log market cap quantiles (10 groups)
                log_mcap = np.log(np.maximum(mcap_train[t, valid], 1))
                group_ids = np.floor(np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0, 101, 10))) / 10).astype(int)
                fv = factor_train[t, valid].copy()
                for g in np.unique(group_ids):
                    gmask = group_ids == g
                    if gmask.sum() >= 10:
                        fv[gmask] = fv[gmask] - np.nanmean(fv[gmask])
                factor_train[t, valid] = fv

        _update_task(task_id, 'running', 30)

        result = engine.full_evaluation(factor_train, univ_train, label=label_train)
        _update_task(task_id, 'running', 70)

        # Progress: evaluate metrics (80 -> 90)
        metrics = _compute_metrics_from_result(
            factor_train, label_train, univ_train, result, top_pct=top_pct
        )
        _update_task(task_id, 'running', 90)

        # Progress: compute PnL series (90 -> 100)
        # PnL already computed inside _compute_metrics_from_result
        _update_task(task_id, 'running', 95)

        # Finalize: store numpy array at task level (not in JSON result)
        factor_arr = metrics.pop('factor_array', None)
        with _tasks_lock:
            _tasks[task_id]['status'] = 'done'
            _tasks[task_id]['progress'] = 100
            _tasks[task_id]['result'] = _to_json_safe({'success': True, **metrics})
            _tasks[task_id]['_factor_array'] = factor_arr

        # Auto-save to history
        _add_to_history(expression, metrics, 'alpha')

    except Exception as e:
        import traceback
        traceback.print_exc()
        with _tasks_lock:
            _tasks[task_id]['status'] = 'error'
            _tasks[task_id]['progress'] = 0
            _tasks[task_id]['error'] = f'回测失败: {str(e)}'


def _compute_metrics_from_result(factor_train, label_train, univ_train, result, top_pct=0.1):
    """Extract all metrics from a factor evaluation result. Used by both
    async backtest and superalpha."""
    import math
    # Direction: always 1 (high factor value = long). User controls sign via -expression.
    direction = 1

    n_dates = factor_train.shape[0]
    daily_excess = []  # Top10% - Market average (competition long-only excess)
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

    # All metrics based on long-only Top10% excess (competition standard)
    excess_arr = np.array([x for x in daily_excess if x is not None])
    excess_mean = float(np.mean(excess_arr))
    excess_std = float(np.std(excess_arr))
    ann_excess = excess_mean * 250
    wq_sharpe = ann_excess / (excess_std * np.sqrt(250) + 1e-10)

    # Turnover
    turnovers = []
    for t in range(1, len(daily_top_set)):
        prev = daily_top_set[t - 1]
        curr = daily_top_set[t]
        if len(prev) > 0 and len(curr) > 0:
            overlap = len(prev & curr)
            to = 1.0 - overlap / max(len(prev), len(curr))
            turnovers.append(to)
    avg_turnover = float(np.mean(turnovers)) if turnovers else 0.0

    # Fitness: based on excess returns and turnover
    fitness_denom = max(avg_turnover, 0.125)
    wq_fitness = wq_sharpe * np.sqrt(abs(ann_excess) / fitness_denom) if ann_excess != 0 else 0.0

    # Drawdown (based on cumulative excess)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    cum_pnl = []
    for r in daily_excess:
        if r is not None:
            cum += r
            if cum > peak:
                peak = cum
            dd = peak - cum
            if dd > max_dd:
                max_dd = dd
        cum_pnl.append(float(cum * 100))

    wq_margin = float(excess_mean / (np.mean(np.abs(excess_arr)) + 1e-10) * 10000)

    win_rate = float((excess_arr > 0).mean())

    ic_series = result.get('ic_series', np.array([]))
    ic_series_display = [round(float(x), 4) if not np.isnan(x) else None
                         for x in ic_series[-60:]]
    # Clean NaN from pnl_series
    pnl_display = [None if x is None or math.isnan(float(x)) else float(x) for x in cum_pnl]

    # Also store the full factor_train for superalpha combination
    def safe_round(val, ndigits):
        try:
            v = float(val)
            return round(v, ndigits) if not math.isnan(v) and not math.isinf(v) else None
        except Exception: return None

    return {
        'pearson_ic': safe_round(result.get('mean_pearson_ic', 0), 4),
        'icir': safe_round(result.get('icir', 0), 3),
        'ic_positive_ratio': safe_round(result.get('ic_positive_ratio', 0), 3),
        'annual_excess': safe_round(ann_excess, 4),
        'sharpe': safe_round(wq_sharpe, 3),
        'fitness': safe_round(wq_fitness, 3),
        'returns': safe_round(ann_excess, 4),
        'max_drawdown': safe_round(max_dd, 4),
        'turnover': safe_round(avg_turnover, 4),
        'margin_bps': safe_round(wq_margin, 1),
        'win_rate': safe_round(win_rate, 3),
        'n_days': int(result['n_eval_days']) if result.get('n_eval_days') else 0,
        'ic_series': ic_series_display,
        'pnl_series': pnl_display,
        # Internal: not serialized to client but used by superalpha
        '_factor_array': factor_train,
        '_direction': direction,
    }


def _update_task(task_id, status, progress):
    """Thread-safe task progress update."""
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id]['status'] = status
            _tasks[task_id]['progress'] = progress


# ---- Task 2: Updated /api/fields (categorized) ----

@app.route('/api/fields')
def api_fields():
    return jsonify({
        '价格类': ['close', 'open', 'high', 'low', 'preclose'],
        '收益类': ['morning_return', 'afternoon_return', 'first30min_return',
                  'last30min_return', 'body_return', 'auction_return'],
        '成交量类': ['volume', 'amount', 'volume_profile_ratio', 'turnover_rate'],
        '波动类': ['intraday_volatility', 'upper_shadow_pct', 'lower_shadow_pct'],
        '分钟模拟类': ['morning_return', 'afternoon_return', 'first30min_return',
                     'last30min_return', 'body_return', 'upper_shadow_pct',
                     'lower_shadow_pct', 'auction_return',
                     'intraday_volatility'],
        '预计算因子': ['ret_20d', 'ret_60d', 'ret_120d_skip5', 'ret_5d',
                     'sharpe_60d', 'mom_vol_adj', 'max_dd_60d', 'close_vs_high_20d',
                     'rev_1d', 'rev_5d', 'rev_overnight', 'abnormal_vol_rev',
                     'vol_20d', 'vol_60d', 'vol_ratio', 'downside_vol_60d',
                     'skewness_60d', 'turnover_5d', 'amihud_20d', 'log_dollar_vol',
                     'upper_shadow', 'lower_shadow', 'body_ratio', 'gap_up',
                     'vpin', 'rsi_14', 'bollinger_pos', 'beta_60d', 'market_cap_rank'],
        'operators': ['ts_delta(x,d)', 'ts_mean(x,d)', 'ts_std(x,d)', 'ts_rank(x,d)',
                      'ts_max(x,d)', 'ts_min(x,d)', 'ts_sum(x,d)', 'ts_corr(x,y,d)',
                      'rank(x)', 'zscore(x)', 'demean(x)', 'signed_power(x,e)',
                      'group_neutralize(x,group)', 'group_rank(x,group)', 'group_zscore(x,group)',
                      'ts_delay(x,d)', 'ts_decay_linear(x,d)', 'ts_backfill(x)',
                      'ts_regression(y,x,d,lag)'],
    })


# ---- Task 5: /api/datafields (metadata-rich field listing) ----

@app.route('/api/datafields')
def api_datafields():
    """Return all available data fields with metadata, grouped by category."""
    categories_order = ['价格类', '收益类', '量价类', '波动类', '微观结构类',
                        '动量因子', '反转因子', '波动率因子', '量价因子', '形态因子',
                        '微观结构因子', '跨模态因子', '技术指标']
    grouped = {cat: [] for cat in categories_order}

    for field_name, meta in FIELDS_METADATA.items():
        cat = meta['category']
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append({
            'name': field_name,
            'chinese_name': meta.get('chinese_name', field_name),
            'category': meta['category'],
            'description': meta['description'],
            'calculation': meta['calculation'],
        })

    # Remove empty categories
    grouped = {k: v for k, v in grouped.items() if v}
    return jsonify({'categories': grouped})


# ---- Task 3: SuperAlpha ----

@app.route('/api/superalpha', methods=['POST'])
def api_superalpha():
    """Combine multiple alphas via weighted factor average and backtest.

    Accepts TWO input formats:

    Format A (direct expressions):
      {"expressions": ["expr1", "expr2", ...], "weights": [0.5, 0.5, ...],
       "neutralize": "none"|"market_cap"}

    Format B (alpha_ids from history):
      {"alpha_ids": ["id1", "id2", ...], "neutralize": "none"|"market_cap"}
      Looks up expressions from alpha_history, re-parses each, uses equal weight.
    """
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    # Check if this will use inline path (fast, no lock needed)
    # Only subprocess path needs the lock for memory safety
    data_preview = request.get_json() or {}
    expressions_count = len(data_preview.get('expressions', data_preview.get('alpha_ids', [])))
    needs_subprocess = expressions_count > 10 or any(
        (e or '').startswith('superalpha') or (e or '').startswith('lgb')
        for e in data_preview.get('expressions', []))

    if needs_subprocess:
        if not _superalpha_lock.acquire(blocking=False):
            return jsonify({'error': '服务器正在处理另一个组合计算，请稍后重试（通常需要30-60秒）'}), 503
        try:
            return _api_superalpha_impl()
        finally:
            _superalpha_lock.release()
    else:
        return _api_superalpha_impl()


def _neutralize_combo_matrix(combined, pipeline, fc, t0, t1, neutralize):
    """Apply cross-sectional neutralization to an OOS combo matrix in place."""
    if neutralize == 'none':
        return combined

    valid_modes = {'market_cap', 'market_cap_regression', 'beta', 'market_cap_beta'}
    if neutralize not in valid_modes:
        raise ValueError(f'unsupported combo neutralization: {neutralize}')

    adjf = np.clip(
        np.where(
            np.isnan(pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(combined[0]))),
            1.0,
            pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(combined[0])),
        ),
        0.01,
        100,
    )
    mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get(
        'I_D_TOTAL_SHARES', pipeline.fields.get('I_D_SHARE_LIQA', np.ones_like(combined[0]))
    )
    mcap_train = np.asarray(mcap[t0:t1], dtype=np.float64)

    if neutralize == 'market_cap':
        for tt in range(combined.shape[0]):
            vld = ~np.isnan(combined[tt]) & ~np.isnan(mcap_train[tt]) & (mcap_train[tt] > 0)
            if vld.sum() < 100:
                continue
            log_mcap = np.log(np.maximum(mcap_train[tt, vld], 1))
            gids = np.floor(
                np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0, 101, 10))) / 10
            ).astype(int)
            cv = combined[tt, vld].copy()
            for g in np.unique(gids):
                gm = gids == g
                if gm.sum() >= 10:
                    cv[gm] = cv[gm] - np.nanmean(cv[gm])
            combined[tt, vld] = cv
        return combined

    beta_train = None
    if neutralize in {'beta', 'market_cap_beta'}:
        beta_arr = parse_expression('beta_60d', pipeline, fc)
        beta_train = np.asarray(beta_arr[t0:t1], dtype=np.float64)
        del beta_arr

    for tt in range(combined.shape[0]):
        y = combined[tt]
        regressors = []
        if neutralize in {'market_cap_regression', 'market_cap_beta'}:
            regressors.append(np.log(np.maximum(mcap_train[tt], 1)))
        if neutralize in {'beta', 'market_cap_beta'}:
            regressors.append(beta_train[tt])
        vld = np.isfinite(y)
        for x in regressors:
            vld &= np.isfinite(x)
        if vld.sum() < 100:
            continue
        xmat = np.column_stack([np.ones(vld.sum())] + [x[vld] for x in regressors])
        coef, *_ = np.linalg.lstsq(xmat, y[vld], rcond=None)
        combined[tt, vld] = y[vld] - xmat @ coef
    return combined


def _compute_superalpha_inline(expressions, weights, neutralize, sub_alpha_limit, method,
                               cached_expr_map=None, lineage_labels=None):
    """Compute superalpha inline — fast path for ≤10 factors, no subprocess overhead."""
    pipeline, engine, fc = get_engine()

    # OOS period only
    date_keys = sorted(pipeline.date_to_idx.keys())
    t0 = None
    for d in date_keys:
        if d >= '2023-01-01':
            t0 = pipeline.date_to_idx[d]
            break
    t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
    label = pipeline.fields['Label'][t0:t1]
    univ = pipeline.universe_mask[t0:t1]

    n_dates, n_stocks = label.shape
    combined = np.zeros((n_dates, n_stocks), dtype=np.float32)
    weight_sum = np.zeros((n_dates, n_stocks), dtype=np.float32)
    sub_results = []
    valid_count = 0
    limit = min(sub_alpha_limit or len(expressions), len(expressions), 100)

    for i, expr in enumerate(expressions):
        try:
            if expr == '__cached__':
                # Load cached matrix directly
                cache_key = str(i)
                if isinstance(cached_expr_map, dict) and cache_key in cached_expr_map:
                    cache_path = cached_expr_map[cache_key]
                    cached_matrix = np.load(cache_path)
                    # Cached matrix is already OOS-only — use as-is
                    f_train = np.asarray(cached_matrix, dtype=np.float32)
                    del cached_matrix
                else:
                    continue
            else:
                factor = parse_expression(expr, pipeline, fc)
                f_train = np.asarray(factor[t0:t1], dtype=np.float32)
                del factor
            f_mean = np.nanmean(f_train, axis=1, keepdims=True)
            f_std = np.nanstd(f_train, axis=1, keepdims=True) + 1e-10
            fz = (f_train - f_mean) / f_std
            valid = np.isfinite(fz)
            if not np.any(valid):
                continue
            w = float(weights[i])
            combined[valid] += w * fz[valid]
            weight_sum[valid] += w
            valid_count += 1
            if len(sub_results) < limit:
                result = engine.full_evaluation(f_train, univ, label=label)
                metrics = _compute_metrics_from_result(f_train, label, univ, result)
                sub_results.append({
                    'expression': expr, 'weight': round(w, 4),
                    'metrics': {k: v for k, v in metrics.items() if k not in ('_factor_array', '_direction', 'ic_series', 'pnl_series')},
                })
            del f_train, fz, valid, f_mean, f_std
        except Exception:
            continue

    valid_weight = np.isfinite(weight_sum) & (np.abs(weight_sum) > 1e-12)
    if valid_count < 1 or not np.any(valid_weight):
        return {'success': False, 'error': 'no valid factors'}

    combined[valid_weight] = combined[valid_weight] / weight_sum[valid_weight]
    combined[~valid_weight] = np.nan
    del weight_sum

    combined = _neutralize_combo_matrix(combined, pipeline, fc, t0, t1, neutralize)

    cr = engine.full_evaluation(combined, univ, label=label)
    cm = _compute_metrics_from_result(combined, label, univ, cr)
    cm['_neutralize'] = neutralize
    cm_clean = {k: v for k, v in cm.items() if k not in ('_factor_array', '_direction')}

    # Build expression + save to history
    expr_strs = lineage_labels if lineage_labels and len(lineage_labels) == len(expressions) else expressions
    if method == 'equal':
        combo_expr = 'superalpha(' + ' + '.join(expr_strs) + ')'
    else:
        weighted = [f'{round(w, 4)}*{e}' for w, e in zip(weights, expr_strs)]
        combo_expr = f'superalpha[{method}](' + ' + '.join(weighted) + ')'

    hid = _add_to_history(combo_expr, cm, 'superalpha')

    # Cache combined matrix
    if hid:
        try:
            os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache'), exist_ok=True)
            cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', f'ew_{hid}.npy')
            np.save(cache_path, combined)
        except Exception:
            pass

    del combined
    import gc as _gc; _gc.collect()

    return {
        'success': True, 'type': 'superalpha',
        'n_requested_factors': len(expressions), 'n_valid_factors': valid_count,
        'n_skipped_features': 0, 'skipped_features': [],
        'sub_alphas_truncated': max(0, valid_count - len(sub_results)),
        'combined_metrics': cm_clean, 'sub_alphas': sub_results,
    }


def _api_superalpha_impl():
    data = request.get_json()
    neutralize = data.get('neutralize', 'none')

    # ---- Determine input format ----
    direct_expressions = data.get('expressions', None)
    alpha_ids = data.get('alpha_ids', [])

    if direct_expressions is not None:
        cached_expr_map = {}
        # Format A: direct expressions with optional weights
        expressions = [e.strip() for e in direct_expressions if (e or '').strip()]
        lineage_labels = list(expressions)
        weights_in = data.get('weights', None)

        if len(expressions) < 1:
            return jsonify({'error': '至少需要1个表达式'}), 400
        # No upper limit; estimate time: ~2s per expression
        est_seconds = len(expressions) * 2.0

        if weights_in is None:
            weights = [1.0 / len(expressions)] * len(expressions)
        else:
            if len(weights_in) != len(expressions):
                return jsonify({'error': 'weights长度必须与expressions一致'}), 400
            w_sum = sum(weights_in)
            if w_sum <= 0:
                return jsonify({'error': '权重之和必须大于0'}), 400
            weights = [w / w_sum for w in weights_in]

        # Use sequential IDs for sub-alpha entries
        alpha_ids_for_subs = ['direct_' + str(i) for i in range(len(expressions))]

    elif alpha_ids and len(alpha_ids) >= 1:
        lineage_labels = []
        weights_in = data.get('weights', None)
        if weights_in is not None:
            if len(weights_in) != len(alpha_ids):
                return jsonify({'error': 'weights length must match alpha_ids'}), 400
            try:
                source_weights = [float(weight) for weight in weights_in]
            except (TypeError, ValueError):
                return jsonify({'error': 'weights must be numeric'}), 400
            if sum(source_weights) <= 0:
                return jsonify({'error': 'weights sum must be positive'}), 400
        else:
            source_weights = [1.0] * len(alpha_ids)
        cached_expr_map = {}  # index→cache_path for matrix-cached entries
        # Format B: look up from history, equal weight
        # No upper limit; estimate time: ~2s per alpha
        est_seconds = len(alpha_ids) * 2.0

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        placeholders = ','.join(['?' for _ in alpha_ids])
        rows = conn.execute(
            f'SELECT id, expression FROM alpha_history WHERE id IN ({placeholders})',
            alpha_ids
        ).fetchall()
        conn.close()

        id_to_expr = {row['id']: row['expression'] for row in rows}

        expressions = []
        alpha_ids_for_subs = []
        weights = []
        # Map index→cache_path for matrix-cached entries (LGB + superalpha)
        # Populated alongside expressions list, passed to worker
        for aid, source_weight in zip(alpha_ids, source_weights):
            expr = id_to_expr.get(aid)
            if not expr:
                return jsonify({'error': f'Alpha ID {aid} 不存在于历史记录中'}), 404
            if expr.startswith('lgb('):
                # LGB: load cached prediction matrix if available
                cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', f'lgb_{aid}.npy')
                if os.path.exists(cache_path):
                    idx = len(expressions)
                    cached_expr_map[str(idx)] = cache_path
                    expressions.append('__cached__')
                    lineage_labels.append(f'lgb_ref({aid})')
                    weights.append(source_weight)
                    continue
                else:
                    return jsonify({'error': f'LGB缓存缺失，请先运行LGB组合 (ID: {aid[:12]}...)'}), 400
            elif expr.startswith('superalpha[') or expr.startswith('superalpha('):
                # Try to reuse cached OOS matrix first (true nesting)
                cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', f'ew_{aid}.npy')
                if os.path.exists(cache_path):
                    idx = len(expressions)
                    cached_expr_map[str(idx)] = cache_path
                    expressions.append('__cached__')
                    lineage_labels.append(f'superalpha_ref({aid})')
                    weights.append(source_weight)
                    continue
                # Fallback: expand to inner expressions
                if expr.startswith('superalpha('):
                    inner = expr[len('superalpha('):-1]
                    base_exprs = [e.strip() for e in inner.split(' + ') if e.strip()]
                    w_each = source_weight / len(base_exprs)
                    for be in base_exprs:
                        expressions.append(be)
                        lineage_labels.append(be)
                        weights.append(w_each)
                else:
                    tag_end = expr.index('](') + 1
                    inner = expr[tag_end+1:-1]
                    for part in inner.split(' + '):
                        part = part.strip()
                        if '*' in part:
                            w_str, be = part.split('*', 1)
                            try:
                                w = float(w_str.strip())
                            except ValueError:
                                w = 1.0
                            expressions.append(be.strip())
                            lineage_labels.append(be.strip())
                            weights.append(source_weight * w)
                        else:
                            expressions.append(part)
                            lineage_labels.append(part)
                            weights.append(source_weight)
            else:
                expressions.append(expr)
                lineage_labels.append(expr)
                weights.append(source_weight)
                alpha_ids_for_subs.append(aid)

        if not expressions:
            return jsonify({'error': '没有有效的表达式可用于组合'}), 400

    else:
        return jsonify({'error': '请提供 expressions（表达式列表）或 alpha_ids（历史记录ID列表）'}), 400

    # Determine combination method
    method = data.get('method', 'equal')

    try:
        pipeline, engine, fc = get_engine()

        if method == 'icir' or method == 'ridge':
            # Compute ICIR/volatility weights from IS period only (2020-2022)
            # to avoid look-ahead bias — same split as LGB training
            t_full0 = pipeline.date_to_idx['2020-01-02']
            # Find last trading day before 2023
            t_full1 = None
            for d in sorted(pipeline.date_to_idx.keys(), reverse=True):
                if d < '2023-01-01':
                    t_full1 = pipeline.date_to_idx[d] + 1
                    break
            if t_full1 is None:
                t_full1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
            label_full = pipeline.fields['Label'][t_full0:t_full1]
            univ_full = pipeline.universe_mask[t_full0:t_full1]
            n_dates = label_full.shape[0]

            icirs = []
            vols = []
            for expr in expressions:
                if isinstance(expr, tuple) and expr[0] == '__cached__':
                    # Cached LGB: approximate ICIR from stored metrics
                    icirs.append(1.0)
                    vols.append(1.0)
                    continue
                try:
                    factor = parse_expression(expr, pipeline, fc)
                    f_train = np.asarray(factor[t_full0:t_full1], dtype=np.float32)
                    del factor
                    # Compute daily rank IC
                    daily_ic = []
                    daily_returns = []
                    for t in range(n_dates):
                        fv = f_train[t]
                        lv = label_full[t]
                        valid = univ_full[t] & (~np.isnan(fv)) & (~np.isnan(lv))
                        if valid.sum() < 30:
                            continue
                        from scipy import stats as _scipy_stats
                        ic = _scipy_stats.spearmanr(fv[valid], lv[valid])[0]
                        if not np.isnan(ic):
                            daily_ic.append(ic)
                            daily_returns.append(np.nanmean(fv[valid]))
                    ic_arr = np.array(daily_ic)
                    mean_ic = np.nanmean(ic_arr)
                    std_ic = np.nanstd(ic_arr)
                    icir = mean_ic / (std_ic + 1e-10)
                    icirs.append(max(0.1, icir))  # floor at 0.1 to avoid negative/zero
                    vols.append(np.nanstd(np.array(daily_returns)) + 1e-10)
                    del f_train
                except Exception:
                    icirs.append(0.1)
                    vols.append(1.0)

        if method == 'icir':
            icir_sum = sum(icirs)
            weights = [ic / icir_sum for ic in icirs] if icir_sum > 0 else [1.0/len(expressions)]*len(expressions)
        elif method == 'ridge':
            # Ridge-like: w_i ∝ 1/(σ_i + λ) where λ = median(σ)
            lam = np.median(vols) if vols else 1.0
            inv_vols = [1.0 / (v + lam) for v in vols]
            inv_sum = sum(inv_vols)
            weights = [iv / inv_sum for iv in inv_vols] if inv_sum > 0 else [1.0/len(expressions)]*len(expressions)
        else:
            # Default: equal weight
            w_sum = sum(weights)
            weights = [w / w_sum for w in weights]

        # Use OOS period (2023) only — aligned with LGB evaluation
        has_cached = any(isinstance(e, tuple) and e[0] == '__cached__' for e in expressions)
        date_keys = sorted(pipeline.date_to_idx.keys())
        if has_cached or data.get('oos_only', False):
            t0 = None
            for d in date_keys:
                if d >= '2023-01-01':
                    t0 = pipeline.date_to_idx[d]
                    break
            if t0 is None: t0 = pipeline.date_to_idx[date_keys[-1]]
            t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
        else:
            t0 = pipeline.date_to_idx['2020-01-02']
            t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
        label_train = pipeline.fields['Label'][t0:t1]
        univ_train = pipeline.universe_mask[t0:t1]

        import gc
        sub_results = []
        skipped_features = []
        n_dates, n_stocks = label_train.shape
        combined = np.zeros((n_dates, n_stocks), dtype=np.float32)
        weight_sum = np.zeros((n_dates, n_stocks), dtype=np.float32)
        sub_alpha_limit = int(data.get('sub_alpha_limit', len(expressions)) or 0)
        sub_alpha_limit = max(0, min(sub_alpha_limit, len(expressions), 100))
        valid_count = 0

        # ---- INLINE path for small combos (≤10 factors, no cached matrices) ----
        has_cached = any(e == '__cached__' for e in expressions) if expressions else False
        # Use inline path for <=10 factors even with cached matrices
        if len(expressions) <= 10:
            result = _compute_superalpha_inline(
                expressions, weights, neutralize, sub_alpha_limit, method,
                cached_expr_map, lineage_labels,
            )
            return jsonify(result)

        # ---- Subprocess path for larger combos ----
        cached_expr_map_send = {}
        expr_strs = []
        for i, e in enumerate(expressions):
            if e == '__cached__':
                cache_path = cached_expr_map.get(str(i))
                if cache_path:
                    cached_expr_map_send[str(len(expr_strs))] = cache_path
                expr_strs.append('__cached__')
            elif isinstance(e, tuple) and e[0] == '__cached__':
                # Legacy tuple path (should no longer be used)
                expr_strs.append('__cached__')
            else:
                expr_strs.append(e)

        data_for_worker = {
            'expressions': [str(e) for e in expr_strs],
            'weights': [float(w) for w in weights],
            'neutralize': str(neutralize),
            'sub_alpha_limit': int(sub_alpha_limit),
            'method': str(method),
            'oos_only': True,
            'cached_expr_map': cached_expr_map_send,
        }

        result = _run_compute_subprocess('superalpha', data_for_worker)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'SuperAlpha计算失败: {str(e)}'}), 400


# ---- Task 4: Alpha History CRUD (SQLite-backed) ----

@app.route('/api/alpha/history', methods=['GET'])
def api_alpha_history():
    """Return all alpha history records (newest first)."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json, max_corr '
        'FROM alpha_history '
        'WHERE (type!=\'alpha\' OR type IS NULL OR ABS(CAST(json_extract(metrics_json,\'$.is_pearson_ic\') AS REAL)) > 0.01) '
        'ORDER BY timestamp DESC'
    ).fetchall()
    conn.close()

    records = []
    for row in rows:
        rec = _row_to_record(row, include_pnl=True)
        if rec is None:
            continue
        _normalize_history_metrics(rec)
        records.append(rec)

    computed_corrs = _history_max_corrs(records)
    records, dropped_mirrors = _filter_negative_mirror_records(records)
    for rec in records:
        computed_corr = _safe_float(computed_corrs.get(rec.get('id')))
        stored_corr = _history_metric_value(rec, 'max_corr')
        if computed_corr is not None and computed_corr > 0:
            stored_corr = computed_corr
        rec['max_corr'] = round(float(stored_corr), 4) if stored_corr is not None and stored_corr > 0 else None
        rec.update(_economic_group(rec.get('expression'), rec.get('type')))
        rec.pop('pnl_series', None)
        rec.pop('ic_series', None)
        if 'name' not in rec or not rec['name']:
            expr = rec.get('expression', '')
            rec['name'] = expr[:40] + ('...' if len(expr) > 40 else '')

    return jsonify({
        'count': len(records),
        'records': records,
        'dropped_negative_mirrors': dropped_mirrors,
        'max_corr_computed': bool(computed_corrs),
    })


@app.route('/api/alpha/history/corr_greedy', methods=['POST'])
def api_alpha_history_corr_greedy():
    """Select single alphas by a chosen metric with greedy PnL-correlation filtering."""
    if 'user' not in session:
        return jsonify({'error': 'not logged in'}), 401

    data = request.get_json() or {}
    try:
        max_corr = float(data.get('max_corr', 0.7))
        keep_count = int(data.get('keep_count', 50))
    except Exception:
        return jsonify({'error': 'invalid max_corr or keep_count'}), 400
    sort_metric = str(data.get('sort_metric') or 'abs_ic').lower()
    sort_order = str(data.get('sort_order') or 'desc').lower()
    if sort_order not in ('asc', 'desc'):
        sort_order = 'desc'
    valid_metrics = {
        'ic', 'abs_ic', 'rank_ic', 'icir', 'sharpe', 'fitness', 'annual',
        'annual_excess', 'returns', 'turnover', 'maxdd', 'max_drawdown',
        'max_corr', 'corr', 'margin_bps', 'sortino', 'win_rate', 'timestamp',
    }
    if sort_metric not in valid_metrics:
        return jsonify({'error': 'invalid sort_metric'}), 400
    if not (0 <= max_corr <= 1):
        return jsonify({'error': 'max_corr must be between 0 and 1'}), 400
    if keep_count < 1:
        return jsonify({'error': 'keep_count must be positive'}), 400

    candidate_ids = data.get('candidate_ids') or []
    if not isinstance(candidate_ids, list):
        return jsonify({'error': 'candidate_ids must be a list'}), 400
    candidate_ids = [str(x) for x in candidate_ids if x]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = (
        "SELECT * FROM alpha_history "
        "WHERE ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01 "
        "AND pnl_json IS NOT NULL AND length(pnl_json) > 5"
    )
    params = []
    if candidate_ids:
        placeholders = ','.join(['?'] * len(candidate_ids))
        sql += f" AND id IN ({placeholders})"
        params.extend(candidate_ids)
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    candidates = []
    for row in rows:
        rec = _row_to_record(row, include_pnl=True)
        if rec is None:
            continue
        expr = rec.get('expression') or ''
        _normalize_history_metrics(rec)
        rec.update(_economic_group(expr, rec.get('type')))
        ic = _safe_float((rec.get('metrics') or {}).get('pearson_ic'))
        daily = _daily_returns_from_cum_pct(rec.get('pnl_series', []))
        score = _history_metric_value(rec, sort_metric)
        if ic is None or score is None or len(daily) < 30:
            continue
        candidates.append({'record': rec, 'ic': ic, 'score': score, 'daily': daily})

    filtered_records, dropped_mirrors = _filter_negative_mirror_records([x['record'] for x in candidates])
    kept_record_ids = {x.get('id') for x in filtered_records}
    candidates = [x for x in candidates if x['record'].get('id') in kept_record_ids]
    candidates.sort(key=lambda x: x['score'], reverse=(sort_order != 'asc'))
    selected = []
    skipped_corr = 0
    selected_max_corr = 0.0
    for cand in candidates:
        if len(selected) >= keep_count:
            break
        worst = 0.0
        too_close = False
        for kept in selected:
            c = _abs_corr_aligned(cand['daily'], kept['daily'])
            if c is None:
                continue
            worst = max(worst, c)
            if c > max_corr:
                too_close = True
                break
        if too_close:
            skipped_corr += 1
            continue
        cand['selected_max_corr'] = round(float(worst), 4)
        selected_max_corr = max(selected_max_corr, worst)
        selected.append(cand)

    out = []
    for item in selected:
        rec = item['record']
        rec['selected_max_corr'] = item['selected_max_corr']
        rec.pop('pnl_series', None)
        rec.pop('ic_series', None)
        out.append(rec)

    avg_ic = float(np.mean([x['ic'] for x in selected])) if selected else 0.0
    min_ic = float(min([x['ic'] for x in selected])) if selected else 0.0
    avg_score = float(np.mean([x['score'] for x in selected])) if selected else 0.0
    return jsonify({
        'success': True,
        'max_corr': max_corr,
        'sort_metric': sort_metric,
        'sort_order': sort_order,
        'requested_keep_count': keep_count,
        'candidate_count': len(candidates),
        'selected_count': len(out),
        'dropped_negative_mirrors': dropped_mirrors,
        'skipped_by_corr': skipped_corr,
        'selected_max_corr': round(float(selected_max_corr), 4),
        'avg_ic': round(avg_ic, 4),
        'min_ic': round(min_ic, 4),
        'avg_score': round(avg_score, 4),
        'ids': [r.get('id') for r in out],
        'expressions': [r.get('expression') for r in out],
        'records': out,
    })

@app.route('/api/alpha/history/<record_id>/pnl', methods=['GET'])
def api_alpha_history_pnl(record_id):
    """Return PnL + full metrics with IS/OOS split."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute('SELECT * FROM alpha_history WHERE id=?', (record_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': '记录不存在'}), 404
    rec = _row_to_record(row, include_pnl=True)
    if rec is None:
        return jsonify({'error': '记录无效'}), 404
    m = rec.get('metrics', {})
    # IS and OOS PnL stored as separate series
    pnl_is = m.get('is_pnl_series', [])
    pnl_oos = rec.get('pnl_series', [])  # OOS is the primary PnL
    return jsonify({
        'id': rec['id'],
        'name': rec.get('name',''),
        'expression': rec.get('expression',''),
        'pnl_is': pnl_is,
        'pnl_oos': pnl_oos,
        'metrics': m,
    })


@app.route('/api/alpha/history/<record_id>', methods=['DELETE'])
def api_alpha_history_delete(record_id):
    """Delete a specific history record by ID."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute('DELETE FROM alpha_history WHERE id = ?', (record_id,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()

    if deleted:
        return jsonify({'success': True, 'deleted': record_id})
    return jsonify({'error': '记录不存在'}), 404


@app.route('/api/alpha/history/<record_id>/rename', methods=['POST'])
def api_alpha_history_rename(record_id):
    """Rename a specific history record."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    new_name = (data.get('name', '') or '').strip()
    if not new_name:
        return jsonify({'error': '名称不能为空'}), 400
    if len(new_name) > 200:
        return jsonify({'error': '名称不超过200字符'}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        'UPDATE alpha_history SET name = ? WHERE id = ?', (new_name, record_id)
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()

    if updated:
        return jsonify({'success': True, 'id': record_id, 'name': new_name})
    return jsonify({'error': '记录不存在'}), 404


@app.route('/api/alpha/compare', methods=['POST'])
def api_alpha_compare():
    """Compare 2-5 alphas side-by-side. Returns metrics, pnl_series, ic_series for each."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    ids = data.get('ids', [])

    if not ids or len(ids) < 2:
        return jsonify({'error': '至少需要选择2个Alpha'}), 400
    # No upper limit

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    placeholders = ','.join(['?' for _ in ids])
    rows = conn.execute(
        f'SELECT * FROM alpha_history WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    id_to_record = {}
    for row in rows:
        rec = _row_to_record(row)
        if rec is None: continue
        id_to_record[rec['id']] = rec

    alphas = []
    for aid in ids:
        rec = id_to_record.get(aid)
        if not rec:
            return jsonify({'error': f'Alpha ID {aid} 不存在'}), 404
        m = rec.get('metrics', {})
        alphas.append({
            'id': rec['id'],
            'name': rec.get('name', rec['expression'][:40]),
            'expression': rec['expression'],
            'type': rec.get('type', 'alpha'),
            'timestamp': rec.get('timestamp', ''),
            'metrics': {
                'pearson_ic': m.get('pearson_ic'),
                'annual_excess': m.get('annual_excess'),
                'sharpe': m.get('sharpe'),
                'fitness': m.get('fitness'),
                'turnover': m.get('turnover'),
                'max_drawdown': m.get('max_drawdown'),
                'margin_bps': m.get('margin_bps'),
                'win_rate': m.get('win_rate'),
                'rank_ic': m.get('rank_ic'),
                'icir': m.get('icir'),
                'sortino': m.get('sortino'),
            },
            'pnl_series': rec.get('pnl_series', []),
            'ic_series': rec.get('ic_series', []),
        })

    return jsonify({'success': True, 'alphas': alphas})


@app.route('/api/alpha/correlation', methods=['POST'])
def api_alpha_correlation():
    """Compute pairwise correlation matrix of daily excess returns. No upper limit.

    Accepts: {"ids": ["id1","id2",...]}
    Returns: alphas metadata, daily_pnl (differenced from cumulative),
             ic_series, correlation_matrix, estimated_time_seconds.
    """
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    ids = data.get('ids', [])

    if not ids or len(ids) < 2:
        return jsonify({'error': '至少需要选择2个Alpha'}), 400
    # No upper limit — estimate time: O(n^2 * pnl_length)
    n = len(ids)
    est_seconds = n * n * 970 / 1000000 * 0.05  # rough estimate

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    placeholders = ','.join(['?' for _ in ids])
    rows = conn.execute(
        f'SELECT * FROM alpha_history WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    id_to_record = {}
    for row in rows:
        rec = _row_to_record(row, include_pnl=True)
        if rec is None: continue
        id_to_record[rec['id']] = rec

    alphas = []
    daily_pnls = []  # list of 1D np arrays (daily excess returns, not cumulative)

    for aid in ids:
        rec = id_to_record.get(aid)
        if not rec:
            return jsonify({'error': f'Alpha ID {aid} 不存在'}), 404
        m = rec.get('metrics', {})
        cum_pnl = rec.get('pnl_series', [])
        # Difference cumulative PnL to get daily excess returns (%)
        # cum_pnl stores cumulative % (cum * 100), so diff gives daily bp changes / 100 = daily excess return in %
        dailies = np.array([cum_pnl[i] - cum_pnl[i - 1] for i in range(1, len(cum_pnl))]) if len(cum_pnl) > 1 else np.array([])
        daily_pnls.append(dailies)
        alphas.append({
            'id': rec['id'],
            'name': rec.get('name', rec['expression'][:40]),
            'expression': rec['expression'],
            'type': rec.get('type', 'alpha'),
            'metrics': {
                'pearson_ic': m.get('pearson_ic'),
                'annual_excess': m.get('annual_excess'),
                'sharpe': m.get('sharpe'),
                'fitness': m.get('fitness'),
                'turnover': m.get('turnover'),
                'max_drawdown': m.get('max_drawdown'),
                'margin_bps': m.get('margin_bps'),
                'win_rate': m.get('win_rate'),
            },
            'pnl_series': rec.get('pnl_series', []),
            'ic_series': rec.get('ic_series', []),
        })

    # Compute pairwise correlation matrix from daily excess returns
    n = len(alphas)
    corr_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                corr_matrix[i][j] = 1.0
            else:
                a = daily_pnls[i]
                b = daily_pnls[j]
                # Align to common length
                min_len = min(len(a), len(b))
                if min_len < 10:
                    corr_matrix[i][j] = 0.0
                    continue
                aa = a[-min_len:]
                bb = b[-min_len:]
                # Remove NaNs / Infs
                mask = np.isfinite(aa) & np.isfinite(bb)
                if mask.sum() < 10:
                    corr_matrix[i][j] = 0.0
                else:
                    corr_matrix[i][j] = round(float(np.corrcoef(aa[mask], bb[mask])[0, 1]), 4)

    # Find most and least correlated pair
    max_corr = -2.0
    min_corr = 2.0
    max_pair = None
    min_pair = None
    for i in range(n):
        for j in range(i + 1, n):
            c = corr_matrix[i][j]
            if c > max_corr:
                max_corr = c
                max_pair = (alphas[i]['name'], alphas[j]['name'], c)
            if c < min_corr:
                min_corr = c
                min_pair = (alphas[i]['name'], alphas[j]['name'], c)

    return jsonify({
        'success': True,
        'alphas': alphas,
        'corr_matrix': corr_matrix.tolist(),
        'summary': {
            'max_pair': list(max_pair) if max_pair else None,
            'min_pair': list(min_pair) if min_pair else None,
        },
    })


@app.route('/api/alpha/decay', methods=['POST'])
def api_alpha_decay():
    """Compute IC Persistence (IC series autocorrelation at lags) for 3-10 alphas.

    IMPORTANT: This is NOT WQ-style IC Decay (factor[t] vs label[t+lag]).
    Since raw factor arrays are too large to store, we use the stored IC series
    as an approximation. This measures "IC Persistence" — the autocorrelation of
    the daily IC sequence at lags [1, 3, 5, 10, 15, 20] — which captures how
    persistently the factor's predictive power holds over time.

    Accepts: {"ids": ["id1","id2",...]}
    """
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    ids = data.get('ids', [])

    if not ids or len(ids) < 3:
        return jsonify({'error': '至少需要选择3个Alpha'}), 400
    # No upper limit

    lags = [1, 3, 5, 10, 15, 20]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    placeholders = ','.join(['?' for _ in ids])
    rows = conn.execute(
        f'SELECT * FROM alpha_history WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    id_to_record = {}
    for row in rows:
        rec = _row_to_record(row)
        id_to_record[rec['id']] = rec

    decay_results = []
    for aid in ids:
        rec = id_to_record.get(aid)
        if not rec:
            return jsonify({'error': f'Alpha ID {aid} 不存在'}), 404

        ic_raw = rec.get('ic_series', [])
        # ic_series is stored as list of floats (or None for NaN)
        ic_arr = np.array([x if x is not None else np.nan for x in ic_raw], dtype=np.float64)
        # Remove NaN values
        ic_clean = ic_arr[np.isfinite(ic_arr)]

        decay = {}
        for lag in lags:
            if len(ic_clean) > lag + 10:
                a = ic_clean[lag:]
                b = ic_clean[:-lag]
                mask = np.isfinite(a) & np.isfinite(b)
                if mask.sum() >= 10:
                    decay[str(lag)] = round(float(np.corrcoef(a[mask], b[mask])[0, 1]), 4)
                else:
                    decay[str(lag)] = None
            else:
                decay[str(lag)] = None

        decay_results.append({
            'id': rec['id'],
            'name': rec.get('name', rec['expression'][:40]),
            'persistence': decay,
        })

    return jsonify({
        'success': True,
        'lags': lags,
        'decay_results': decay_results,
        'note': 'IC Persistence (IC时序自相关): 近似度量，因子原始数组未存储，使用已保存的IC序列计算自相关。测量的是IC自身的持续性，而非因子值与未来收益的相关性。',
    })


@app.route('/api/alpha/selfcorr', methods=['POST'])
def api_alpha_selfcorr():
    """Compute IC Self-Correlation (lag-1 IC autocorrelation) for 1-50 alphas.

    WQ requires self_corr < 0.6 for submission. Since raw factor arrays are not
    stored (too large), this uses the stored IC series as an approximation.
    True factor self-correlation (factor[t] vs factor[t+1]) would correlate the
    raw factor values across adjacent days, but we approximate it using the IC
    series lag-1 autocorrelation instead.

    Accepts: {"ids": ["id1","id2",...]}
    Returns: [{id, name, self_corr, status ("PASS"/"FAIL")}]
    """
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    ids = data.get('ids', [])

    if not ids or len(ids) < 1:
        return jsonify({'error': '至少需要选择1个Alpha'}), 400
    # No upper limit

    THRESHOLD = 0.6
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    placeholders = ','.join(['?' for _ in ids])
    rows = conn.execute(
        f'SELECT * FROM alpha_history WHERE id IN ({placeholders})', ids
    ).fetchall()
    conn.close()

    id_to_record = {}
    for row in rows:
        rec = _row_to_record(row)
        id_to_record[rec['id']] = rec

    results = []
    for aid in ids:
        rec = id_to_record.get(aid)
        if not rec:
            return jsonify({'error': f'Alpha ID {aid} 不存在'}), 404

        ic_raw = rec.get('ic_series', [])
        ic_arr = np.array([x if x is not None else np.nan for x in ic_raw], dtype=np.float64)
        ic_clean = ic_arr[np.isfinite(ic_arr)]

        if len(ic_clean) > 11:
            a = ic_clean[1:]
            b = ic_clean[:-1]
            mask = np.isfinite(a) & np.isfinite(b)
            if mask.sum() >= 10:
                lag1_corr = round(float(np.corrcoef(a[mask], b[mask])[0, 1]), 4)
            else:
                lag1_corr = None
        else:
            lag1_corr = None

        m = rec.get('metrics', {})
        results.append({
            'id': rec['id'],
            'name': rec.get('name', rec['expression'][:40]),
            'expression': rec['expression'],
            'self_corr': lag1_corr,
            'status': 'PASS' if lag1_corr is not None and abs(lag1_corr) < THRESHOLD else 'FAIL',
            'sharpe': m.get('sharpe'),
            'pearson_ic': m.get('pearson_ic'),
        })

    return jsonify({
        'success': True,
        'threshold': THRESHOLD,
        'results': results,
        'note': 'IC Self-Correlation (近似): 使用IC序列的lag-1自相关近似因子自相关。WQ要求 self_corr < 0.6 方可提交。',
    })


@app.route('/api/alpha/history/dedup', methods=['POST'])
def api_alpha_history_dedup():
    """Deduplicate alpha history — keep only the best entry per unique expression."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT id, expression, metrics_json FROM alpha_history ORDER BY timestamp DESC'
    ).fetchall()
    conn.close()
    # Group by expression, keep only the BEST (highest Sharpe+Fitness) per expression
    seen = {}
    to_delete = []
    for row in rows:
        expr = row['expression'].strip()
        if expr in seen:
            to_delete.append(row['id'])
        else:
            seen[expr] = row['id']
    if not to_delete:
        return jsonify({'success': True, 'deleted': 0, 'kept': len(seen), 'message': '没有重复因子'})
    conn = sqlite3.connect(DB_PATH)
    for rid in to_delete:
        conn.execute('DELETE FROM alpha_history WHERE id=?', (rid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'deleted': len(to_delete), 'kept': len(seen)})


@app.route('/api/alpha/history/clear', methods=['POST'])
def api_alpha_history_clear():
    """Clear all alpha history after making a recoverable archive copy."""
    if 'user' not in session:
        return jsonify({'error': 'not logged in'}), 401

    import shutil
    backup_path = os.path.join(
        os.path.dirname(DB_PATH),
        'backtest_before_clear_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '.db'
    )
    try:
        shutil.copy2(DB_PATH, backup_path)
    except Exception:
        backup_path = None

    conn = sqlite3.connect(DB_PATH)
    count = conn.execute('SELECT COUNT(*) FROM alpha_history').fetchone()[0]
    conn.execute('''CREATE TABLE IF NOT EXISTS alpha_history_trash (
        deleted_at TEXT,
        id TEXT, name TEXT, expression TEXT,
        timestamp TEXT, type TEXT, metrics_json TEXT,
        pnl_json TEXT, ic_json TEXT, max_corr REAL, neutralization TEXT
    )''')
    deleted_at = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    conn.execute('''INSERT INTO alpha_history_trash
        (deleted_at, id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json, max_corr, neutralization)
        SELECT ?, id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json, max_corr, neutralization
        FROM alpha_history''', (deleted_at,))
    conn.execute('DELETE FROM alpha_history')
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'cleared': count, 'archived': count, 'backup': backup_path})

# ---- Community Forum (SQLite-backed) ----

@app.route('/learn')
def learn_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('learn.html')


@app.route('/community')
def community_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    raw_user = session['user']
    display_name = _resolve_display_name(raw_user)
    return render_template('community.html', username=display_name, is_admin=(raw_user=='admin'))


@app.route('/api/community/posts', methods=['GET'])
def api_community_get_posts():
    """Return all community posts (newest first), with alpha_ref when alpha_id is set."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT p.*, a.expression AS ref_expr, a.metrics_json AS ref_metrics, a.pnl_json AS ref_pnl '
        'FROM community_posts p '
        'LEFT JOIN alpha_history a ON p.alpha_id = a.id '
        'ORDER BY p.timestamp DESC'
    ).fetchall()
    # Get likes for current user
    user_email = session.get('user', '')
    liked_rows = conn.execute('SELECT post_id FROM post_likes WHERE user_email=?',
                              (user_email,)).fetchall()
    liked_set = {r['post_id'] for r in liked_rows}
    conn.close()

    posts = []
    for row in rows:
        post = _build_post_dict(dict(row))
        post['likes'] = row['likes'] or 0
        post['liked_by_me'] = row['id'] in liked_set
        # Admin badge
        post['is_admin'] = (row['author'] == 'admin')
        posts.append(post)
    return jsonify({'count': len(posts), 'posts': posts})


@app.route('/api/community/posts', methods=['POST'])
def api_community_create_post():
    """Create a new community post. Accepts optional alpha_id to reference an alpha."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': '请求体为空'}), 400

    expression = (data.get('expression', '') or '').strip()
    if not expression:
        return jsonify({'error': '表达式不能为空'}), 400

    name = (data.get('name', '') or '').strip()
    description = (data.get('description', '') or '').strip()
    alpha_id = (data.get('alpha_id', '') or '').strip()

    raw_user = session['user']

    # Validate alpha_id if provided
    if alpha_id:
        conn = sqlite3.connect(DB_PATH)
        exists = conn.execute('SELECT 1 FROM alpha_history WHERE id=?', (alpha_id,)).fetchone()
        conn.close()
        if not exists:
            return jsonify({'error': '引用的 Alpha 不存在'}), 400

    # Resolve display name: look up nickname from users table
    display_name = _resolve_display_name(raw_user)

    post_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    post_name = name or expression[:40] + ('...' if len(expression) > 40 else '')

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO community_posts (id, author, expression, name, description, timestamp, alpha_id) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (post_id, raw_user, expression, post_name, description, timestamp, alpha_id or None)
    )
    conn.commit()
    conn.close()

    post = {
        'id': post_id,
        'author': raw_user,
        'author_display': display_name,
        'expression': expression,
        'name': post_name,
        'description': description,
        'timestamp': timestamp,
        'alpha_id': alpha_id or None,
    }
    return jsonify({'success': True, 'post': post})


@app.route('/api/community/posts/<post_id>', methods=['DELETE'])
def api_community_delete_post(post_id):
    """Delete a community post (admin only)."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    if session['user'] != 'admin':
        return jsonify({'error': '仅管理员可删除'}), 403
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM community_posts WHERE id=?', (post_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/community/posts/<post_id>/like', methods=['POST'])
def api_community_like(post_id):
    """Toggle like on a post."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    user_email = session['user']
    conn = sqlite3.connect(DB_PATH)
    existing = conn.execute('SELECT 1 FROM post_likes WHERE post_id=? AND user_email=?',
                            (post_id, user_email)).fetchone()
    if existing:
        conn.execute('DELETE FROM post_likes WHERE post_id=? AND user_email=?',
                     (post_id, user_email))
        conn.execute('UPDATE community_posts SET likes=MAX(0, likes-1) WHERE id=?', (post_id,))
        conn.commit()
        likes = conn.execute('SELECT likes FROM community_posts WHERE id=?', (post_id,)).fetchone()
        conn.close()
        return jsonify({'liked': False, 'likes': likes[0] if likes else 0})
    else:
        conn.execute('INSERT INTO post_likes(post_id, user_email) VALUES(?,?)',
                     (post_id, user_email))
        conn.execute('UPDATE community_posts SET likes=likes+1 WHERE id=?', (post_id,))
        conn.commit()
        likes = conn.execute('SELECT likes FROM community_posts WHERE id=?', (post_id,)).fetchone()
        conn.close()
        return jsonify({'liked': True, 'likes': likes[0] if likes else 0})


@app.route('/api/community/posts/<post_id>/comments', methods=['GET'])
def api_community_get_comments(post_id):
    """Get comments for a post."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT * FROM post_comments WHERE post_id=? ORDER BY timestamp ASC',
        (post_id,)
    ).fetchall()
    conn.close()
    comments = []
    for row in rows:
        c = dict(row)
        c['author_display'] = _resolve_display_name(c.get('author', ''))
        c['is_admin'] = (c.get('author', '') == 'admin')
        comments.append(c)
    return jsonify({'comments': comments})


@app.route('/api/community/posts/<post_id>/comments', methods=['POST'])
def api_community_create_comment(post_id):
    """Add a comment to a post."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    data = request.get_json()
    content = (data.get('content', '') or '').strip()
    if not content:
        return jsonify({'error': '评论内容不能为空'}), 400
    if len(content) > 1000:
        return jsonify({'error': '评论不超过1000字'}), 400
    comment_id = str(uuid.uuid4())
    timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    user_email = session['user']
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO post_comments(id, post_id, author, content, timestamp) VALUES(?,?,?,?,?)',
        (comment_id, post_id, user_email, content, timestamp)
    )
    conn.commit()
    conn.close()
    return jsonify({
        'id': comment_id,
        'post_id': post_id,
        'author': user_email,
        'author_display': _resolve_display_name(user_email),
        'is_admin': (user_email == 'admin'),
        'content': content,
        'timestamp': timestamp,
    })


# ======================== MAIN ========================

# AI conversation memory (in-memory, per user session)
_ai_memory = {}

def _local_ai_fallback(question):
    """Deterministic platform help when DeepSeek is unavailable."""
    q = (question or '').lower()
    q_cn = question or ''
    if 'lgb' in q or 'lightgbm' in q or '机器学习' in q_cn:
        return ('LightGBM 组合现在按样本外口径运行：先对表达式去重并跳过解析失败/常数特征，'
                '用 2020-2022 训练，默认 purge_days=5，最后只在 2023 OOS 评估。'
                '默认最多训练 300 个唯一特征，并受内存预算限制，适合验证非线性组合是否真的泛化。')
    if '等权' in q_cn or '组合' in q_cn or 'superalpha' in q:
        return ('等权组合会把选中的单因子逐个截面标准化，再等权平均后回测。'
                '它的价值是检验低相关弱因子能否叠加成更稳定的 PnL；如果 maxcorr 低、回撤下降、OOS 年化提升，通常比单个高 IC 高相关因子更稳。')
    if '单因子' in q_cn or '表达式' in q_cn or '因子' in q_cn:
        return ('单因子回测用于验证一个经济假设。建议从字段含义出发，经过时序处理、截面 rank/zscore、必要的中性化后再回测；'
                '保留时看 |IC|、年化超额、最大回撤、换手、PnL 稳定性和与已有因子的相关性。')
    if 'maxcorr' in q or '相关' in q_cn or '去重' in q_cn:
        return ('maxcorr 是该因子与已选因子日收益序列的最大相关。Alpha 历史页的贪心去重会按 IC 降序扫描，'
                '只保留与已保留因子相关性不超过你输入阈值的因子，可用来比较“低相关低 IC”和“高相关高 IC”的组合效果。')
    if 'ic' in q or '指标' in q_cn or '年化' in q_cn or '回撤' in q_cn:
        return ('核心指标：IC 衡量信号和未来5日收益的相关；年化超额是 Top10% 多头相对全市场等权的年化收益；'
                '最大回撤看 PnL 最深下跌；Sharpe/Sortino 看收益稳定性；turnover 看换手成本风险。')
    return ('我现在使用本地平台知识兜底回答。这个平台的主流程是：构建表达式 → 单因子回测 → Alpha 历史筛选 → '
            'maxcorr 贪心去重 → 等权或 LightGBM OOS 组合 → 观察 IC、年化、回撤和相关性后决定是否保留。')

@app.route('/api/superalpha/lgb', methods=['POST'])
def api_superalpha_lgb():
    """LightGBM SuperAlpha: train on 2020-2022 and report 2023 OOS metrics."""
    if 'user' not in session:
        return jsonify({'error': 'not logged in'}), 401
    return _do_lgb_training(request.get_json() or {})


def _do_lgb_training(data):
    """Core LGB training logic — no session check (called from both route and bg task)."""
    raw_expressions = [e.strip() for e in (data.get('expressions', []) or []) if e.strip()]
    requested_factor_count = len(raw_expressions)
    seen_expressions = set()
    expressions = []
    cached_matrices = {}  # expr -> full matrix for cached LGB inputs
    for expr in raw_expressions:
        if expr in seen_expressions:
            continue
        seen_expressions.add(expr)
        if expr.startswith('lgb('):
            try:
                cached_matrices[expr] = _load_cached_lgb(expr)
                expressions.append(expr)
            except ValueError:
                continue  # skip if cache unavailable
        else:
            expressions.append(expr)
    deduped_factor_count = len(expressions)
    max_lgb_features = int(data.get('max_lgb_features', 300) or 300)
    max_lgb_features = max(1, min(max_lgb_features, 600))
    feature_truncated = len(expressions) > max_lgb_features
    if feature_truncated:
        expressions = expressions[:max_lgb_features]
    if len(expressions) < 1:
        return jsonify({'error': 'at least one expression is required'}), 400
    try:
        import gc
        import lightgbm as lgb

        pipeline, engine, fc = get_engine()
        date_keys = sorted(pipeline.date_to_idx.keys())

        def idx_on_or_after(date_s):
            for d in date_keys:
                if d >= date_s:
                    return pipeline.date_to_idx[d]
            raise KeyError(date_s)

        def idx_on_or_before(date_s):
            for d in reversed(date_keys):
                if d <= date_s:
                    return pipeline.date_to_idx[d]
            raise KeyError(date_s)

        idx_to_date = {v: k for k, v in pipeline.date_to_idx.items()}
        train_start = idx_on_or_after('2020-01-02')
        train_nominal_end = min(idx_on_or_before('2022-12-31') + 1, pipeline.n_dates)
        oos_start = idx_on_or_after('2023-01-01')
        oos_end = min(idx_on_or_before('2023-12-29') + 1, pipeline.n_dates)
        purge_days = max(0, int(data.get('purge_days', 5) or 0))
        train_end = min(train_nominal_end, max(train_start + 1, oos_start - purge_days))
        if not (train_start < train_end <= oos_start < oos_end):
            return jsonify({'error': 'invalid train/OOS date split'}), 400

        user_max_train_samples = int(data.get('max_train_samples', 500000) or 500000)
        user_max_train_samples = max(1000, min(user_max_train_samples, 1200000))
        train_matrix_budget_mb = int(data.get('train_matrix_budget_mb', 128) or 128)
        train_matrix_budget_mb = max(16, min(train_matrix_budget_mb, 512))
        sub_alpha_limit = int(data.get('sub_alpha_limit', 8) or 8)
        sub_alpha_limit = max(0, min(sub_alpha_limit, len(expressions)))

        label_train = pipeline.fields['Label'][train_start:train_end]
        univ_train = pipeline.universe_mask[train_start:train_end]
        label_oos = pipeline.fields['Label'][oos_start:oos_end]
        univ_oos = pipeline.universe_mask[oos_start:oos_end]
        train_valid = (np.isfinite(label_train) & univ_train).reshape(-1)
        valid_idx = np.flatnonzero(train_valid)
        valid_oos = np.isfinite(label_oos) & univ_oos
        n_oos_valid = int(valid_oos.sum())
        if valid_idx.size < 1000 or n_oos_valid < 1000:
            return jsonify({'error': 'not enough valid samples'}), 400

        rng = np.random.default_rng(42)
        n_features_requested_after_cap = len(expressions)
        bytes_per_row = max(4 * n_features_requested_after_cap, 4)
        budget_rows = max(1000, int(train_matrix_budget_mb * 1024 * 1024 // bytes_per_row))
        max_train_samples = min(user_max_train_samples, budget_rows)
        sampled = valid_idx.size > max_train_samples
        sample_idx = rng.choice(valid_idx, size=max_train_samples, replace=False) if sampled else valid_idx
        n_train_samples = int(sample_idx.size)
        X_train = np.empty((n_train_samples, n_features_requested_after_cap), dtype=np.float32)
        y_train = label_train.reshape(-1)[sample_idx].astype(np.float32, copy=False)

        valid_expressions = []
        skipped_features = []
        oos_factor_arrays = []
        oos_cache_feature_limit = int(data.get('oos_cache_feature_limit', 60) or 60)
        oos_cache_feature_limit = max(0, min(oos_cache_feature_limit, 120))
        cache_oos_arrays = len(expressions) <= oos_cache_feature_limit
        col_idx = 0
        for expr in expressions:
            try:
                if expr in cached_matrices:
                    factor = cached_matrices[expr]
                else:
                    factor = parse_expression(expr, pipeline, fc)
                if factor.shape[0] < oos_end:
                    raise ValueError('factor shape too short')
            except Exception as parse_error:
                skipped_features.append({'expression': expr, 'reason': str(parse_error)[:180]})
                continue
            train_col = factor[train_start:train_end].reshape(-1)[sample_idx]
            train_col = np.nan_to_num(train_col, nan=0.0, posinf=0.0, neginf=0.0)
            if np.nanstd(train_col) <= 1e-12:
                skipped_features.append({'expression': expr, 'reason': 'constant or all-missing train feature'})
                del factor, train_col
                continue
            X_train[:, col_idx] = train_col.astype(np.float32, copy=False)
            valid_expressions.append(expr)
            if cache_oos_arrays:
                oos_factor_arrays.append(np.asarray(factor[oos_start:oos_end], dtype=np.float32).copy())
            del factor, train_col
            col_idx += 1
            if col_idx % 10 == 0:
                gc.collect()
        if col_idx < 1:
            return jsonify({
                'error': 'no valid LightGBM features after parsing',
                'skipped_features': skipped_features[:50],
                'n_skipped_features': len(skipped_features),
            }), 400
        X_train = X_train[:, :col_idx]
        expressions = valid_expressions
        n_features = len(expressions)
        bytes_per_row = max(4 * n_features, 4)
        sub_alpha_limit = max(0, min(sub_alpha_limit, n_features))

        model = lgb.LGBMRegressor(
            n_estimators=int(data.get('n_estimators', 80) or 80),
            learning_rate=0.05,
            max_depth=2,
            num_leaves=7,
            min_child_samples=2000,
            subsample=0.7,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_alpha=5.0,
            reg_lambda=5.0,
            max_bin=63,
            random_state=42,
            verbose=-1,
            n_jobs=2,
            force_col_wise=True,
        )
        model.fit(X_train, y_train)
        del X_train, y_train
        gc.collect()

        n_oos_dates, n_stocks = label_oos.shape
        pred_daily = np.full(label_oos.shape, np.nan, dtype=np.float32)
        pred_flat = pred_daily.reshape(-1)
        predict_matrix_budget_mb = int(data.get('predict_matrix_budget_mb', 16) or 16)
        predict_matrix_budget_mb = max(4, min(predict_matrix_budget_mb, 128))
        max_predict_rows = max(1, int(predict_matrix_budget_mb * 1024 * 1024 // bytes_per_row))
        requested_chunk_days = max(1, int(data.get('predict_chunk_days', 20) or 20))
        chunk_days = max(1, min(requested_chunk_days, n_oos_dates, max(1, max_predict_rows // max(n_stocks, 1))))
        for lo in range(0, n_oos_dates, chunk_days):
            hi = min(n_oos_dates, lo + chunk_days)
            rows = (hi - lo) * n_stocks
            X_chunk = np.empty((rows, n_features), dtype=np.float32)
            for j, expr in enumerate(expressions):
                if cache_oos_arrays:
                    col = oos_factor_arrays[j][lo:hi].reshape(-1)
                else:
                    factor = parse_expression(expr, pipeline, fc)
                    col = factor[oos_start + lo:oos_start + hi].reshape(-1)
                    del factor
                col = np.nan_to_num(col, nan=0.0, posinf=0.0, neginf=0.0)
                X_chunk[:, j] = col.astype(np.float32, copy=False)
            chunk_valid = valid_oos[lo:hi].reshape(-1)
            if np.any(chunk_valid):
                pred_chunk = np.full(rows, np.nan, dtype=np.float32)
                pred_chunk[chunk_valid] = model.predict(X_chunk[chunk_valid]).astype(np.float32, copy=False)
                pred_flat[lo * n_stocks:hi * n_stocks] = pred_chunk
            del X_chunk

        result = engine.full_evaluation(pred_daily, univ_oos, label=label_oos)
        metrics = _compute_metrics_from_result(pred_daily, label_oos, univ_oos, result)
        display_keys = ['pearson_ic','icir','ic_positive_ratio',
            'annual_excess','sharpe','fitness','returns','max_drawdown',
            'turnover','margin_bps','win_rate','n_days',
            'ic_series','pnl_series']
        metrics_clean = {k: v for k, v in metrics.items() if k in display_keys}

        combined_expression = (
            'lgb(train=2020-2022,purge_days=' + str(purge_days) +
            ',oos=2023; ' + ', '.join(expressions) + ')'
        )
        history_id = _add_to_history(combined_expression, metrics_clean, 'superalpha')

        # Cache prediction matrix for reuse in future combos
        if history_id:
            try:
                os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache'), exist_ok=True)
                cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', f'lgb_{history_id}.npy')
                np.save(cache_path, pred_daily)
            except Exception:
                pass

        importance = dict(zip(expressions, model.feature_importances_.tolist()))
        top_sub_indices = sorted(range(len(expressions)), key=lambda k: importance.get(expressions[k], 0), reverse=True)[:sub_alpha_limit]
        sub_alphas = []
        for i in top_sub_indices:
            if cache_oos_arrays:
                sub_factor = oos_factor_arrays[i]
            else:
                full_factor = parse_expression(expressions[i], pipeline, fc)
                sub_factor = np.asarray(full_factor[oos_start:oos_end], dtype=np.float32).copy()
                del full_factor
            sub_result = engine.full_evaluation(sub_factor, univ_oos, label=label_oos)
            sub_metrics = _compute_metrics_from_result(sub_factor, label_oos, univ_oos, sub_result)
            sub_alphas.append({
                'expression': expressions[i],
                'metrics': {k: v for k, v in sub_metrics.items()
                           if k not in ('_factor_array', '_direction', 'ic_series')},
                'pnl_series': sub_metrics.get('pnl_series', []),
                'ic_series': sub_metrics.get('ic_series', []),
            })
        del oos_factor_arrays
        gc.collect()

        return jsonify({
            'success': True,
            'type': 'lgb_superalpha',
            'n_factors': len(expressions),
            'n_requested_factors': requested_factor_count,
            'n_unique_factors': deduped_factor_count,
            'n_skipped_features': len(skipped_features),
            'skipped_features': skipped_features[:50],
            'feature_truncated': feature_truncated,
            'max_lgb_features': max_lgb_features,
            'oos_cached_features': cache_oos_arrays,
            'oos_cache_feature_limit': oos_cache_feature_limit,
            'n_samples': n_train_samples,
            'n_train_samples': n_train_samples,
            'n_train_available': int(valid_idx.size),
            'n_oos_samples': n_oos_valid,
            'sampled_train': sampled,
            'max_train_samples': max_train_samples,
            'user_max_train_samples': user_max_train_samples,
            'train_matrix_budget_mb': train_matrix_budget_mb,
            'predict_matrix_budget_mb': predict_matrix_budget_mb,
            'predict_chunk_days': chunk_days,
            'train_period': {
                'start': idx_to_date.get(train_start, str(train_start)),
                'end': idx_to_date.get(train_end - 1, str(train_end - 1)),
                'purge_days': purge_days,
            },
            'oos_period': {
                'start': idx_to_date.get(oos_start, str(oos_start)),
                'end': idx_to_date.get(oos_end - 1, str(oos_end - 1)),
            },
            'history_id': history_id,
            'feature_importance': importance,
            'metrics': metrics_clean,
            'combined_metrics': metrics_clean,
            'pnl_series': metrics.get('pnl_series', []),
            'sub_alphas': sub_alphas,
            'sub_alphas_truncated': max(0, len(expressions) - len(sub_alphas)),
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': f'LightGBM training failed: {str(e)}'}), 400


@app.route('/api/superalpha/lgb/start', methods=['POST'])
def api_superalpha_lgb_start():
    """Run LGB in subprocess and wait for result — sync, memory-safe, ngrok-friendly."""
    if 'user' not in session:
        return jsonify({'error': 'not logged in'}), 401
    data = request.get_json() or {}
    task_id = str(uuid.uuid4())
    task_file = os.path.join(tempfile.gettempdir(), f'lgb_task_{task_id}.json')
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump({'task_id': task_id, 'data': data}, f)
    worker = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lgb_worker.py')
    proc = subprocess.Popen([sys.executable, worker, task_file],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    result_file = task_file.replace('.json', '_result.json')
    try:
        for _ in range(600):
            time.sleep(1)
            if os.path.exists(result_file):
                try:
                    with open(result_file, 'r', encoding='utf-8') as f:
                        r = json.load(f)
                    if r.get('status') == 'done':
                        return jsonify(r.get('result', {}))
                    elif r.get('status') == 'error':
                        return jsonify({'error': r.get('error', '未知错误')}), 500
                except (json.JSONDecodeError, FileNotFoundError):
                    continue
        return jsonify({'error': 'LightGBM 超时（10分钟）'}), 500
    finally:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            os.remove(task_file)
            if os.path.exists(result_file): os.remove(result_file)
        except OSError:
            pass


@app.route('/api/ai/ask', methods=['POST'])
def api_ai_ask():
    """Platform AI: answer questions by reading source code."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    data = request.get_json()
    question = (data.get('question', '') or '').strip()
    if not question:
        return jsonify({'error': '问题不能为空'}), 400

    # Load key source code sections
    base = os.path.dirname(__file__)
    app_path = os.path.join(base, 'app.py')
    ep_path = os.path.join(base, 'expression_parser.py')

    code_context = ''
    if os.path.exists(app_path):
        with open(app_path, 'r', encoding='utf-8') as f:
            app_code = f.read()
        # Include: LGB endpoint, SA endpoint, backtest, metrics, _add_to_history
        sections = []
        for marker in ['def api_superalpha_lgb', 'def api_superalpha', 'def api_backtest_legacy',
                        'def _compute_metrics_from_result', 'def _add_to_history',
                        'def api_alpha_history', 'def api_community',
                        'def api_ai_ask', 'def _init_db', 'def get_engine']:
            idx = app_code.find(marker)
            if idx >= 0:
                end = app_code.find('\ndef ', idx + 10)
                if end < 0: end = len(app_code)
                sections.append(app_code[max(0,idx-20):min(len(app_code),end+200)])
        code_context += '\n=== app.py 关键函数 ===\n' + '\n...\n'.join(sections[-8:])

    if os.path.exists(ep_path):
        with open(ep_path, 'r', encoding='utf-8') as f:
            ep_code = f.read()
        # Include: parse_expression, _parse_single, _eval_function, field registries
        idx = ep_code.find('def parse_expression')
        if idx >= 0:
            code_context += '\n=== expression_parser.py ===\n' + ep_code[idx:idx+3000]

    # Load complete field list
    from expression_parser import FIELDS_METADATA, DERIVED_FIELD_REGISTRY
    field_list = []
    for name, meta in sorted(FIELDS_METADATA.items()):
        cn = meta.get('chinese_name', name)
        field_list.append(f"  {name} ({cn}) — {meta.get('description','')[:60]}")
    fields_text = '\n'.join(field_list)

    system_prompt = f'''你是"量化回测平台"的AI助手，运行在DeepSeek API上。只能回答平台相关问题，基于下方提供的源码和字段列表精确回答。

平台功能：
- POST /api/backtest — 表达式回测(IC/Sharpe/Fitness/PnL)
- POST /api/superalpha — 等权组合(zscore标准化→等权平均→回测)
- POST /api/superalpha/lgb — LightGBM训练(表达式去重/坏特征跳过→2020-2022训练+5日purge→2023 OOS评估→IC/PnL/特征重要性)
- GET /api/alpha/history — 回测历史
- 89个数据字段(下方完整列表)
- 操作符: rank, zscore, ts_delta, ts_mean, ts_std, ts_rank, ts_sum, ts_corr, ts_decay_linear, ts_delay, ts_backfill, ts_regression, ts_argmax, ts_argmin, signed_power, group_neutralize, group_rank, group_zscore, demean, log, exp, sqrt, abs, sign, power, if_else
- 多行代码: 分号/换行分隔, 变量赋值(如 returns=close/open-1; returns+1)
- 市值中性化: POST时指定neutralize=market_cap

回答规则：严格基于下方源码和字段列表。不知道就说不知道。引用行号。200字以内。

=== 全部可用字段 ===
{fields_text}

=== 平台源码 ===
{code_context}'''

    # Conversation memory
    user = session.get('user', 'guest')
    if user not in _ai_memory:
        _ai_memory[user] = []
    history = _ai_memory[user]

    # Build messages: system + history + current question
    messages = [{'role': 'system', 'content': system_prompt}]
    messages.extend(history[-20:])  # last 10 rounds (20 messages)
    messages.append({'role': 'user', 'content': question})

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        answer = _local_ai_fallback(question)
    else:
        try:
            for attempt in range(3):
                try:
                    resp = requests.post(
                        'https://api.deepseek.com/v1/chat/completions',
                        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
                        json={'model': 'deepseek-chat', 'messages': messages, 'max_tokens': 800, 'temperature': 0.3},
                        timeout=45
                    )
                    break
                except requests.exceptions.Timeout:
                    if attempt == 2: raise
                except requests.exceptions.ConnectionError:
                    if attempt == 2: raise
                    time.sleep(1)
            if resp.status_code == 200:
                answer = resp.json()['choices'][0]['message']['content']
            else:
                answer = _local_ai_fallback(question) + f'\n\nDeepSeek API 暂不可用({resp.status_code})，已使用本地兜底。'
        except Exception as e:
            answer = _local_ai_fallback(question) + f'\n\nDeepSeek 请求失败：{str(e)[:120]}，已使用本地兜底。'

    # Save to history
    history.append({'role': 'user', 'content': question})
    history.append({'role': 'assistant', 'content': answer})
    if len(history) > 40:
        history = history[-40:]
    _ai_memory[user] = history

    return jsonify({'question': question, 'answer': answer})


@app.route('/api/alpha/recompute_max_corr', methods=['POST'])
def api_recompute_max_corr():
    """Recompute max pairwise correlation for all single-alpha factors.

    Computes daily excess returns from stored PnL series, then for each alpha
    finds the maximum correlation with any other alpha. LGB/superalpha combos
    are excluded (they're composites of other factors).

    Returns {updated: N, total: M}."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, expression, type, pnl_json FROM alpha_history"
    ).fetchall()
    conn.close()

    # Filter to single-alphas only (exclude superalpha/LGB combos)
    singles = []
    for row in rows:
        t = row['type'] or 'alpha'
        expr = row['expression'] or ''
        if t == 'superalpha' or expr.startswith('lgb(') or expr.startswith('superalpha('):
            continue
        try:
            pnl_raw = json.loads(row['pnl_json'] or '[]')
        except Exception:
            continue
        if len(pnl_raw) < 20:
            continue
        # Cumulative PnL -> daily excess returns
        dailies = np.array([pnl_raw[i] - pnl_raw[i - 1] for i in range(1, len(pnl_raw))])
        # Remove NaN/Inf
        dailies = dailies[np.isfinite(dailies)]
        if len(dailies) < 20:
            continue
        singles.append((row['id'], dailies))

    if len(singles) < 2:
        return jsonify({'error': '至少需要2个单因子', 'total': len(singles)}), 400

    n = len(singles)
    max_corrs = {sid: 0.0 for sid, _ in singles}

    for i in range(n):
        id_i, di = singles[i]
        for j in range(i + 1, n):
            id_j, dj = singles[j]
            min_len = min(len(di), len(dj))
            if min_len < 10:
                continue
            a = di[-min_len:]
            b = dj[-min_len:]
            mask = np.isfinite(a) & np.isfinite(b)
            if mask.sum() < 10:
                continue
            c = abs(float(np.corrcoef(a[mask], b[mask])[0, 1]))
            if not np.isfinite(c):
                continue
            if c > max_corrs[id_i]:
                max_corrs[id_i] = c
            if c > max_corrs[id_j]:
                max_corrs[id_j] = c

    # Update DB
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for sid, mc in max_corrs.items():
        conn.execute('UPDATE alpha_history SET max_corr=? WHERE id=?',
                     (round(float(mc), 4), sid))
        updated += 1
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'updated': updated, 'total': len(singles)})


@app.route('/api/ai/clear', methods=['POST'])
def api_ai_clear():
    """Clear conversation memory."""
    if 'user' not in session:
        return jsonify({'error': '未登录'}), 401
    user = session.get('user', 'guest')
    _ai_memory.pop(user, None)
    return jsonify({'success': True})


if __name__ == '__main__':
    # Prevent multiple instances — check if port 5000 is already in use
    import socket as _socket
    _test = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    _in_use = _test.connect_ex(('127.0.0.1', 5000)) == 0
    _test.close()
    if _in_use:
        print("[Init] Port 5000 already in use — another Flask instance is running. Exiting.", flush=True)
        sys.exit(0)

    # Clean up stale LGB workers and temp files from previous runs. Keep the
    # external scheduler and combo builder alive so they can recover Flask.
    import subprocess as _sp, glob as _glob, tempfile as _tempfile
    _sp.run(['powershell.exe', '-NoProfile', '-Command',
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'lgb_worker\\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
        capture_output=True)
    for _f in _glob.glob(os.path.join(_tempfile.gettempdir(), 'lgb_task_*.json')):
        try: os.remove(_f)
        except OSError: pass
    print("[Init] Stale workers and temp files cleaned.")

    # Memory watchdog: auto-restart when Flask bloats past 3.5 GB
    def _memory_watchdog():
        import psutil as _psutil
        _proc = _psutil.Process()
        while True:
            time.sleep(60)
            try:
                mem_mb = _proc.memory_info().rss / (1024 * 1024)
                if mem_mb > 4500:
                    # Check if any active compute/LGB workers are running
                    import subprocess as _sp
                    result = _sp.run(['powershell.exe', '-NoProfile', '-Command',
                        "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'compute_worker|lgb_worker' }).Count"],
                        capture_output=True, text=True, timeout=5)
                    workers = int(result.stdout.strip() or '0')
                    if workers == 0:
                        print(f"[Watchdog] Memory {mem_mb:.0f} MB, no active workers — auto-restarting.", flush=True)
                        os._exit(0)
                    else:
                        print(f"[Watchdog] Memory {mem_mb:.0f} MB, but {workers} workers running — deferring restart.", flush=True)
            except Exception:
                pass
    threading.Thread(target=_memory_watchdog, daemon=True).start()

    print("[Init] Loading engine...")
    get_engine()
    print("[Init] Engine ready. Starting server...")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
