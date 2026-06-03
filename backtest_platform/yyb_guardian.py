#!/usr/bin/env python3
"""Keep yyb platform, ngrok tunnel, and factor miner alive."""
import datetime as dt
import http.cookiejar
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from yyb_factor_policy import eligible_expr

BASE = r"D:\yyb\backtest_platform"
LOG_DIR = r"D:\yyb\logs"
DB = os.path.join(BASE, "backtest.db")
PYTHON = r"python"
NGROK = r"D:\yyb\ngrok.exe"
CLOUDFLARED_PUBLIC_FILE = os.path.join(LOG_DIR, "cloudflared_public_url.txt")
PUBLIC = "https://remark-glance-tweet.ngrok-free.dev"
LOCAL = "http://127.0.0.1:5000"
TARGET = 1000
CHECK_INTERVAL = 600
DEDUP_EVERY = 1

os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "yyb_guardian.log")
STATUS_JSON = os.path.join(LOG_DIR, "yyb_status.json")
MINING_PAUSE_FLAG = os.path.join(LOG_DIR, "mining_paused.flag")
MEMORY_PAUSE_FLAG = os.path.join(LOG_DIR, "memory_paused.flag")
COMBO_BUILDER_PAUSE_FLAG = os.path.join(LOG_DIR, "combo_builder_paused.flag")
MIN_FREE_GB = 3.0
RESUME_FREE_GB = 4.0
FLASK_RESTART_GB = 4.5


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def process_rows():
    cmd = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True,
            encoding="utf-8",
            errors="ignore",
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        data = json.loads(out) if out.strip() else []
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception:
        return []


def has_process(pattern, name_pattern=None):
    rx = re.compile(pattern, re.I)
    name_rx = re.compile(name_pattern, re.I) if name_pattern else None
    for row in process_rows():
        if name_rx and not name_rx.search(row.get("Name") or ""):
            continue
        if rx.search(row.get("CommandLine") or ""):
            return True
    return False


def matching_pids(pattern, name_pattern=None):
    rx = re.compile(pattern, re.I)
    name_rx = re.compile(name_pattern, re.I) if name_pattern else None
    out = []
    for row in process_rows():
        if name_rx and not name_rx.search(row.get("Name") or ""):
            continue
        if rx.search(row.get("CommandLine") or ""):
            try:
                pid = int(row.get("ProcessId") or 0)
            except Exception:
                pid = 0
            if pid > 0:
                out.append(pid)
    return out


def mining_paused():
    return os.path.exists(MINING_PAUSE_FLAG)


def memory_snapshot():
    try:
        import psutil
        vm = psutil.virtual_memory()
        flask_gb = 0.0
        for p in psutil.process_iter(["name", "cmdline", "memory_info"]):
            try:
                name = (p.info.get("name") or "").lower()
                cmd = " ".join(p.info.get("cmdline") or [])
                if "python" in name and re.search(r"\bapp\.py\b", cmd, re.I):
                    flask_gb = max(flask_gb, p.info["memory_info"].rss / (1024 ** 3))
            except Exception:
                continue
        return vm.available / (1024 ** 3), flask_gb
    except Exception:
        return None, None


def update_memory_pause():
    free_gb, flask_gb = memory_snapshot()
    auto_paused = os.path.exists(MEMORY_PAUSE_FLAG)
    if free_gb is not None and free_gb < MIN_FREE_GB and not auto_paused:
        with open(MEMORY_PAUSE_FLAG, "w", encoding="utf-8") as f:
            f.write(f"{now()} free_gb={free_gb:.2f}\n")
        auto_paused = True
        log(f"Memory pressure free={free_gb:.2f}GB; pausing background workloads")
    elif (
        auto_paused
        and free_gb is not None
        and free_gb >= RESUME_FREE_GB
        and (flask_gb is None or flask_gb < FLASK_RESTART_GB)
    ):
        try:
            os.remove(MEMORY_PAUSE_FLAG)
        except OSError:
            pass
        auto_paused = False
        log(f"Memory recovered free={free_gb:.2f}GB; resuming background workloads")
    return free_gb, flask_gb, auto_paused


def stop_pid(pid):
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {int(pid)} -Force"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return True
    except Exception:
        return False


def cleanup_extra_ngroks():
    pids = sorted(set(matching_pids(r"ngrok(?:\.exe)?\s+http\s+5000|ngrok\.exe.*remark-glance-tweet", r"ngrok")))
    if len(pids) <= 1:
        return
    for pid in pids[1:]:
        if stop_pid(pid):
            log(f"Stopped duplicate ngrok pid={pid}")


def cleanup_extra_cloudflared():
    pids = sorted(set(matching_pids(r"cloudflared(?:\.exe)?.*tunnel.*127\.0\.0\.1:5000", r"cloudflared")))
    if len(pids) <= 1:
        return
    for pid in pids[1:]:
        if stop_pid(pid):
            log(f"Stopped duplicate cloudflared pid={pid}")


def cleanup_extra_flasks():
    pids = sorted(set(matching_pids(r"\bapp\.py\b", r"python")))
    if len(pids) <= 1:
        return
    for pid in pids[1:]:
        if stop_pid(pid):
            log(f"Stopped duplicate Flask app pid={pid}")


def cleanup_extra_miners():
    pids = sorted(set(matching_pids(r"\bsimple_miner\.py\b", r"python")))
    if len(pids) <= 1:
        return
    for pid in pids[1:]:
        if stop_pid(pid):
            log(f"Stopped duplicate miner pid={pid}")


def cleanup_extra_combo_testers():
    pids = sorted(set(matching_pids(r"\bnight_combo_tester\.py\b", r"python")))
    if len(pids) <= 1:
        return
    for pid in pids[1:]:
        if stop_pid(pid):
            log(f"Stopped duplicate combo tester pid={pid}")


def cleanup_extra_combo_builders():
    pids = sorted(set(matching_pids(r"\bcombo_builder\.py\b", r"python")))
    if len(pids) <= 1:
        return
    for pid in pids[1:]:
        if stop_pid(pid):
            log(f"Stopped duplicate combo builder pid={pid}")


def post_login(base_url, timeout=20):
    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        data = urllib.parse.urlencode({"username": "admin", "password": "quant2026"}).encode()
        req = urllib.request.Request(
            base_url.rstrip("/") + "/login",
            data=data,
            headers={
                "User-Agent": "curl/8.13.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "ngrok-skip-browser-warning": "true",
            },
        )
        resp = opener.open(req, timeout=timeout)
        body = resp.read(300).decode("utf-8", "ignore")
        if resp.status == 200 and ("dashboard" in resp.geturl() or len(cj) > 0):
            return True
        return resp.status == 200 and ("dashboard" in resp.geturl() or "量化" in body or len(cj) > 0)
    except Exception:
        return False


def curl_login_page_ok(base_url, timeout=20):
    try:
        out = subprocess.check_output(
            [
                "curl.exe",
                "-L",
                "-s",
                "-o",
                "NUL",
                "-w",
                "%{http_code}",
                "-H",
                "ngrok-skip-browser-warning: true",
                base_url.rstrip("/") + "/login",
                "--max-time",
                str(int(timeout)),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 5,
        )
        return out.strip().endswith("200")
    except Exception:
        return False


def login_ok(base_url, timeout=20, attempts=3):
    for i in range(attempts):
        if post_login(base_url, timeout=timeout):
            return True
        time.sleep(2 + i)
    return curl_login_page_ok(base_url, timeout=timeout)


def tunnel_api_ok():
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=5)
        data = json.loads(resp.read().decode())
        return any(t.get("public_url") == PUBLIC for t in data.get("tunnels", []))
    except Exception:
        return False


def cloudflared_public_url():
    try:
        url = open(CLOUDFLARED_PUBLIC_FILE, encoding="utf-8").read().strip()
        return url if re.fullmatch(r"https://[a-z0-9-]+\.trycloudflare\.com", url) else None
    except Exception:
        return None


def discover_cloudflared_public_url():
    text = ""
    for name in ("cloudflared_stderr.log", "cloudflared_stdout.log"):
        try:
            with open(os.path.join(LOG_DIR, name), encoding="utf-8", errors="ignore") as handle:
                text += "\n" + handle.read()
        except OSError:
            continue
    urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", text)
    if not urls:
        return None
    url = urls[-1]
    with open(CLOUDFLARED_PUBLIC_FILE, "w", encoding="ascii") as handle:
        handle.write(url + "\n")
    return url


def cloudflared_ok():
    url = cloudflared_public_url() or discover_cloudflared_public_url()
    return bool(
        url
        and has_process(r"cloudflared(?:\.exe)?.*tunnel.*127\.0\.0\.1:5000", r"cloudflared")
        and login_ok(url, timeout=20, attempts=2)
    )


def start_cloudflared():
    executable = shutil.which("cloudflared.exe") or shutil.which("cloudflared")
    if not executable:
        log("Cloudflared executable not found; fallback tunnel unavailable")
        return
    out = open(os.path.join(LOG_DIR, "cloudflared_stdout.log"), "a", encoding="utf-8")
    err = open(os.path.join(LOG_DIR, "cloudflared_stderr.log"), "a", encoding="utf-8")
    subprocess.Popen(
        [executable, "tunnel", "--url", "http://127.0.0.1:5000", "--no-autoupdate"],
        cwd=r"D:\yyb",
        stdout=out,
        stderr=err,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def start_flask():
    out = open(os.path.join(LOG_DIR, "flask_stdout.log"), "a", encoding="utf-8")
    err = open(os.path.join(LOG_DIR, "flask_stderr.log"), "a", encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("YYB_PRELOAD_MINUTE_CACHE", "0")
    subprocess.Popen([PYTHON, "app.py"], cwd=BASE, stdout=out, stderr=err, env=env)


def restart_flask():
    for pid in matching_pids(r"\bapp\.py\b", r"python"):
        stop_pid(pid)
    time.sleep(3)
    start_flask()


def wait_local_login(seconds=75):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if login_ok(LOCAL, timeout=5, attempts=1):
            return True
        time.sleep(3)
    return False


def start_ngrok():
    out = open(os.path.join(LOG_DIR, "ngrok_stdout.log"), "a", encoding="utf-8")
    err = open(os.path.join(LOG_DIR, "ngrok_stderr.log"), "a", encoding="utf-8")
    subprocess.Popen(
        [NGROK, "http", "5000", "--url=remark-glance-tweet.ngrok-free.dev", "--pooling-enabled"],
        cwd=r"D:\yyb",
        stdout=out,
        stderr=err,
    )


def restart_ngrok():
    for pid in matching_pids(r"ngrok(?:\.exe)?\s+http\s+5000|ngrok\.exe.*remark-glance-tweet", r"ngrok"):
        stop_pid(pid)
    time.sleep(3)
    start_ngrok()


def start_miner():
    out = open(os.path.join(LOG_DIR, "simple_miner_stdout.log"), "a", encoding="utf-8")
    err = open(os.path.join(LOG_DIR, "simple_miner_stderr.log"), "a", encoding="utf-8")
    subprocess.Popen([PYTHON, "-u", "simple_miner.py"], cwd=BASE, stdout=out, stderr=err)


def start_combo_tester():
    out = open(os.path.join(LOG_DIR, "night_combo_tester_stdout.log"), "a", encoding="utf-8")
    err = open(os.path.join(LOG_DIR, "night_combo_tester_stderr.log"), "a", encoding="utf-8")
    subprocess.Popen([PYTHON, "-u", "night_combo_tester.py"], cwd=BASE, stdout=out, stderr=err)


def start_combo_builder():
    out = open(os.path.join(LOG_DIR, "combo_builder_stdout.log"), "a", encoding="utf-8")
    err = open(os.path.join(LOG_DIR, "combo_builder_stderr.log"), "a", encoding="utf-8")
    subprocess.Popen([PYTHON, "-u", "combo_builder.py"], cwd=BASE, stdout=out, stderr=err)


def count_eligible():
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT expression FROM alpha_history "
        "WHERE ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01 "
        "AND pnl_json IS NOT NULL AND length(pnl_json)>5"
    ).fetchall()
    con.close()
    return sum(1 for (expr,) in rows if eligible_expr(expr))


def run_dedup():
    try:
        out = subprocess.check_output(
            [PYTHON, "corr_dedup.py", "0.7"],
            cwd=BASE,
            text=True,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
        return out.strip().splitlines()[:5]
    except Exception as e:
        return [f"dedup_error={e}"]


def check_once(iteration):
    cleanup_extra_ngroks()
    cleanup_extra_cloudflared()
    cleanup_extra_flasks()
    cleanup_extra_miners()
    cleanup_extra_combo_testers()
    cleanup_extra_combo_builders()

    free_gb, flask_gb, memory_paused = update_memory_pause()

    local_ok = login_ok(LOCAL, timeout=15, attempts=2)
    if not local_ok:
        if has_process(r"\bapp\.py\b", r"python"):
            log("Flask login failed while app.py exists; restarting stale app.py")
            restart_flask()
        else:
            log("Flask down; starting app.py")
            start_flask()
        local_ok = wait_local_login()

    api_ok = tunnel_api_ok()
    ngrok_ok = api_ok and login_ok(PUBLIC, timeout=30, attempts=3)
    cloudflare_ok = cloudflared_ok()
    if not ngrok_ok and cloudflare_ok:
        log(f"Ngrok unavailable; Cloudflare fallback healthy url={cloudflared_public_url()}")
    elif not ngrok_ok:
        if not api_ok:
            log("Ngrok API/tunnel down; starting pooled tunnel")
            start_ngrok()
        else:
            log("Ngrok public login failed after retries; restarting pooled tunnel")
            restart_ngrok()
        time.sleep(10)
        cleanup_extra_ngroks()
        ngrok_ok = tunnel_api_ok() and login_ok(PUBLIC, timeout=30, attempts=3)
        if not ngrok_ok:
            log("Ngrok recovery unsuccessful; starting Cloudflare fallback")
            start_cloudflared()
            time.sleep(12)
            cleanup_extra_cloudflared()
            cloudflare_ok = cloudflared_ok()
    public_ok = ngrok_ok or cloudflare_ok

    paused = mining_paused() or memory_paused
    miner_ok = has_process(r"\bsimple_miner\.py\b", r"python")
    if paused:
        if miner_ok:
            for pid in matching_pids(r"\bsimple_miner\.py\b", r"python"):
                if stop_pid(pid):
                    log(f"Mining paused; stopped miner pid={pid}")
            time.sleep(2)
        miner_ok = False
    elif not miner_ok and local_ok and public_ok:
        log("Miner down; starting simple_miner.py")
        start_miner()
        time.sleep(5)
        miner_ok = has_process(r"\bsimple_miner\.py\b", r"python")
    elif not miner_ok:
        log("Miner paused until platform login checks recover")

    combo_ok = has_process(r"\bnight_combo_tester\.py\b", r"python")
    if paused:
        if combo_ok:
            for pid in matching_pids(r"\bnight_combo_tester\.py\b", r"python"):
                if stop_pid(pid):
                    log(f"Mining paused; stopped combo tester pid={pid}")
            time.sleep(2)
        combo_ok = False
    elif local_ok and not combo_ok:
        log("Combo tester down; starting night_combo_tester.py")
        start_combo_tester()
        time.sleep(2)
        combo_ok = has_process(r"\bnight_combo_tester\.py\b", r"python")

    combo_builder_ok = has_process(r"\bcombo_builder\.py\b", r"python")
    combo_builder_paused = os.path.exists(COMBO_BUILDER_PAUSE_FLAG)
    if memory_paused or combo_builder_paused:
        if combo_builder_ok:
            for pid in matching_pids(r"\bcombo_builder\.py\b", r"python"):
                if stop_pid(pid):
                    reason = "Memory paused" if memory_paused else "Combo builder paused"
                    log(f"{reason}; stopped combo builder pid={pid}")
            time.sleep(2)
        combo_builder_ok = False
    elif local_ok and not combo_builder_ok:
        log("Combo builder down; starting combo_builder.py")
        start_combo_builder()
        time.sleep(2)
        combo_builder_ok = has_process(r"\bcombo_builder\.py\b", r"python")

    dedup_lines = []
    if iteration % DEDUP_EVERY == 0:
        dedup_lines = run_dedup()

    count = count_eligible()
    status = {
        "time": now(),
        "local_login": local_ok,
        "public_login": public_ok,
        "ngrok_login": ngrok_ok,
        "cloudflared_login": cloudflare_ok,
        "cloudflared_public_url": cloudflared_public_url(),
        "miner_running": miner_ok,
        "combo_tester_running": combo_ok,
        "combo_builder_running": combo_builder_ok,
        "mining_paused": paused,
        "memory_paused": memory_paused,
        "combo_builder_paused": combo_builder_paused,
        "free_memory_gb": round(free_gb, 2) if free_gb is not None else None,
        "flask_rss_gb": round(flask_gb, 2) if flask_gb is not None else None,
        "eligible_factor_count": count,
        "target": TARGET,
        "remaining": max(TARGET - count, 0),
        "dedup": dedup_lines,
    }
    with open(STATUS_JSON, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    free_text = f"{free_gb:.2f}" if free_gb is not None else "n/a"
    flask_text = f"{flask_gb:.2f}" if flask_gb is not None else "n/a"
    log(
        f"status local={local_ok} public={public_ok} ngrok={ngrok_ok} cloudflared={cloudflare_ok} miner={miner_ok} "
        f"combo={combo_ok} combo_builder={combo_builder_ok} "
        f"free_gb={free_text} flask_gb={flask_text} "
        f"eligible_factors={count}/{TARGET} remaining={status['remaining']}"
    )
    if dedup_lines:
        log("dedup " + " | ".join(dedup_lines))


def main():
    if "--once" in sys.argv:
        check_once(1)
        return
    log("guardian start")
    iteration = 0
    while True:
        iteration += 1
        try:
            check_once(iteration)
        except Exception as e:
            log(f"guardian_error={e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
