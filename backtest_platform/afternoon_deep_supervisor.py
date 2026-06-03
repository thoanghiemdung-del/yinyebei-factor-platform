#!/usr/bin/env python3
"""Launch the deep extension after the first afternoon search completes."""

import datetime as dt
import pathlib
import subprocess
import time

import psutil


BASE = pathlib.Path(__file__).resolve().parent
FIRST = BASE / "experiment_results" / "afternoon_extension_results.json"
FINAL = BASE / "experiment_results" / "afternoon_deep_results.json"
RUNNER = BASE / "run_afternoon_deep_extension.py"
LOG = pathlib.Path(r"D:\yyb\logs\afternoon_deep_supervisor.log")
PYTHON = r"python"


def log(message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def running():
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            if (process.info.get("name") or "").lower() == "python.exe" and RUNNER.name in " ".join(process.info.get("cmdline") or []):
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return False


def main():
    log("deep extension supervisor start")
    while not FINAL.exists():
        if FIRST.exists() and not running():
            out = pathlib.Path(r"D:\yyb\logs\afternoon_deep_runner_stdout.log").open("a", encoding="utf-8")
            err = pathlib.Path(r"D:\yyb\logs\afternoon_deep_runner_stderr.log").open("a", encoding="utf-8")
            subprocess.Popen([PYTHON, "-u", str(RUNNER)], cwd=str(BASE), stdout=out, stderr=err)
            log("started deep extension runner")
        time.sleep(30)
    log("deep extension final JSON exists; supervisor exit")


if __name__ == "__main__":
    main()
