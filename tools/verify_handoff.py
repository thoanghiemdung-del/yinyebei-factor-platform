#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify that the public handoff contains the required project pieces."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "README.md",
    ROOT / "submission" / "银叶杯_三个臭诸葛亮_初赛结果.zip",
    ROOT / "submission" / "official_initial_round_result" / "银叶杯.py",
    ROOT / "submission" / "official_initial_round_result" / "因子值.xlsx",
    ROOT / "submission" / "official_initial_round_result" / "回测报告.docx",
    ROOT / "submission" / "official_initial_round_result" / "因子逻辑说明文档.pdf",
    ROOT / "backtest_platform" / "app.py",
    ROOT / "model" / "data_pipeline.py",
    ROOT / "runtime_state" / "backtest_platform" / "backtest.db",
    ROOT / "runtime_state" / "experiment_results" / "final_audit_results.json",
    ROOT / "docs" / "HANDOFF_FULL_REPRODUCTION.md",
]


def main() -> None:
    missing = [str(p.relative_to(ROOT)) for p in REQUIRED if not p.exists()]
    if missing:
        raise SystemExit("missing required files:\n" + "\n".join(missing))

    with zipfile.ZipFile(ROOT / "submission" / "银叶杯_三个臭诸葛亮_初赛结果.zip") as zf:
        entries = sorted(Path(i.filename).name for i in zf.infolist() if not i.is_dir())
    expected = sorted(["银叶杯.py", "回测报告.docx", "因子逻辑说明文档.pdf", "因子值.xlsx"])
    if entries != expected:
        raise SystemExit(f"unexpected official zip entries: {entries}")

    script = ROOT / "submission" / "official_initial_round_result" / "银叶杯.py"
    spec = importlib.util.spec_from_file_location("yyb_submission", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    dates, stocks, values = mod.load_factor_values(
        ROOT / "submission" / "official_initial_round_result" / "因子值.xlsx"
    )
    if values.shape != (970, 5515):
        raise SystemExit(f"unexpected factor matrix shape: {values.shape}")
    if str(dates[0]) != "2020-01-02" or str(dates[-1]) != "2023-12-29":
        raise SystemExit(f"unexpected date range: {dates[0]} to {dates[-1]}")
    if len(stocks) != 5515:
        raise SystemExit(f"unexpected stock count: {len(stocks)}")

    con = sqlite3.connect(ROOT / "runtime_state" / "backtest_platform" / "backtest.db")
    try:
        count = con.execute("SELECT COUNT(*) FROM alpha_history").fetchone()[0]
    finally:
        con.close()
    if count <= 0:
        raise SystemExit("alpha_history is empty")

    manifest = json.loads((ROOT / "large_artifacts" / "split_manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "ok": True,
        "factor_shape": list(values.shape),
        "date_range": [str(dates[0]), str(dates[-1])],
        "stock_count": len(stocks),
        "alpha_history_count": count,
        "split_artifact_count": len(manifest),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
