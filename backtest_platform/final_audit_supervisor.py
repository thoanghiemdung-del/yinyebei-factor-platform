#!/usr/bin/env python3
"""Keep the low-memory final audit runner alive until its frozen JSON exists."""

import datetime as dt
import os
import pathlib
import subprocess
import time

import psutil


BASE = pathlib.Path(__file__).resolve().parent
LOG_DIR = pathlib.Path(r"D:\yyb\logs")
LOG = LOG_DIR / "final_audit_supervisor.log"
FINAL = BASE / "experiment_results" / "final_audit_results.json"
PYTHON = r"python"
RUNNER = BASE / "run_final_audit_experiments.py"


def log(message):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def runner_alive():
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "python" in name and "run_final_audit_experiments.py" in cmd:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def start_runner():
    out = (LOG_DIR / "final_audit_runner_stdout.log").open("a", encoding="utf-8")
    err = (LOG_DIR / "final_audit_runner_stderr.log").open("a", encoding="utf-8")
    subprocess.Popen([PYTHON, "-u", str(RUNNER)], cwd=str(BASE), stdout=out, stderr=err)
    log("started final audit runner")


def main():
    log("supervisor start")
    while not FINAL.exists():
        if not runner_alive():
            start_runner()
        time.sleep(60)
    log("frozen audit JSON exists; supervisor exit")


if __name__ == "__main__":
    main()

