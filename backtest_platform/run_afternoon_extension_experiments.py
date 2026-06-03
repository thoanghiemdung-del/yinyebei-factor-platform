#!/usr/bin/env python3
"""Sequential low-memory afternoon search for diverse OOS alpha candidates.

This is an exploratory search runner. It never submits external Alpha and never loads a
second pipeline. Each API result is persisted before the next request. Selection uses
absolute Pearson correlation of daily changes in stored cumulative OOS PnL.
"""

import datetime as dt
import json
import math
import os
import pathlib
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

import numpy as np
import psutil


BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "backtest.db"
OUT = BASE / "experiment_results"
LOG_DIR = pathlib.Path(r"D:\yyb\logs")
LOG = LOG_DIR / "afternoon_extension_runner.log"
JSONL = OUT / "afternoon_extension_experiments.jsonl"
STATUS = OUT / "afternoon_extension_status.json"
FINAL = OUT / "afternoon_extension_results.json"
PAUSE_FLAG = LOG_DIR / "combo_builder_paused.flag"
PYTHON = r"python"
API = "http://127.0.0.1:5000"
USER = os.environ.get("YYB_USER", "admin")
PASSWORD = os.environ.get("YYB_PASSWORD", "quant2026")
MIN_FREE_GB = 0.7
RESUME_FREE_GB = 1.0
TARGET_STRICT = 12
MIN_EXPERIMENTS = 50
NEUTRALS = ("none", "market_cap", "beta", "market_cap_beta", "market_cap_regression")

THEMES = {
    "reversal": ("rev_", "reversal", "gap", "auction", "abnormal_vol_rev", "bollinger", "rsi"),
    "momentum": ("ret_", "cumret", "momentum", "trend", "breakout", "ts_delta"),
    "liquidity": ("turnover", "volume", "amihud", "dollar", "amount", "liquidity"),
    "microstructure": ("vwap", "intraday", "auction", "shadow", "body", "close_location"),
    "volatility": ("vol", "beta", "max_dd", "downside", "skew", "kurt", "range", "atr"),
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
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(row):
    OUT.mkdir(parents=True, exist_ok=True)
    with JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def completed_rows():
    rows = {}
    if JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("label"):
                rows[row["label"]] = row
    return rows


DONE = completed_rows()


def safe_float(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def parse_pnl(raw):
    try:
        values = json.loads(raw or "[]")
    except Exception:
        return []
    if isinstance(values, dict):
        values = values.get("pnl_series") or values.get("_pnl_series") or values.get("oos_pnl") or []
    return values if isinstance(values, list) else []


def daily(values):
    try:
        arr = np.asarray(values or [], dtype=float)
    except Exception:
        return np.asarray([], dtype=float)
    return np.diff(arr) if arr.size >= 3 else np.asarray([], dtype=float)


def abs_corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return 1.0
    aa, bb = np.asarray(a[-n:]), np.asarray(b[-n:])
    valid = np.isfinite(aa) & np.isfinite(bb)
    if valid.sum() < 30 or np.std(aa[valid]) <= 1e-12 or np.std(bb[valid]) <= 1e-12:
        return 1.0
    return abs(float(np.corrcoef(aa[valid], bb[valid])[0, 1]))


def free_gb():
    return psutil.virtual_memory().available / 1024 ** 3


def url_ok(path="/login", timeout=8):
    try:
        with urllib.request.urlopen(API + path, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def process_rows():
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            yield process.info["pid"], process.info.get("name") or "", " ".join(process.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue


def stop_flask():
    for pid, name, cmd in process_rows():
        if name.lower() == "python.exe" and " app.py" in cmd:
            try:
                psutil.Process(pid).kill()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass


def restart_flask():
    log(f"restart Flask for memory recovery free_gb={free_gb():.2f}")
    stop_flask()
    time.sleep(3)
    out = (LOG_DIR / "app_stdout.log").open("a", encoding="utf-8")
    err = (LOG_DIR / "app_stderr.log").open("a", encoding="utf-8")
    subprocess.Popen([PYTHON, "-u", "app.py"], cwd=str(BASE), stdout=out, stderr=err)
    deadline = time.time() + 180
    while time.time() < deadline:
        if url_ok() and free_gb() >= RESUME_FREE_GB:
            log(f"Flask recovered free_gb={free_gb():.2f}")
            return
        time.sleep(4)
    if not url_ok():
        raise RuntimeError("Flask did not recover")
    log(f"Flask healthy with limited free memory free_gb={free_gb():.2f}")


def ensure_memory():
    if free_gb() < MIN_FREE_GB:
        restart_flask()


def login():
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    data = urllib.parse.urlencode({"username": USER, "password": PASSWORD}).encode()
    with opener.open(urllib.request.Request(API + "/login", data=data), timeout=20) as response:
        response.read()
    return opener


def request_json(opener, path, payload, timeout=120):
    body = json.dumps(payload).encode()
    request = urllib.request.Request(API + path, data=body, headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "ignore") or "{}")


def theme(expression):
    low = (expression or "").lower()
    scores = [(sum(key in low for key in keys), name) for name, keys in THEMES.items()]
    score, name = max(scores)
    return name if score else "other"


def load_history():
    connection = sqlite3.connect(DB)
    rows = connection.execute(
        "SELECT id, expression, COALESCE(type,'alpha'), metrics_json, pnl_json, timestamp "
        "FROM alpha_history WHERE pnl_json IS NOT NULL AND length(pnl_json)>5"
    ).fetchall()
    connection.close()
    out = []
    for aid, expression, kind, metrics_json, pnl_json, timestamp in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            continue
        changes = daily(parse_pnl(pnl_json))
        if len(changes) < 30 or safe_float(metrics.get("n_days")) < 30:
            continue
        out.append({
            "id": aid, "expression": expression or "", "type": kind,
            "theme": theme(expression), "metrics": metrics, "daily": changes,
            "timestamp": timestamp,
        })
    return out


def strict_select(rows, min_sharpe=8.0, max_corr=0.5):
    candidates = [row for row in rows if safe_float(row["metrics"].get("sharpe")) > min_sharpe]
    candidates.sort(key=lambda row: (-safe_float(row["metrics"].get("sharpe")), row["id"]))
    selected = []
    for candidate in candidates:
        values = [abs_corr(candidate["daily"], old["daily"]) for old in selected]
        if all(value < max_corr for value in values):
            selected.append({**candidate, "max_corr_to_selected": max(values) if values else 0.0})
    return selected


def strict_manifest(rows):
    return [{
        "id": row["id"], "expression": row["expression"], "type": row["type"],
        "theme": row["theme"], "sharpe": safe_float(row["metrics"].get("sharpe")),
        "ic": safe_float(row["metrics"].get("pearson_ic")),
        "fitness": safe_float(row["metrics"].get("fitness")),
        "turnover": safe_float(row["metrics"].get("turnover")),
        "max_corr_to_selected": row["max_corr_to_selected"],
    } for row in strict_select(rows)]


def latest_superalpha_id():
    connection = sqlite3.connect(DB)
    row = connection.execute(
        "SELECT id FROM alpha_history WHERE type='superalpha' ORDER BY timestamp DESC, rowid DESC LIMIT 1"
    ).fetchone()
    connection.close()
    return row[0] if row else None


def write_status(phase, count):
    rows = load_history()
    strict = strict_manifest(rows)
    atomic_json(STATUS, {
        "time": now(), "phase": phase, "completed_experiments": count,
        "strict_gt8_lowcorr_count": len(strict), "strict_gt8_lowcorr": strict,
        "free_memory_gb": round(free_gb(), 2),
    })
    return rows, strict


def call_combo(opener, label, ids, method="equal", neutralize="none", phase="exploratory", metadata=None):
    if label in DONE:
        log(f"reuse {label}")
        return DONE[label]
    ensure_memory()
    before = latest_superalpha_id()
    payload = {
        "alpha_ids": list(ids), "method": method, "neutralize": neutralize,
        "oos_only": True, "sub_alpha_limit": min(10, len(ids)),
    }
    log(f"run {label} n={len(ids)} method={method} neutralize={neutralize} free_gb={free_gb():.2f}")
    error = None
    response = {}
    for attempt in (1, 2):
        try:
            response = request_json(opener, "/api/superalpha", payload)
            error = None
            break
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log(f"attempt={attempt} failed {label}: {error}")
            if attempt == 1:
                restart_flask()
                opener = login()
    after = latest_superalpha_id()
    metrics = response.get("combined_metrics") or {}
    row = {
        "time": now(), "label": label, "phase": phase, "method": method,
        "neutralize": neutralize, "alpha_ids": list(ids),
        "history_id": after if after != before else None,
        "success": bool(response.get("success")), "metrics": {
            key: metrics.get(key) for key in (
                "pearson_ic", "icir", "fitness", "annual_excess", "sharpe",
                "max_drawdown", "turnover", "win_rate", "n_days",
            )
        }, "pnl_series": metrics.get("pnl_series") or [],
        "metadata": metadata or {}, "error": error or response.get("error"),
    }
    append_jsonl(row)
    DONE[label] = row
    log(f"done {label} success={row['success']} sharpe={safe_float(metrics.get('sharpe')):.3f}")
    write_status(phase, len(DONE))
    return row


def ranked_singles(rows):
    singles = [row for row in rows if row["type"] == "alpha"]
    singles.sort(key=lambda row: (
        -safe_float(row["metrics"].get("is_sharpe")),
        -safe_float(row["metrics"].get("is_pearson_ic")),
        row["id"],
    ))
    return singles


def greedy(rows, count, max_corr=0.55):
    selected = []
    for row in rows:
        if all(abs_corr(row["daily"], old["daily"]) < max_corr for old in selected):
            selected.append(row)
        if len(selected) >= count:
            break
    return selected


def id_list(rows):
    return [row["id"] for row in rows]


def refresh():
    return load_history(), strict_manifest(load_history())


def run():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    PAUSE_FLAG.write_text(f"{now()} afternoon extension owns experiment slot\n", encoding="utf-8")
    if not url_ok():
        restart_flask()
    if free_gb() < RESUME_FREE_GB:
        restart_flask()
    opener = login()
    rows, _ = write_status("start", len(DONE))
    strict = strict_select(rows)
    log(f"afternoon extension start history={len(rows)} strict_gt8_lowcorr={len(strict)}")

    singles = ranked_singles(rows)
    strict_ids = {row["id"] for row in strict}
    satellites = [row for row in strict if row["type"] == "alpha"]
    satellite_ids = id_list(satellites)

    # Phase A: residualize existing near-threshold high-Sharpe candidates.
    near = []
    for row in rows:
        if safe_float(row["metrics"].get("sharpe")) <= 7.5 or row["id"] in strict_ids:
            continue
        values = [abs_corr(row["daily"], old["daily"]) for old in strict]
        if values:
            near.append((max(values), -safe_float(row["metrics"].get("sharpe")), row))
    near.sort(key=lambda item: (item[0], item[1]))
    for _, _, candidate in near[:10]:
        for neutralize in ("market_cap", "beta", "market_cap_beta", "market_cap_regression"):
            call_combo(
                opener, f"aft_residual_{candidate['id'][:8]}_{neutralize}",
                [candidate["id"]], "equal", neutralize, "residualized_near_threshold",
                {"source": candidate["id"], "source_theme": candidate["theme"]},
            )

    # Phase B: bridge a near-threshold candidate with diverse strict satellites.
    rows = load_history()
    strict = strict_select(rows)
    strict_ids = {row["id"] for row in strict}
    near = [row for row in rows if row["id"] not in strict_ids and safe_float(row["metrics"].get("sharpe")) > 7.5]
    near.sort(key=lambda row: (
        max(abs_corr(row["daily"], old["daily"]) for old in strict),
        -safe_float(row["metrics"].get("sharpe")),
    ))
    for candidate in near[:6]:
        for satellite in satellites[:8]:
            if candidate["id"] == satellite["id"]:
                continue
            for neutralize in ("none", "beta", "market_cap_beta"):
                call_combo(
                    opener,
                    f"aft_bridge_{candidate['id'][:8]}_{satellite['id'][:8]}_{neutralize}",
                    [candidate["id"], satellite["id"]], "equal", neutralize, "cross_style_bridge",
                    {"source_theme": candidate["theme"], "satellite_theme": satellite["theme"]},
                )

    # Phase C: build style anchors with multiple weight and neutralization regimes.
    rows = load_history()
    cached = [
        row for row in rows
        if row["type"] == "superalpha" and (BASE / "cache" / f"ew_{row['id']}.npy").exists()
    ]
    anchors = []
    for style in THEMES:
        pool = [row for row in cached if row["theme"] == style]
        # Read cached bridge matrices here. Higher-order combinations must not
        # reparse original leaves under the constrained desktop memory budget.
        basket = greedy(pool, 2, 0.75)
        if len(basket) < 2:
            continue
        for method in ("equal", "icir", "ridge"):
            for neutralize in ("none", "market_cap", "beta", "market_cap_beta"):
                result = call_combo(
                    opener, f"aft_anchor_{style}_{method}_{neutralize}", id_list(basket),
                    method, neutralize, "style_anchor", {"style": style},
                )
                if result.get("success") and result.get("history_id"):
                    anchors.append(result)

    # Phase D: true nesting of the best measured style anchors.
    best_anchor = {}
    for row in anchors:
        style = row["metadata"]["style"]
        if style not in best_anchor or safe_float(row["metrics"].get("sharpe")) > safe_float(best_anchor[style]["metrics"].get("sharpe")):
            best_anchor[style] = row
    anchor_ids = [row["history_id"] for row in best_anchor.values()]
    if len(anchor_ids) >= 2:
        for take in range(2, len(anchor_ids) + 1):
            for neutralize in NEUTRALS:
                call_combo(
                    opener, f"aft_nest_anchor_n{take}_{neutralize}", anchor_ids[:take],
                    "equal", neutralize, "nested_style_anchor", {"layer": 2, "n_styles": take},
                )

    # Phase E: IS-ranked cross-style offset baskets produce alternatives, not one core family.
    rows = load_history()
    cached = [
        row for row in rows
        if row["type"] == "superalpha" and (BASE / "cache" / f"ew_{row['id']}.npy").exists()
    ]
    grouped = {style: [row for row in cached if row["theme"] == style] for style in THEMES}
    styles = [style for style in THEMES if grouped[style]]
    for offset in range(5):
        rotated_styles = [styles[(offset + index) % len(styles)] for index in range(min(2, len(styles)))]
        basket = [grouped[style][offset % len(grouped[style])] for style in rotated_styles]
        if len(basket) < 2:
            continue
        for method in ("equal", "icir", "ridge"):
            for neutralize in ("none", "market_cap", "beta", "market_cap_beta"):
                call_combo(
                    opener, f"aft_cross_offset{offset}_{method}_{neutralize}", id_list(basket),
                    method, neutralize, "cross_style_offset", {"offset": offset, "styles": rotated_styles},
                )

    rows, strict = write_status("complete", len(DONE))
    atomic_json(FINAL, {
        "generated_at": now(), "completed_experiments": len(DONE),
        "strict_gt8_lowcorr_count": len(strict), "strict_gt8_lowcorr": strict,
        "results": list(DONE.values()),
        "note": "Exploratory OOS search; real measurements only. Requires future walk-forward confirmation.",
    })
    log(f"afternoon extension complete experiments={len(DONE)} strict_gt8_lowcorr={len(strict)}")


if __name__ == "__main__":
    run()
