#!/usr/bin/env python3
"""Independent 10-minute yyb check loop."""
import datetime as dt
import os
import re
import sys
import time

import yyb_guardian

LOG_DIR = r"D:\yyb\logs"
LOG = os.path.join(LOG_DIR, "yyb_scheduler_loop.log")


def log(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def already_running_loop():
    this = os.getpid()
    rows = yyb_guardian.process_rows()
    for row in rows:
        try:
            pid = int(row.get("ProcessId") or 0)
        except Exception:
            pid = 0
        name = (row.get("Name") or "").lower()
        cmd = row.get("CommandLine") or ""
        if (
            pid != this
            and "python" in name
            and re.search(r"yyb_scheduler_loop\.py([\s\"]|$)", cmd, re.I)
            and "--ensure" not in cmd
        ):
            return True
    return False


def ensure_loop():
    if already_running_loop():
        log("loop already running")
        return
    import subprocess
    subprocess.Popen(
        [sys.executable, "-u", __file__],
        cwd=os.path.dirname(__file__),
        stdout=open(os.path.join(LOG_DIR, "yyb_scheduler_loop_stdout.log"), "a", encoding="utf-8"),
        stderr=open(os.path.join(LOG_DIR, "yyb_scheduler_loop_stderr.log"), "a", encoding="utf-8"),
    )
    log("loop started")


def main():
    if "--ensure" in sys.argv:
        ensure_loop()
        return
    log("loop start")
    iteration = 0
    while True:
        iteration += 1
        try:
            yyb_guardian.check_once(iteration)
            log(f"check ok iteration={iteration}")
        except Exception as e:
            log(f"check error={e}")
        time.sleep(600)


if __name__ == "__main__":
    main()
