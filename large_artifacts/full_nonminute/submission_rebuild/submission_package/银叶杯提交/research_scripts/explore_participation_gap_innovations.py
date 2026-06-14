#!/usr/bin/env python3
"""Evaluate explicit participation-gap innovations and find a tenth robust factor."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, r"D:\yyb\submission_rebuild")
import analyze_explainable_submission as core  # noqa: E402


RESULTS = core.RESULTS
OUT = core.WORK / "innovation_candidate_matrices"
OUT.mkdir(parents=True, exist_ok=True)


INNOVATIONS = {
    "I1_count_ticket_balance": {
        "meaning": "低交易笔数集中度与低平均单笔金额共同出现时，刻画分散参与而非少量大单推动。",
        "terms": {"N4_count_hhi": -0.5, "N5_log_avg_ticket": -0.5},
    },
    "I2_count_toxicity_bridge": {
        "meaning": "交易笔数集中度与VPIN异常变化结合，刻画集中参与下的订单流毒性。",
        "terms": {"N4_count_hhi": -0.5, "F_COMBO_2_vpin_informed": -0.5},
    },
    "I3_ticket_liquidity_bridge": {
        "meaning": "平均单笔金额与分钟Amihud异常结合，刻画大单参与和流动性冲击的共同状态。",
        "terms": {"N5_log_avg_ticket": -0.5, "F_COMBO_4_amihud_hybrid": 0.5},
    },
    "I4_vwap_count_bridge": {
        "meaning": "收盘VWAP偏离与交易笔数集中度结合，检验集中交易推动的执行价格偏离。",
        "terms": {"F4_1_close_vs_vwap": -0.5, "N4_count_hhi": -0.5},
    },
    "I5_vwap_ticket_bridge": {
        "meaning": "上午下午VWAP迁移与平均单笔金额结合，检验大单推动的成本中枢变化。",
        "terms": {"F4_2_vwap_trend": -0.5, "N5_log_avg_ticket": -0.5},
    },
    "I6_intraday_ticket_bridge": {
        "meaning": "日内收益反转与大单金额占比结合，检验大单推动后的日内价格修复。",
        "terms": {"F1_3_intraday_mom": -0.5, "N6_large_ticket_amount_ratio": 0.5},
    },
    "I7_tail_ticket_amihud": {
        "meaning": "尾盘大单反转与分钟Amihud异常结合，检验尾盘流动性冲击后的修复。",
        "terms": {"N8_tail_ticket_reversal": 0.5, "F_COMBO_4_amihud_hybrid": 0.5},
    },
    "I8_count_hhi_vpin": {
        "meaning": "交易笔数集中度与VPIN结合，检验交易活跃集中和订单流毒性的共同变化。",
        "terms": {"N4_count_hhi": -0.5, "F6_3_vpin": -0.5},
    },
    "I9_count_corr_vwap": {
        "meaning": "成交笔数与价格相关性结合收盘VWAP偏离，检验参与放大与执行偏离是否共振。",
        "terms": {"N7_count_price_corr": -0.5, "F4_1_close_vs_vwap": -0.5},
    },
    "I10_volume_count_concentration_gap": {
        "meaning": "成交量HHI减去成交笔数HHI，刻画成交金额集中但交易笔数不集中时的单笔规模变化。",
        "terms": {"F5_1_volume_hhi": 0.5, "N4_count_hhi": -0.5},
    },
    "I11_open_participation_gap": {
        "meaning": "早盘成交量占比减去早盘成交笔数占比，刻画早盘平均单笔规模异常。",
        "terms": {"F5_2_open_vol_ratio": 0.5, "N2_open_count_ratio": -0.5},
    },
    "I12_close_participation_gap": {
        "meaning": "尾盘成交量占比减去尾盘成交笔数占比，刻画尾盘平均单笔规模异常。",
        "terms": {"F5_3_close_vol_ratio": 0.5, "N3_close_count_ratio": -0.5},
    },
    "I13_weighted_time_gap": {
        "meaning": "成交量加权时点与成交笔数加权时点之差，刻画大额订单相对普通交易更偏早盘还是尾盘。",
        "terms": {"F_COMBO_7_wat": -0.5, "N1_count_weighted_time": 0.5},
    },
}


def build_matrix(name, terms, leaf_paths, universe):
    path = OUT / f"{name}.npy"
    matrices = {leaf: np.load(leaf_paths[leaf], mmap_mode="r") for leaf in terms}
    shape = next(iter(matrices.values())).shape
    out = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=shape)
    out[:] = np.nan
    for t in range(shape[0]):
        row = np.zeros(shape[1], dtype=np.float64)
        valid_any = np.zeros(shape[1], dtype=bool)
        for leaf, weight in terms.items():
            values = matrices[leaf][t]
            valid = np.isfinite(values)
            row[valid] += weight * values[valid]
            valid_any |= valid
        row[~valid_any] = np.nan
        out[t] = core.cs_standardize(row, universe[t])
    out.flush()
    del out
    return path


def main():
    pipeline = core.DataPipeline(core.ROOT)
    t0 = pipeline.date_to_idx["2020-01-02"]
    is_stop_abs = pipeline.date_to_idx["2021-12-31"] + 1
    t1 = pipeline.date_to_idx["2023-12-29"] + 1
    is_stop = is_stop_abs - t0
    label = pipeline.fields["Label"][t0:t1]
    universe = pipeline.universe_mask[t0:t1]
    leaf_paths = {leaf: core.NORMALIZED / f"{core.safe_name(leaf)}.npy" for leaf in core.LEAVES}

    current = json.loads((RESULTS / "submission_final_manifest.json").read_text(encoding="utf-8"))["selected"]
    current_paths = {name: core.CANDIDATES / f"{core.safe_name(name)}.npy" for name in current}
    rows = []
    selected_path = None

    for name, spec in INNOVATIONS.items():
        print(f"Build and evaluate {name}")
        path = build_matrix(name, spec["terms"], leaf_paths, universe)
        matrix = np.load(path, mmap_mode="r")
        row = {
            "candidate": name,
            "meaning": spec["meaning"],
            "formula": core.explicit_formula(spec["terms"]),
        }
        for prefix, start, stop in (("is", 0, is_stop), ("oos", is_stop, len(label)), ("full", 0, len(label))):
            for key, value in core.metrics(matrix, label, universe, start, stop).items():
                row[f"{prefix}_{key}"] = value
        corrs = {}
        for old, old_path in current_paths.items():
            corrs[old] = abs(core.matrix_corr(matrix, np.load(old_path, mmap_mode="r"), universe, 0, len(label)))
        row["max_corr_vs_selected9"] = max(corrs.values())
        row["corr_vs_selected9"] = json.dumps(corrs, ensure_ascii=False)
        rows.append(row)

    frame = pd.DataFrame(rows)
    frame["robust"] = (
        (frame["is_pearson_ic"] > 0)
        & (frame["oos_pearson_ic"] > 0)
        & (frame["oos_annual_excess"] > 0)
        & (frame["max_corr_vs_selected9"] < 0.50)
    )
    frame = frame.sort_values(["robust", "is_pearson_ic", "is_annual_excess"], ascending=[False, False, False])
    frame.to_csv(RESULTS / "participation_gap_innovation_metrics.csv", index=False, encoding="utf-8-sig")
    eligible = frame[frame["robust"]]
    chosen = eligible.iloc[0]["candidate"] if not eligible.empty else None
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_selected9": current,
        "innovation_count": len(frame),
        "robust_eligible_count": len(eligible),
        "chosen_tenth": chosen,
        "chosen_matrix": str(OUT / f"{chosen}.npy") if chosen else None,
    }
    (RESULTS / "participation_gap_innovation_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(frame[["candidate", "robust", "is_pearson_ic", "is_annual_excess", "oos_pearson_ic", "oos_annual_excess", "oos_excess_sharpe", "max_corr_vs_selected9"]].to_string(index=False))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
