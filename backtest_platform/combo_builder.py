#!/usr/bin/env python3
"""Continuous OOS combo builder for YYB.

Builds economically grouped low-correlation LightGBM combos from single-factor
history. It keeps simple factor mining separate: mining can stay paused while
this process continues to search for competition-style combo factors.
"""

import ctypes
import datetime as dt
import hashlib
import json
import math
import os
import random
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


API = os.environ.get("YYB_API", "http://127.0.0.1:5000")
USER = os.environ.get("YYB_USER", "admin")
PASSWORD = os.environ.get("YYB_PASSWORD", "quant2026")
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "backtest.db")
LOG_DIR = r"D:\yyb\logs"
LOG = os.path.join(LOG_DIR, "combo_builder.log")
STATE_FILE = os.path.join(LOG_DIR, "combo_builder_state.json")
STATUS_FILE = os.path.join(LOG_DIR, "combo_builder_status.json")
PAUSE_FLAG = os.path.join(LOG_DIR, "combo_builder_paused.flag")
TARGET_QUALIFIED = int(os.environ.get("YYB_COMBO_TARGET", "100"))
MAX_COMBO_CORR = float(os.environ.get("YYB_COMBO_MAX_CORR", "0.70"))
QUALIFIED_ABS_IC = float(os.environ.get("YYB_COMBO_MIN_ABS_IC", "0.05"))
INTERVAL_SECONDS = int(os.environ.get("YYB_COMBO_INTERVAL", "20"))
MIN_FREE_GB_LGB = float(os.environ.get("YYB_COMBO_MIN_FREE_GB", "4.0"))


THEMES = {
    "liquidity": [
        "turnover", "volume", "vol_ratio", "volume_profile", "volume_breakout",
        "amihud", "liquidity", "dollar", "amount",
    ],
    "reversal": [
        "rev_", "reversal", "gap", "auction", "abnormal_vol_rev",
        "close_location", "shadow", "doji",
    ],
    "momentum": [
        "ret_", "cumret", "momentum", "mom_", "trend", "breakout",
        "ts_delta",
    ],
    "volatility": [
        "vol", "downside", "max_dd", "beta", "skew", "kurt", "bollinger",
        "rsi", "range", "atr",
    ],
    "microstructure": [
        "vwap", "intraday", "smart_money", "body", "upper_shadow",
        "lower_shadow", "close_location", "auction",
    ],
    "size": ["market_cap", "mcap", "size"],
}


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{now()}] {message}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def atomic_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    state.setdefault("cycle", 0)
    state.setdefault("tested", [])
    state.setdefault("qualified", [])
    state.setdefault("errors", [])
    return state


def save_state(state):
    state["tested"] = state.get("tested", [])[-10000:]
    state["errors"] = state.get("errors", [])[-100:]
    atomic_json(STATE_FILE, state)


def write_status(state, **extra):
    qualified = state.get("qualified", [])
    status = {
        "time": now(),
        "target_qualified": TARGET_QUALIFIED,
        "qualified_count": len(qualified),
        "remaining": max(TARGET_QUALIFIED - len(qualified), 0),
        "qualified_abs_ic": QUALIFIED_ABS_IC,
        "max_combo_corr": MAX_COMBO_CORR,
        "cycle": state.get("cycle", 0),
        "tested_count": len(state.get("tested", [])),
        "running": True,
        "last_result": state.get("last_result"),
        "last_error": state.get("last_error"),
    }
    status.update(extra)
    atomic_json(STATUS_FILE, status)


def opener():
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def login():
    op = opener()
    data = urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode("utf-8")
    req = urllib.request.Request(API.rstrip("/") + "/login", data=data)
    with op.open(req, timeout=20) as resp:
        resp.read()
    return op


def request_json(op, path, payload=None, method=None, timeout=120):
    data = None
    headers = {"ngrok-skip-browser-warning": "true"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API.rstrip("/") + path, data=data, headers=headers, method=method)
    with op.open(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "ignore")
        return json.loads(body) if body else {}


def free_memory_gb():
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MemoryStatus()
    stat.dwLength = ctypes.sizeof(MemoryStatus)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return stat.ullAvailPhys / (1024 ** 3)
    return None


def safe_float(value, default=0.0):
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return default


def pnl_to_daily(pnl):
    values = []
    for item in pnl or []:
        if isinstance(item, dict):
            item = item.get("value", item.get("pnl", item.get("cum", item.get("y"))))
        x = safe_float(item, None)
        if x is not None:
            values.append(float(x))
    if len(values) < 2:
        return []
    return [values[i] - values[i - 1] for i in range(1, len(values))]


def corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return None
    aa = a[-n:]
    bb = b[-n:]
    ma = sum(aa) / n
    mb = sum(bb) / n
    va = 0.0
    vb = 0.0
    cov = 0.0
    for x, y in zip(aa, bb):
        dx = x - ma
        dy = y - mb
        va += dx * dx
        vb += dy * dy
        cov += dx * dy
    if va <= 1e-18 or vb <= 1e-18:
        return None
    return cov / math.sqrt(va * vb)


def abs_corr(a, b):
    c = corr(a, b)
    return abs(c) if c is not None else 0.0


def expression_themes(expr):
    low = (expr or "").lower()
    found = []
    for theme, keys in THEMES.items():
        if any(k in low for k in keys):
            found.append(theme)
    return found or ["other"]


def load_candidates():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, expression, type, metrics_json, pnl_json FROM alpha_history "
        "WHERE COALESCE(type,'alpha')='alpha' "
        "AND ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01 "
        "AND pnl_json IS NOT NULL AND length(pnl_json) > 5"
    ).fetchall()
    con.close()

    candidates = []
    seen_expr = set()
    for row in rows:
        expr = (row["expression"] or "").strip()
        if not expr or expr in seen_expr:
            continue
        if expr.startswith("superalpha(") or expr.startswith("lgb("):
            continue
        seen_expr.add(expr)
        try:
            metrics = json.loads(row["metrics_json"] or "{}")
            pnl = json.loads(row["pnl_json"] or "[]")
        except Exception:
            continue
        daily = pnl_to_daily(pnl)
        if len(daily) < 30:
            continue
        ic = safe_float(metrics.get("pearson_ic"))
        abs_ic = abs(ic)
        if abs_ic <= 0.01:
            continue
        candidates.append({
            "id": row["id"],
            "expression": expr,
            "ic": ic,
            "abs_ic": abs_ic,
            "annual": safe_float(metrics.get("annual_excess")),
            "sharpe": safe_float(metrics.get("sharpe")),
            "fitness": safe_float(metrics.get("fitness")),
            "daily": daily,
            "themes": expression_themes(expr),
        })
    return candidates


def load_existing_combo_records():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, expression, metrics_json, pnl_json FROM alpha_history "
        "WHERE COALESCE(type,'alpha')='superalpha' "
        "AND ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) >= ? "
        "AND pnl_json IS NOT NULL AND length(pnl_json) > 5",
        (QUALIFIED_ABS_IC,),
    ).fetchall()
    con.close()
    records = []
    for row in rows:
        expr = row["expression"] or ""
        if not (expr.startswith("lgb(train=2020-2022") or expr.startswith("superalpha(")):
            continue
        try:
            metrics = json.loads(row["metrics_json"] or "{}")
            pnl = json.loads(row["pnl_json"] or "[]")
        except Exception:
            continue
        daily = pnl_to_daily(pnl)
        if len(daily) >= 30:
            records.append({
                "id": row["id"],
                "expression_hash": hashlib.sha1(expr.encode("utf-8")).hexdigest()[:12],
                "ic": safe_float(metrics.get("pearson_ic")),
                "annual": safe_float(metrics.get("annual_excess")),
                "sharpe": safe_float(metrics.get("sharpe")),
                "fitness": safe_float(metrics.get("fitness")),
                "daily": daily,
                "source": "history_seed",
                "time": now(),
            })
    return records


def seed_existing_qualified(state):
    known = {q.get("id") for q in state.get("qualified", []) if q.get("id")}
    added = 0
    for rec in load_existing_combo_records():
        if rec["id"] in known:
            continue
        max_c = max_combo_corr(rec["daily"], state)
        if max_c <= MAX_COMBO_CORR:
            rec["max_corr_to_qualified"] = round(max_c, 4)
            state.setdefault("qualified", []).append(rec)
            known.add(rec["id"])
            added += 1
    return added


def make_configs():
    theme_sets = [
        ("liquidity_reversal", ["liquidity", "reversal"]),
        ("liquidity_volatility", ["liquidity", "volatility"]),
        ("reversal_microstructure", ["reversal", "microstructure"]),
        ("momentum_volatility", ["momentum", "volatility"]),
        ("microstructure_liquidity", ["microstructure", "liquidity"]),
        ("volatility_size", ["volatility", "size"]),
        ("balanced_all", ["balanced"]),
        ("liquidity", ["liquidity"]),
        ("reversal", ["reversal"]),
        ("volatility", ["volatility"]),
        ("microstructure", ["microstructure"]),
    ]
    priority = []
    priority_themes = [
        ("balanced_all", ["balanced"]),
        ("reversal_microstructure", ["reversal", "microstructure"]),
        ("momentum_volatility", ["momentum", "volatility"]),
        ("microstructure_liquidity", ["microstructure", "liquidity"]),
        ("liquidity_reversal", ["liquidity", "reversal"]),
        ("liquidity_volatility", ["liquidity", "volatility"]),
    ]
    high_ic_themes = [
        ("high_ic_liquidity_volatility", ["liquidity", "volatility"]),
        ("high_ic_liquidity_reversal", ["liquidity", "reversal"]),
        ("high_ic_reversal_microstructure", ["reversal", "microstructure"]),
        ("high_ic_balanced", ["balanced"]),
        ("high_ic_momentum_volatility", ["momentum", "volatility"]),
        ("high_ic_microstructure_liquidity", ["microstructure", "liquidity"]),
    ]
    for keep_count in [8, 12, 16, 20]:
        for max_seed_corr in [0.70, 0.65, 0.55, 0.45]:
            for max_corr_single in [0.55, 0.65, 0.70, 0.45]:
                for name, themes in high_ic_themes:
                    for style in ["high_ic", "positive_high_ic", "negative_high_ic"]:
                        priority.append({
                            "mode": "lgb",
                            "theme_name": name,
                            "themes": themes,
                            "style": style,
                            "single_max_corr": max_corr_single,
                            "keep_count": keep_count,
                            "anti_corr": True,
                            "max_seed_corr": max_seed_corr,
                        })
    for keep_count in [30, 36, 24, 45]:
        for max_seed_corr in [0.45, 0.55, 0.35]:
            for max_corr_single in [0.55, 0.65, 0.70]:
                for name, themes in priority_themes:
                    for style in ["abs", "low_ic", "positive", "negative"]:
                        priority.append({
                            "mode": "lgb",
                            "theme_name": name,
                            "themes": themes,
                            "style": style,
                            "single_max_corr": max_corr_single,
                            "keep_count": keep_count,
                            "anti_corr": True,
                            "max_seed_corr": max_seed_corr,
                        })
    for keep_count in [30, 24, 36, 45]:
        for max_corr_single in [0.65, 0.70, 0.55]:
            for name, themes in priority_themes:
                for style in ["abs", "positive", "low_ic", "negative"]:
                    priority.append({
                        "mode": "lgb",
                        "theme_name": name,
                        "themes": themes,
                        "style": style,
                        "single_max_corr": max_corr_single,
                        "keep_count": keep_count,
                        "anti_corr": False,
                    })
    configs = []
    styles = ["abs", "positive", "negative", "low_ic"]
    for max_corr_single in [0.55, 0.65, 0.70, 0.45]:
        for keep_count in [18, 24, 30, 36, 45, 60, 12]:
            for name, themes in theme_sets:
                for style in styles:
                    configs.append({
                        "mode": "lgb",
                        "theme_name": name,
                        "themes": themes,
                        "style": style,
                        "single_max_corr": max_corr_single,
                        "keep_count": keep_count,
                        "anti_corr": False,
                    })
    seen = set()
    merged = []
    for cfg in priority + configs:
        key = (
            cfg["theme_name"], tuple(cfg["themes"]), cfg["style"],
            cfg["single_max_corr"], cfg["keep_count"],
            cfg.get("anti_corr", False), cfg.get("max_seed_corr"),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(cfg)
    return merged


CONFIGS = make_configs()


def seed_corr(cand, state):
    worst = 0.0
    for q in state.get("qualified", []):
        q_daily = q.get("daily") or []
        worst = max(worst, abs_corr(cand["daily"], q_daily))
    return worst


def score_candidate(cand, style, rng, cfg, state):
    if style in ("high_ic", "positive_high_ic", "negative_high_ic"):
        score = cand["abs_ic"] * 180.0
        score += max(cand["annual"], -2.0) * 0.08
        score += max(cand["fitness"], -20.0) * 0.006
        score += min(abs(cand["sharpe"]), 20.0) * 0.006
        if cfg.get("anti_corr"):
            score -= seed_corr(cand, state) * 0.8
        return score + rng.random() * 0.02

    score = cand["abs_ic"] * 100.0
    score += max(cand["annual"], -2.0) * 0.05
    score += max(cand["fitness"], -20.0) * 0.004
    score += min(abs(cand["sharpe"]), 20.0) * 0.003
    if style == "positive" and cand["ic"] <= 0:
        score -= 20.0
    elif style == "negative" and cand["ic"] >= 0:
        score -= 20.0
    elif style == "low_ic":
        score = (0.035 - min(cand["abs_ic"], 0.035)) * 30.0 + cand["abs_ic"] * 35.0
    if cfg.get("anti_corr"):
        score -= seed_corr(cand, state) * 1.4
    return score + rng.random() * 0.035


def candidate_allowed(cand, cfg):
    style = cfg["style"]
    if style in ("positive", "positive_high_ic") and cand["ic"] <= 0:
        return False
    if style in ("negative", "negative_high_ic") and cand["ic"] >= 0:
        return False
    if style == "low_ic" and cand["abs_ic"] > 0.03:
        return False
    if style in ("high_ic", "positive_high_ic", "negative_high_ic") and cand["abs_ic"] < 0.022:
        return False
    themes = cfg["themes"]
    if "balanced" in themes:
        return True
    return any(t in cand["themes"] for t in themes)


def select_basket(candidates, cfg, cycle, state):
    rng = random.Random(20260526 + cycle * 17 + cfg["keep_count"])
    pool = [c for c in candidates if candidate_allowed(c, cfg)]
    if len(pool) < max(6, cfg["keep_count"] // 3):
        pool = candidates[:]
    if cfg.get("anti_corr") and state.get("qualified"):
        max_seed_corr = float(cfg.get("max_seed_corr", 0.55))
        filtered = [c for c in pool if seed_corr(c, state) <= max_seed_corr]
        if len(filtered) >= max(6, cfg["keep_count"] // 2):
            pool = filtered
    scored = sorted(pool, key=lambda c: score_candidate(c, cfg["style"], rng, cfg, state), reverse=True)

    selected = []
    theme_counts = {k: 0 for k in THEMES}
    selected_max = 0.0
    for cand in scored:
        if len(selected) >= cfg["keep_count"]:
            break
        if "balanced" in cfg["themes"]:
            known_theme_counts = [theme_counts.get(t, 0) for t in cand["themes"] if t in theme_counts]
            rare_bonus = min(known_theme_counts) if known_theme_counts else 0
            if rare_bonus > 0 and rng.random() < min(0.55, rare_bonus * 0.08):
                continue
        worst = 0.0
        too_close = False
        for kept in selected:
            c = abs_corr(cand["daily"], kept["daily"])
            worst = max(worst, c)
            if c > cfg["single_max_corr"]:
                too_close = True
                break
        if too_close:
            continue
        selected.append(cand)
        selected_max = max(selected_max, worst)
        for theme in cand["themes"]:
            if theme in theme_counts:
                theme_counts[theme] += 1
    return selected, selected_max, theme_counts


def combo_signature(cfg, selected):
    body = "|".join(x["expression"] for x in selected)
    raw = json.dumps({
        "mode": cfg["mode"],
        "theme": cfg["theme_name"],
        "style": cfg["style"],
        "single_max_corr": cfg["single_max_corr"],
        "keep": cfg["keep_count"],
        "anti_corr": cfg.get("anti_corr", False),
        "max_seed_corr": cfg.get("max_seed_corr"),
        "body": body,
    }, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def max_combo_corr(daily, state):
    worst = 0.0
    for q in state.get("qualified", []):
        q_daily = q.get("daily") or []
        c = abs_corr(daily, q_daily)
        worst = max(worst, c)
    return worst


def delete_history(op, history_id):
    if not history_id:
        return False
    try:
        request_json(op, f"/api/alpha/history/{history_id}", method="DELETE", timeout=30)
        return True
    except Exception:
        return False


def start_lgb(op, expressions, cfg):
    payload = {
        "expressions": expressions,
        "max_lgb_features": min(50, max(10, len(expressions))),
        "max_train_samples": 80000,
        "train_matrix_budget_mb": 32,
        "predict_matrix_budget_mb": 3,
        "predict_chunk_days": 15,
        "sub_alpha_limit": 4,
        "oos_cache_feature_limit": 0,
        "n_estimators": 35,
        "purge_days": 5,
    }
    if len(expressions) >= 30:
        payload["max_train_samples"] = 60000
        payload["train_matrix_budget_mb"] = 28
        payload["n_estimators"] = 28
    log(
        f"lgb sync features={len(expressions)} "
        f"max_train_samples={payload['max_train_samples']} "
        f"n_estimators={payload['n_estimators']}"
    )
    # The Flask endpoint waits for its worker and kills it in a finally block.
    # Keep the client timeout longer than the server-side 10 minute ceiling so
    # an early disconnect cannot leave a high-memory LGB worker behind.
    result = request_json(op, "/api/superalpha/lgb/start", payload, timeout=660)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result


def run_one_combo(state):
    seed_existing_qualified(state)
    candidates = load_candidates()
    if len(candidates) < 10:
        raise RuntimeError(f"not enough candidates: {len(candidates)}")

    state["cycle"] = int(state.get("cycle", 0)) + 1
    cycle = state["cycle"]
    free_gb = free_memory_gb()
    if free_gb is not None and free_gb < MIN_FREE_GB_LGB:
        write_status(state, free_gb=round(free_gb, 2), phase="low_memory_wait", candidates=len(candidates))
        log(f"low memory wait free_gb={free_gb:.2f}")
        time.sleep(120)
        return

    tested = set(state.get("tested", []))
    chosen = None
    for offset in range(min(40, len(CONFIGS))):
        cfg = CONFIGS[(cycle + offset - 1) % len(CONFIGS)]
        selected, selected_max, theme_counts = select_basket(candidates, cfg, cycle + offset, state)
        if len(selected) < max(6, min(cfg["keep_count"], 12)):
            continue
        sig = combo_signature(cfg, selected)
        if sig in tested:
            continue
        chosen = (cfg, selected, selected_max, theme_counts, sig)
        break
    if chosen is None:
        raise RuntimeError("no fresh basket found")

    cfg, selected, selected_max, theme_counts, sig = chosen
    expressions = [x["expression"] for x in selected]
    ic_values = [x["ic"] for x in selected]
    write_status(
        state,
        phase="lgb_running",
        candidates=len(candidates),
        free_gb=round(free_gb, 2) if free_gb is not None else None,
        active_config={k: cfg.get(k) for k in ("theme_name", "style", "single_max_corr", "keep_count", "anti_corr", "max_seed_corr")},
        selected_count=len(selected),
        selected_single_max_corr=round(selected_max, 4),
        selected_avg_abs_ic=round(sum(abs(x) for x in ic_values) / len(ic_values), 4),
        selected_theme_counts={k: v for k, v in theme_counts.items() if v},
    )
    log(
        "start lgb "
        f"theme={cfg['theme_name']} style={cfg['style']} keep={len(selected)} "
        f"single_max_corr={cfg['single_max_corr']} selected_max_corr={selected_max:.4f} "
        f"avg_abs_ic={sum(abs(x) for x in ic_values) / len(ic_values):.4f}"
    )

    op = login()
    result = start_lgb(op, expressions, cfg)
    metrics = result.get("combined_metrics") or result.get("metrics") or {}
    ic = safe_float(metrics.get("pearson_ic"))
    annual = safe_float(metrics.get("annual_excess"))
    sharpe = safe_float(metrics.get("sharpe"))
    fitness = safe_float(metrics.get("fitness"))
    daily = pnl_to_daily(result.get("pnl_series") or metrics.get("pnl_series") or [])
    history_id = result.get("history_id")
    max_c = max_combo_corr(daily, state)
    qualified = abs(ic) >= QUALIFIED_ABS_IC and len(daily) >= 30 and max_c <= MAX_COMBO_CORR

    state.setdefault("tested", []).append(sig)
    last = {
        "time": now(),
        "signature": sig,
        "history_id": history_id,
        "qualified": qualified,
        "reject_reason": None,
        "mode": cfg["mode"],
        "theme_name": cfg["theme_name"],
        "style": cfg["style"],
        "single_max_corr": cfg["single_max_corr"],
        "anti_corr": cfg.get("anti_corr", False),
        "max_seed_corr": cfg.get("max_seed_corr"),
        "selected_count": len(selected),
        "selected_single_max_corr": round(selected_max, 4),
        "selected_avg_abs_ic": round(sum(abs(x) for x in ic_values) / len(ic_values), 4),
        "selected_theme_counts": {k: v for k, v in theme_counts.items() if v},
        "combo_max_corr_to_qualified": round(max_c, 4),
        "metrics": {
            "pearson_ic": round(ic, 4),
            "annual_excess": round(annual, 4),
            "sharpe": round(sharpe, 4),
            "fitness": round(fitness, 4),
            "max_drawdown": safe_float(metrics.get("max_drawdown")),
            "turnover": safe_float(metrics.get("turnover")),
        },
        "n_factors": result.get("n_factors"),
        "n_skipped_features": result.get("n_skipped_features"),
        "train_period": result.get("train_period"),
        "oos_period": result.get("oos_period"),
    }

    if qualified:
        state.setdefault("qualified", []).append({
            "id": history_id,
            "signature": sig,
            "time": now(),
            "ic": ic,
            "annual": annual,
            "sharpe": sharpe,
            "fitness": fitness,
            "daily": daily,
            "theme_name": cfg["theme_name"],
            "style": cfg["style"],
            "selected_count": len(selected),
            "combo_max_corr_to_qualified": round(max_c, 4),
        })
        log(
            f"QUALIFIED {len(state['qualified'])}/{TARGET_QUALIFIED} "
            f"ic={ic:.4f} annual={annual:.4f} sharpe={sharpe:.3f} maxcorr={max_c:.4f} id={history_id}"
        )
    else:
        reason = "abs_ic_below_0.05" if abs(ic) < QUALIFIED_ABS_IC else "combo_corr_above_0.70"
        last["reject_reason"] = reason
        if history_id:
            delete_history(op, history_id)
        log(
            f"reject {reason} ic={ic:.4f} annual={annual:.4f} "
            f"sharpe={sharpe:.3f} combo_maxcorr={max_c:.4f} id={history_id}"
        )

    state["last_result"] = last
    state["last_error"] = None
    write_status(state, phase="sleep", candidates=len(candidates))


def main():
    log("combo_builder start: OOS LGB combos, target_abs_ic>=0.05, max_combo_corr<=0.70")
    state = load_state()
    while True:
        if os.path.exists(PAUSE_FLAG):
            write_status(state, phase="paused")
            log("paused by combo_builder_paused.flag")
            time.sleep(60)
            continue
        try:
            run_one_combo(state)
            save_state(state)
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "ignore")[:500]
            except Exception:
                detail = str(e)
            msg = f"http_error {e.code}: {detail}"
            state["last_error"] = msg
            state.setdefault("errors", []).append({"time": now(), "error": msg})
            log(msg)
            write_status(state, phase="error")
            save_state(state)
            time.sleep(90)
        except Exception as e:
            msg = f"{type(e).__name__}: {str(e)[:500]}"
            state["last_error"] = msg
            state.setdefault("errors", []).append({"time": now(), "error": msg})
            log(msg)
            write_status(state, phase="error")
            save_state(state)
            time.sleep(90)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
