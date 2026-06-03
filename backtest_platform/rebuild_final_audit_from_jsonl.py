#!/usr/bin/env python3
"""Recover the frozen audit summary from measured JSONL rows.

The original runner wrote every real experiment to JSONL before summary assembly, but
older code omitted L1 and L2 nested rows from the final JSON. This script performs no
backtest and invents no metrics. It deduplicates measured rows by label and atomically
replaces the summary while preserving the frozen screen and selections.
"""

import datetime as dt
import json
import os
import pathlib


BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "experiment_results"
JSONL = OUT / "final_audit_experiments.jsonl"
FINAL = OUT / "final_audit_results.json"


def atomic_json(path, data):
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main():
    frozen = json.loads(FINAL.read_text(encoding="utf-8"))
    measured = [
        json.loads(line)
        for line in JSONL.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_label = {}
    for row in measured:
        label = row.get("label")
        if label:
            by_label[label] = row
    frozen["results"] = list(by_label.values())
    frozen["summary_rebuilt_at"] = dt.datetime.now().isoformat(timespec="seconds")
    frozen["raw_jsonl_rows"] = len(measured)
    frozen["results_recovered_from_jsonl"] = len(frozen["results"])
    atomic_json(FINAL, frozen)
    print(
        f"rebuilt final audit json raw_jsonl={len(measured)} "
        f"unique_results={len(frozen['results'])}"
    )


if __name__ == "__main__":
    main()
