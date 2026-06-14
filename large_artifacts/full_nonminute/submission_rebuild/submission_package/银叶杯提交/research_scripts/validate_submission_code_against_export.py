#!/usr/bin/env python3
"""Recompute a real-data window and compare submission code against exported matrices."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


ROOT = Path(r"D:\yyb")
WORK = ROOT / "submission_rebuild"
MODEL = ROOT / "模型"
sys.path.insert(0, str(MODEL))
sys.path.insert(0, str(WORK))

from data_pipeline import DataPipeline  # noqa: E402
from factor_submission import compute_final_factors  # noqa: E402


def main():
    pipeline = DataPipeline(ROOT)
    available = []
    for date_text in pipeline.get_minute_dates():
        iso = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"
        if "2020-01-02" <= iso <= "2023-12-29" and iso in pipeline.date_to_idx:
            available.append((date_text, iso, pipeline.date_to_idx[iso]))
    window = available[-30:]
    if len(window) != 30:
        raise RuntimeError("Need 30 real minute dates for validation")

    safe_adjfactor = np.where(np.isnan(pipeline.fields["I_D_ADJFACTOR"]), 1.0, pipeline.fields["I_D_ADJFACTOR"])
    safe_adjfactor = np.clip(safe_adjfactor, 0.01, 100.0)
    adjusted_close = pipeline.fields["I_D_CLOSE_ORI"] * safe_adjfactor
    indices = [item[2] for item in window]
    universe = pipeline.universe_mask[indices]

    def aligned_days():
        for date_text, _, index in window:
            yield pipeline.align_minute_to_daily(pipeline.load_minute_day(date_text), index)

    actual = compute_final_factors(aligned_days(), adjusted_close[indices], universe)
    exported = np.load(WORK / "deliverables" / "factor_values" / "standardized_factor_values_2020_2023.npz")
    train_start = pipeline.date_to_idx["2020-01-02"]
    compare_rows = list(range(25, 30))
    rows = []
    for factor_key, values in actual.items():
        reference = exported[factor_key][[indices[row] - train_start for row in compare_rows]]
        recomputed = values[compare_rows]
        valid = np.isfinite(reference) & np.isfinite(recomputed)
        nan_agreement = float(np.mean(np.isfinite(reference) == np.isfinite(recomputed)))
        if valid.sum() < 100:
            raise RuntimeError(f"Too few comparable values for {factor_key}")
        delta = np.abs(reference[valid] - recomputed[valid])
        corr = float(np.corrcoef(reference[valid], recomputed[valid])[0, 1])
        rows.append({
            "factor_key": factor_key,
            "comparable_values": int(valid.sum()),
            "pearson_corr": corr,
            "mean_abs_error": float(delta.mean()),
            "max_abs_error": float(delta.max()),
            "nan_agreement": nan_agreement,
        })
    exported.close()
    passed = all(row["pearson_corr"] > 0.9999 and row["mean_abs_error"] < 1e-4 and row["nan_agreement"] > 0.999 for row in rows)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "PASS" if passed else "FAIL",
        "validation_window": [window[0][1], window[-1][1]],
        "compared_dates": [window[row][1] for row in compare_rows],
        "rows": rows,
    }
    (WORK / "deliverables" / "submission_code_realdata_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

