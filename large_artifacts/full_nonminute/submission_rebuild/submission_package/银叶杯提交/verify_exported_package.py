#!/usr/bin/env python3
"""Verify the exported Silver Leaf Cup package after extraction."""

from __future__ import annotations

import csv
import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent


def main():
    values_path = ROOT / "factor_values" / "standardized_factor_values_2020_2023.npz"
    corr_path = ROOT / "results" / "final_factor_value_correlation.csv"
    code_path = ROOT / "code" / "factor_submission.py"
    smoke_path = ROOT / "code" / "submission_smoke_test.py"
    validation_path = ROOT / "results" / "submission_code_realdata_validation.json"
    checksum_path = ROOT / "MANIFEST_SHA256.txt"
    required = [
        ROOT / "paper" / "银叶杯因子研究报告.pdf",
        code_path,
        smoke_path,
        values_path,
        ROOT / "results" / "final_factor_metrics.csv",
        corr_path,
        ROOT / "results" / "final_factor_dictionary.json",
        validation_path,
        ROOT / "官方赛题要求核对表.md",
        checksum_path,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    expected_keys = [f"factor_{index:02d}" for index in range(1, 11)]

    values = np.load(values_path)
    actual_keys = [key for key in values.files if key.startswith("factor_")]
    shapes = {key: list(values[key].shape) for key in actual_keys}
    values.close()

    with corr_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    corr = np.asarray([[float(value) for value in row[1:]] for row in rows[1:]], dtype=float)
    max_corr = float(np.max(np.abs(corr - np.eye(10))))

    py_compile.compile(str(code_path), doraise=True)
    smoke = subprocess.run([sys.executable, str(smoke_path)], check=True, capture_output=True, text=True)
    pycache = ROOT / "code" / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache)
    realdata = json.loads(validation_path.read_text(encoding="utf-8"))
    checksum_failures = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        digest = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if digest != expected:
            checksum_failures.append(relative)
    checks = {
        "required_files_present": not missing,
        "factor_keys_are_01_to_10": actual_keys == expected_keys,
        "each_factor_shape_is_970_by_5515": all(shape == [970, 5515] for shape in shapes.values()),
        "pairwise_abs_corr_below_0_5": max_corr < 0.5,
        "synthetic_interface_smoke_test_pass": '"status": "PASS"' in smoke.stdout,
        "realdata_reproduction_report_pass": realdata["status"] == "PASS",
        "sha256_manifest_pass": not checksum_failures,
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "missing": missing,
        "checksum_failures": checksum_failures,
        "maximum_abs_factor_value_correlation": max_corr,
        "factor_shapes": shapes,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
