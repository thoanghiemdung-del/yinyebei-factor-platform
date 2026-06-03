#!/usr/bin/env python3
"""Night loop for low-correlation equal-weight and LGB combo tests."""
import datetime as dt
import hashlib
import ctypes
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

API = "http://127.0.0.1:5000"
USER = os.environ.get("YYB_USER", "admin")
PASSWORD = os.environ.get("YYB_PASSWORD", "quant2026")
BASE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = r"D:\yyb\logs"
LOG = os.path.join(LOG_DIR, "night_combo_tester.log")
STATE_FILE = os.path.join(LOG_DIR, "night_combo_tester_state.json")
INTERVAL = int(os.environ.get("YYB_COMBO_INTERVAL", "1200"))

CONFIGS = [
    {"max_corr": 0.50, "keep_count": 5, "mode": "equal"},
    {"max_corr": 0.65, "keep_count": 15, "mode": "lgb"},
    {"max_corr": 0.70, "keep_count": 8, "mode": "equal"},
    {"max_corr": 0.60, "keep_count": 20, "mode": "lgb"},
]


def log(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tested": [], "cycle": 0}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def opener():
    cj = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def request_json(op, path, payload=None, timeout=120):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers)
    with op.open(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def login():
    op = opener()
    payload = urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode("utf-8")
    req = urllib.request.Request(API + "/login", data=payload)
    with op.open(req, timeout=20) as resp:
        resp.read()
    return op


def signature(mode, cfg, expressions):
    joined = "\n".join(expressions)
    h = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]
    return f"{mode}:{cfg['max_corr']}:{cfg['keep_count']}:{h}"


def metric_summary(metrics):
    keys = ["pearson_ic", "rank_ic", "annual_excess", "sharpe", "max_drawdown", "turnover"]
    return {k: metrics.get(k) for k in keys if k in metrics}


def free_memory_gb():
    class MEMORYSTATUSEX(ctypes.Structure):
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

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return stat.ullAvailPhys / (1024 ** 3)
    return None


def run_cycle(state):
    state["cycle"] = int(state.get("cycle", 0)) + 1
    cfg = CONFIGS[(state["cycle"] - 1) % len(CONFIGS)]
    op = login()
    greedy = request_json(op, "/api/alpha/history/corr_greedy", {
        "max_corr": cfg["max_corr"],
        "keep_count": cfg["keep_count"],
    }, timeout=120)
    ids = greedy.get("ids") or []
    expressions = greedy.get("expressions") or []
    if not ids or not expressions:
        raise RuntimeError("corr_greedy returned empty selection")

    mode = cfg["mode"]
    free_gb = free_memory_gb()
    if free_gb is not None:
        if mode == "lgb" and free_gb < 2.5:
            log(f"skip lgb low_memory free_gb={free_gb:.2f} maxcorr={cfg['max_corr']} keep={len(ids)}")
            return
        if mode == "equal" and free_gb < 1.5:
            log(f"skip equal low_memory free_gb={free_gb:.2f} maxcorr={cfg['max_corr']} keep={len(ids)}")
            return
    sig = signature(mode, cfg, expressions)
    tested = set(state.get("tested", []))
    if sig in tested:
        log(f"skip duplicate mode={mode} maxcorr={cfg['max_corr']} keep={len(ids)} sig={sig}")
        return

    if mode == "equal":
        result = request_json(op, "/api/superalpha", {
            "alpha_ids": ids,
            "neutralize": "none",
            "sub_alpha_limit": 0,
        }, timeout=180)
        metrics = result.get("combined_metrics") or result.get("metrics") or {}
    else:
        result = request_json(op, "/api/superalpha/lgb", {
            "expressions": expressions,
            "max_lgb_features": 80,
            "max_train_samples": 120000,
            "train_matrix_budget_mb": 32,
            "predict_matrix_budget_mb": 4,
            "sub_alpha_limit": 4,
            "oos_cache_feature_limit": 12,
            "n_estimators": 45,
            "purge_days": 5,
        }, timeout=1200)
        metrics = result.get("combined_metrics") or {}

    summary = metric_summary(metrics)
    state.setdefault("tested", []).append(sig)
    state["tested"] = state["tested"][-200:]
    state["last_result"] = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "max_corr": cfg["max_corr"],
        "keep_count": cfg["keep_count"],
        "selected_count": len(ids),
        "selected_max_corr": greedy.get("selected_max_corr"),
        "avg_ic": greedy.get("avg_ic"),
        "metrics": summary,
        "signature": sig,
    }
    log(
        f"{mode} done maxcorr={cfg['max_corr']} keep={len(ids)} "
        f"sel_maxcorr={greedy.get('selected_max_corr')} avg_ic={greedy.get('avg_ic')} "
        f"metrics={summary}"
    )


def main():
    log("night combo tester start")
    state = load_state()
    while True:
        try:
            run_cycle(state)
            save_state(state)
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")[:300]
            except Exception:
                detail = str(e)
            log(f"http_error {e.code}: {detail}")
        except Exception as e:
            log(f"error {type(e).__name__}: {str(e)[:300]}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
