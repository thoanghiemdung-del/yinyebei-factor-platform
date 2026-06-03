#!/usr/bin/env python3
"""Keep the sequential afternoon extension runner alive until its final JSON exists."""

import datetime as dt
import pathlib
import subprocess
import time

import psutil


BASE = pathlib.Path(__file__).resolve().parent
FINAL = BASE / "experiment_results" / "afternoon_extension_results.json"
LOG = pathlib.Path(r"D:\yyb\logs\afternoon_extension_supervisor.log")
PYTHON = r"python"
RUNNER = BASE / "run_afternoon_extension_experiments.py"


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
    log("afternoon extension supervisor start")
    while not FINAL.exists():
        if not running():
            out = pathlib.Path(r"D:\yyb\logs\afternoon_extension_runner_stdout.log").open("a", encoding="utf-8")
            err = pathlib.Path(r"D:\yyb\logs\afternoon_extension_runner_stderr.log").open("a", encoding="utf-8")
            subprocess.Popen([PYTHON, "-u", str(RUNNER)], cwd=str(BASE), stdout=out, stderr=err)
            log("started afternoon extension runner")
        time.sleep(30)
    log("afternoon extension final JSON exists; supervisor exit")


if __name__ == "__main__":
    main()
