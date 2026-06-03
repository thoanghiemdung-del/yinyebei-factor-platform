#!/usr/bin/env python3
"""Generate figures and compile the final paper once the audit JSON is frozen."""

import datetime as dt
import json
import pathlib
import subprocess
import time


BASE = pathlib.Path(__file__).resolve().parent
AUDIT = BASE / "experiment_results" / "final_audit_results.json"
PAPER = pathlib.Path(r"D:\yyb\paper")
PDF = PAPER / "final_submission.pdf"
STATUS = PAPER / "final_submission_status.json"
LOG = pathlib.Path(r"D:\yyb\logs\final_submission_supervisor.log")
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
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(STATUS)


def build_once():
    generator = subprocess.run(
        [PYTHON, str(BASE / "generate_final_submission.py")],
        cwd=str(BASE),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if generator.returncode:
        log(f"paper generator failed code={generator.returncode}")
        write_status({"ok": False, "time": dt.datetime.now().isoformat(), "error": generator.stderr[-4000:]})
        return False
    for pass_no in (1, 2):
        log(f"xelatex pass={pass_no}")
        result = subprocess.run(
            [XELATEX, "-interaction=nonstopmode", "-halt-on-error", "final_submission.tex"],
            cwd=str(PAPER),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode:
            log(f"xelatex failed pass={pass_no} code={result.returncode}")
            write_status({"ok": False, "time": dt.datetime.now().isoformat(), "error": (result.stdout + result.stderr)[-4000:]})
            return False
    write_status({
        "ok": PDF.exists(),
        "time": dt.datetime.now().isoformat(),
        "audit": str(AUDIT),
        "tex": str(PAPER / "final_submission.tex"),
        "pdf": str(PDF),
        "pdf_bytes": PDF.stat().st_size if PDF.exists() else 0,
    })
    log(f"final PDF ready bytes={PDF.stat().st_size if PDF.exists() else 0}")
    return PDF.exists()


def main():
    log("final submission supervisor start")
    while not AUDIT.exists():
        time.sleep(60)
    log("frozen audit JSON detected")
    while not build_once():
        log("final build retry in 60 seconds")
        time.sleep(60)


if __name__ == "__main__":
    main()
