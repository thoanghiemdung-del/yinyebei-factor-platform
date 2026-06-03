#!/usr/bin/env python3
"""Generate and compile the afternoon submission after deep search completes."""

import datetime as dt
import json
import pathlib
import subprocess
import time


BASE = pathlib.Path(__file__).resolve().parent
DEEP_FINAL = BASE / "experiment_results" / "afternoon_deep_results.json"
PAPER = pathlib.Path(r"D:\yyb\paper")
PDF = PAPER / "afternoon_final_submission.pdf"
STATUS = PAPER / "afternoon_final_submission_status.json"
LOG = pathlib.Path(r"D:\yyb\logs\afternoon_submission_supervisor.log")
PYTHON = r"python"
XELATEX = r"xelatex"


def log(message):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_status(data):
    PAPER.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATUS)


def build():
    generator = subprocess.run([PYTHON, str(BASE / "generate_afternoon_submission.py")], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if generator.returncode:
        write_status({"ok": False, "time": dt.datetime.now().isoformat(), "error": generator.stderr[-4000:]})
        log(f"generator failed code={generator.returncode}")
        return False
    for number in (1, 2):
        log(f"xelatex pass={number}")
        result = subprocess.run([XELATEX, "-interaction=nonstopmode", "-halt-on-error", "afternoon_final_submission.tex"], cwd=str(PAPER), capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if result.returncode:
            write_status({"ok": False, "time": dt.datetime.now().isoformat(), "error": (result.stdout + result.stderr)[-4000:]})
            log(f"xelatex failed pass={number} code={result.returncode}")
            return False
    write_status({"ok": PDF.exists(), "time": dt.datetime.now().isoformat(), "pdf": str(PDF), "pdf_bytes": PDF.stat().st_size if PDF.exists() else 0})
    log(f"afternoon PDF ready bytes={PDF.stat().st_size if PDF.exists() else 0}")
    return PDF.exists()


def main():
    log("afternoon submission supervisor start")
    while not DEEP_FINAL.exists():
        time.sleep(60)
    while not build():
        log("retry final build in 60 seconds")
        time.sleep(60)


if __name__ == "__main__":
    main()
