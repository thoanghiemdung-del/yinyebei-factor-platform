#!/usr/bin/env python3
"""Keep the cached afternoon backup audit running until it freezes."""

import pathlib
import subprocess
import time


BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "experiment_results"
LOG = pathlib.Path(r"D:\yyb\logs\afternoon_backup_supervisor.log")
PYTHON = r"python"
RUNNER = BASE / "run_afternoon_backup_extension.py"
FINAL = OUT / "afternoon_backup_results.json"


def log(message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {message}\n")


def main():
    log("afternoon backup supervisor start")
    while not FINAL.exists():
        process = subprocess.Popen(
            [PYTHON, "-u", str(RUNNER)],
            cwd=str(BASE),
            stdout=(pathlib.Path(r"D:\yyb\logs\afternoon_backup_runner_stdout.log")).open("a", encoding="utf-8"),
            stderr=(pathlib.Path(r"D:\yyb\logs\afternoon_backup_runner_stderr.log")).open("a", encoding="utf-8"),
        )
        log(f"started backup runner pid={process.pid}")
        while process.poll() is None and not FINAL.exists():
            time.sleep(20)
        if FINAL.exists():
            break
        log(f"backup runner exited code={process.returncode}; retrying")
        time.sleep(10)
    log("afternoon backup supervisor complete")


if __name__ == "__main__":
    main()
