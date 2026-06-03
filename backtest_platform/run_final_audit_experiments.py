#!/usr/bin/env python3
"""Run the final YYB audit matrix without loading a second data pipeline.

The script waits for background LGB work to finish, pauses combo_builder, then
uses the Flask API sequentially. Selection is based on IS metrics only. PnL
correlations use absolute Pearson correlation of daily changes in cumulative
PnL, matching the platform's history correlation convention.
"""

import datetime as dt
import json
import math
import os
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

import numpy as np
import psutil


BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "backtest.db"
LOG_DIR = pathlib.Path(r"D:\yyb\logs")
OUT_DIR = BASE / "experiment_results"
PYTHON = r"python"
API = "http://127.0.0.1:5000"
PUBLIC_LOGIN = "https://remark-glance-tweet.ngrok-free.dev/login"
PAUSE_FLAG = LOG_DIR / "combo_builder_paused.flag"
LOG = LOG_DIR / "final_audit_runner.log"
JSONL = OUT_DIR / "final_audit_experiments.jsonl"
FINAL = OUT_DIR / "final_audit_results.json"
MIN_FREE_GB = 3.0
RESUME_FREE_GB = 4.0
NEUTRALIZATIONS = ("none", "market_cap", "market_cap_regression", "beta", "market_cap_beta")
USER = os.environ.get("YYB_USER", "admin")
PASSWORD = os.environ.get("YYB_PASSWORD", "quant2026")


def load_completed():
    completed = {}
    if not JSONL.exists():
        return completed
    with JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("label"):
                completed[row["label"]] = row
    return completed


COMPLETED = load_completed()

THEMES = {
    "reversal": ["rev_", "reversal", "gap", "auction", "abnormal_vol_rev", "close_location", "shadow", "doji"],
    "momentum": ["ret_", "cumret", "momentum", "mom_", "trend", "breakout", "ts_delta"],
    "liquidity": ["turnover", "volume", "vol_ratio", "volume_profile", "volume_breakout", "amihud", "liquidity", "dollar", "amount"],
    "volatility": ["vol", "downside", "max_dd", "beta", "skew", "kurt", "bollinger", "rsi", "range", "atr"],
    "microstructure": ["vwap", "intraday", "smart_money", "body", "upper_shadow", "lower_shadow", "close_location", "auction"],
    "size": ["market_cap", "mcap", "size"],
}


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def log(message):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{now()}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def append_jsonl(row):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_float(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def daily_from_cumulative(values):
    try:
        arr = np.asarray(values or [], dtype=float)
    except Exception:
        return np.asarray([], dtype=float)
    arr = arr[np.isfinite(arr)]
    return np.diff(arr) if arr.size >= 3 else np.asarray([], dtype=float)


def abs_corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return 0.0
    aa = np.asarray(a[-n:], dtype=float)
    bb = np.asarray(b[-n:], dtype=float)
    valid = np.isfinite(aa) & np.isfinite(bb)
    if valid.sum() < 30 or np.nanstd(aa[valid]) <= 1e-12 or np.nanstd(bb[valid]) <= 1e-12:
        return 0.0
    return abs(float(np.corrcoef(aa[valid], bb[valid])[0, 1]))


def proc_rows():
    rows = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "memory_info"]):
        try:
            rows.append({
                "pid": p.info["pid"],
                "name": p.info.get("name") or "",
                "cmd": " ".join(p.info.get("cmdline") or []),
                "rss_mb": round(p.info["memory_info"].rss / 1024 ** 2, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return rows


def matching_pids(term):
    return [row["pid"] for row in proc_rows() if term in row["cmd"]]


def free_gb():
    return psutil.virtual_memory().available / 1024 ** 3


def url_ok(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"ngrok-skip-browser-warning": "true"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_health(timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if url_ok(API + "/login", 5) and url_ok(PUBLIC_LOGIN, 8):
            return
        time.sleep(3)
    raise RuntimeError("Flask or ngrok health check failed")


def stop_matching(term):
    for pid in matching_pids(term):
        try:
            psutil.Process(pid).kill()
            log(f"stopped pid={pid} term={term}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def wait_for_background_lgb(timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        pids = matching_pids("lgb_worker.py")
        if not pids:
            return
        log(f"waiting for active lgb workers={pids} free_gb={free_gb():.2f}")
        time.sleep(30)
    raise TimeoutError("background LGB worker did not finish within 15 minutes")


def pause_builder():
    PAUSE_FLAG.write_text(f"{now()} final audit owns experiment slot\n", encoding="utf-8")
    stop_matching("combo_builder.py")
    time.sleep(3)


def restart_flask():
    wait_for_background_lgb()
    stop_matching(" app.py")
    time.sleep(3)
    out = (LOG_DIR / "app_stdout.log").open("a", encoding="utf-8")
    err = (LOG_DIR / "app_stderr.log").open("a", encoding="utf-8")
    subprocess.Popen([PYTHON, "-u", "app.py"], cwd=str(BASE), stdout=out, stderr=err)
    wait_health(180)
    log("Flask restarted with audit patches")


def ensure_memory():
    available = free_gb()
    if available >= MIN_FREE_GB:
        return
    log(f"memory pressure free_gb={available:.2f}; restarting Flask before next audit request")
    restart_flask()
    deadline = time.time() + 180
    while free_gb() < RESUME_FREE_GB and time.time() < deadline:
        time.sleep(5)
    log(f"memory recovered free_gb={free_gb():.2f}")


def login():
    jar = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode("utf-8")
    with op.open(urllib.request.Request(API + "/login", data=data), timeout=20) as resp:
        resp.read()
    return op


def request_json(op, path, payload=None, timeout=240):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    with op.open(urllib.request.Request(API + path, data=data, headers=headers), timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "ignore")
        return json.loads(body) if body else {}


def parse_pnl(raw):
    try:
        data = json.loads(raw or "[]")
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("pnl_series") or data.get("_pnl_series") or data.get("oos_pnl") or []
    return data if isinstance(data, list) else []


def theme(expr):
    low = (expr or "").lower()
    scores = []
    for name, keys in THEMES.items():
        score = sum(1 for key in set(keys) if key in low)
        if score:
            scores.append((score, name))
    scores.sort(reverse=True)
    return scores[0][1] if scores else "other"


def load_single_factors():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, expression, metrics_json, pnl_json FROM alpha_history "
        "WHERE COALESCE(type,'alpha')='alpha' "
        "AND CAST(json_extract(metrics_json,'$.is_pearson_ic') AS REAL) > 0.01 "
        "AND pnl_json IS NOT NULL AND length(pnl_json)>5"
    ).fetchall()
    con.close()
    out = []
    for aid, expr, metrics_json, pnl_json in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            continue
        if safe_float(metrics.get("n_days")) < 30:
            continue
        daily = daily_from_cumulative(parse_pnl(pnl_json))
        if len(daily) < 30:
            continue
        out.append({
            "id": aid,
            "expression": expr or "",
            "theme": theme(expr),
            "is_sharpe": safe_float(metrics.get("is_sharpe")),
            "is_ic": safe_float(metrics.get("is_pearson_ic")),
            "oos_sharpe": safe_float(metrics.get("sharpe")),
            "daily": daily,
        })
    out.sort(key=lambda x: (-x["is_sharpe"], -x["is_ic"], x["id"]))
    return out


def greedy(factors, max_corr, count=10):
    selected = []
    for cand in factors:
        if all(abs_corr(cand["daily"], old["daily"]) < max_corr for old in selected):
            selected.append(cand)
        if len(selected) >= count:
            break
    return selected


def latest_superalpha_id():
    con = sqlite3.connect(DB)
    row = con.execute(
        "SELECT id FROM alpha_history WHERE type='superalpha' ORDER BY timestamp DESC, rowid DESC LIMIT 1"
    ).fetchone()
    con.close()
    return row[0] if row else None


def call_combo(op, label, ids, method="equal", neutralize="none", family="confirmatory", metadata=None):
    if label in COMPLETED:
        log(f"reuse completed {label}")
        return COMPLETED[label]
    ensure_memory()
    before = latest_superalpha_id()
    started = now()
    payload = {
        "alpha_ids": ids,
        "method": method,
        "neutralize": neutralize,
        "oos_only": True,
        "sub_alpha_limit": min(len(ids), 10),
    }
    log(f"run {label} n={len(ids)} method={method} neutralize={neutralize}")
    data = request_json(op, "/api/superalpha", payload, timeout=420)
    after = latest_superalpha_id()
    metrics = data.get("combined_metrics") or {}
    row = {
        "time": started,
        "label": label,
        "family": family,
        "method": method,
        "neutralize": neutralize,
        "alpha_ids": ids,
        "history_id": after if after != before else None,
        "success": bool(data.get("success")),
        "n_requested": data.get("n_requested_factors"),
        "n_valid": data.get("n_valid_factors"),
        "n_skipped": data.get("n_skipped_features"),
        "skipped_features": data.get("skipped_features") or [],
        "metrics": {key: metrics.get(key) for key in (
            "pearson_ic", "icir", "fitness", "annual_excess", "sharpe",
            "max_drawdown", "turnover", "win_rate", "n_days",
        )},
        "pnl_series": metrics.get("pnl_series") or [],
        "metadata": metadata or {},
        "error": data.get("error"),
    }
    append_jsonl(row)
    COMPLETED[label] = row
    log(
        f"done {label} success={row['success']} valid={row['n_valid']}/{row['n_requested']} "
        f"sharpe={safe_float(row['metrics'].get('sharpe')):.3f}"
    )
    return row


def final_low_corr_superalphas(max_corr=0.5, min_sharpe=10.0):
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, expression, metrics_json, pnl_json, timestamp FROM alpha_history "
        "WHERE type='superalpha' AND pnl_json IS NOT NULL AND length(pnl_json)>5"
    ).fetchall()
    con.close()
    candidates = []
    for aid, expr, metrics_json, pnl_json, timestamp in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            continue
        sharpe = safe_float(metrics.get("sharpe"))
        daily = daily_from_cumulative(parse_pnl(pnl_json))
        if sharpe <= min_sharpe or len(daily) < 30:
            continue
        candidates.append({
            "id": aid, "expression": expr or "", "timestamp": timestamp,
            "sharpe": sharpe, "ic": safe_float(metrics.get("pearson_ic")),
            "fitness": safe_float(metrics.get("fitness")),
            "turnover": safe_float(metrics.get("turnover")),
            "daily": daily,
        })
    candidates.sort(key=lambda x: (-x["sharpe"], x["id"]))
    selected = []
    for cand in candidates:
        corr_values = [abs_corr(cand["daily"], old["daily"]) for old in selected]
        if all(c < max_corr for c in corr_values):
            row = {k: v for k, v in cand.items() if k != "daily"}
            row["max_corr_to_selected"] = max(corr_values) if corr_values else 0.0
            selected.append({**cand, **row})
    return [{k: v for k, v in row.items() if k != "daily"} for row in selected]


def run():
    log("final audit runner start")
    wait_health()
    wait_for_background_lgb()
    pause_builder()
    restart_flask()
    op = login()
    factors = load_single_factors()
    results = []
    selections = {}
    log(f"loaded eligible single factors={len(factors)}")

    # Confirmatory matrix: all ranking uses IS metrics, with fixed PnL-correlation thresholds.
    top5 = factors[:5]
    top10 = factors[:10]
    for name, basket in [("top_is_sharpe_n5", top5), ("top_is_sharpe_n10", top10)]:
        selections[name] = [x["id"] for x in basket]
        for method in ("equal", "icir", "ridge"):
            for neutralize in NEUTRALIZATIONS:
                results.append(call_combo(op, f"{name}_{method}_{neutralize}", selections[name], method, neutralize))

    for threshold in (0.3, 0.5, 0.7):
        key = f"greedy_corr_{threshold:.1f}_n10"
        basket = greedy(factors, threshold, 10)
        selections[key] = [x["id"] for x in basket]
        metadata = {"threshold": threshold, "selected_count": len(basket)}
        for method in ("equal", "icir", "ridge"):
            for neutralize in NEUTRALIZATIONS:
                results.append(call_combo(op, f"{key}_{method}_{neutralize}", selections[key], method, neutralize, metadata=metadata))

    # Exploratory nesting: construct style-specific L1 caches, then L2 and L3 caches.
    layer1 = {}
    for style in ("reversal", "momentum", "microstructure", "liquidity", "volatility"):
        pool = [x for x in factors if x["theme"] == style]
        basket = greedy(pool, 0.7, 5)
        if len(basket) < 3:
            continue
        ids = [x["id"] for x in basket]
        style_rows = []
        for method in ("equal", "icir", "ridge"):
            style_rows.append(call_combo(
                op, f"nest_l1_{style}_{method}_market_cap", ids, method, "market_cap",
                family="exploratory_nesting", metadata={"style": style, "layer": 1},
            ))
        results.extend(style_rows)
        valid = [row for row in style_rows if row["success"] and row["history_id"]]
        if valid:
            layer1[style] = max(valid, key=lambda row: safe_float(row["metrics"].get("sharpe")))

    layer1_ids = [row["history_id"] for row in layer1.values()]
    layer2 = []
    if len(layer1_ids) >= 2:
        for method in ("equal", "icir", "ridge"):
            for neutralize in NEUTRALIZATIONS:
                layer2.append(call_combo(
                    op, f"nest_l2_{method}_{neutralize}", layer1_ids, method, neutralize,
                    family="exploratory_nesting", metadata={"layer": 2, "styles": list(layer1)},
                ))
        results.extend(layer2)

    valid_l2 = [row for row in layer2 if row["success"] and row["history_id"]]
    if valid_l2:
        best_l2 = max(valid_l2, key=lambda row: safe_float(row["metrics"].get("sharpe")))
        strict = final_low_corr_superalphas(0.5, 10.0)[:2]
        l3_ids = [best_l2["history_id"]] + [row["id"] for row in strict if row["id"] != best_l2["history_id"]]
        if len(l3_ids) >= 2:
            for method in ("equal", "icir", "ridge"):
                for neutralize in NEUTRALIZATIONS:
                    results.append(call_combo(
                        op, f"nest_l3_{method}_{neutralize}", l3_ids, method, neutralize,
                        family="exploratory_nesting", metadata={"layer": 3},
                    ))

    frozen = {
        "generated_at": now(),
        "protocol": {
            "selection_window": "IS 2020-2022 only",
            "evaluation_window": "OOS 2023 only",
            "correlation": "absolute Pearson correlation of daily changes in cumulative PnL",
            "confirmatory_note": "Confirmatory rows use frozen IS selection rules. Nested rows are exploratory.",
        },
        "single_factor_count": len(factors),
        "selections": selections,
        "results": results,
        "strict_superalpha_selection": final_low_corr_superalphas(0.5, 10.0),
    }
    atomic_json(FINAL, frozen)
    log(
        f"final audit complete results={len(results)} "
        f"strict_gt10_lowcorr={len(frozen['strict_superalpha_selection'])}"
    )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        log(f"fatal {type(exc).__name__}: {exc}")
        raise
