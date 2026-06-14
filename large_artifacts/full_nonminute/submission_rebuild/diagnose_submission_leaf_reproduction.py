#!/usr/bin/env python3
"""Compare independently recomputed leaves against frozen normalized leaf matrices."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(r"D:\yyb")
WORK = ROOT / "submission_rebuild"
MODEL = ROOT / "模型"
sys.path.insert(0, str(MODEL))
sys.path.insert(0, str(WORK))

from data_pipeline import DataPipeline  # noqa: E402
from factor_submission import FINAL_SPECS, compute_leaf_matrices, cs_winsor_zscore  # noqa: E402


def main():
    pipeline = DataPipeline(ROOT)
    available = []
    for date_text in pipeline.get_minute_dates():
        iso = f"{date_text[:4]}-{date_text[4:6]}-{date_text[6:8]}"
        if "2020-01-02" <= iso <= "2023-12-29" and iso in pipeline.date_to_idx:
            available.append((date_text, iso, pipeline.date_to_idx[iso]))
    window = available[-30:]
    indices = [item[2] for item in window]
    safe_adjfactor = np.where(np.isnan(pipeline.fields["I_D_ADJFACTOR"]), 1.0, pipeline.fields["I_D_ADJFACTOR"])
    safe_adjfactor = np.clip(safe_adjfactor, 0.01, 100.0)
    adjusted_close = pipeline.fields["I_D_CLOSE_ORI"] * safe_adjfactor

    def aligned_days():
        for date_text, _, index in window:
            yield pipeline.align_minute_to_daily(pipeline.load_minute_day(date_text), index)

    raw = compute_leaf_matrices(aligned_days(), adjusted_close[indices])
    universe = pipeline.universe_mask[indices]
    t0 = pipeline.date_to_idx["2020-01-02"]
    compare_rows = list(range(25, 30))
    leaves = []
    for terms in FINAL_SPECS.values():
        for leaf in terms:
            if leaf not in leaves:
                leaves.append(leaf)
    rows = []
    for leaf in leaves:
        actual = cs_winsor_zscore(raw[leaf], universe)[compare_rows]
        reference = np.load(WORK / "normalized_leaves" / f"{leaf}.npy", mmap_mode="r")[
            [indices[row] - t0 for row in compare_rows]
        ]
        valid = np.isfinite(actual) & np.isfinite(reference)
        corr = float(np.corrcoef(actual[valid], reference[valid])[0, 1])
        rows.append({
            "leaf": leaf,
            "pearson_corr": corr,
            "mean_abs_error": float(np.mean(np.abs(actual[valid] - reference[valid]))),
            "nan_agreement": float(np.mean(np.isfinite(actual) == np.isfinite(reference))),
        })
    rows.sort(key=lambda row: row["pearson_corr"])
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

