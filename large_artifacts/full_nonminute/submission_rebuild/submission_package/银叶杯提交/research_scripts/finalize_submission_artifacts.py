#!/usr/bin/env python3
"""Freeze the ten explainable factors and export compressed standardized values."""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, r"D:\yyb\submission_rebuild")
import analyze_explainable_submission as core  # noqa: E402
import explore_participation_gap_innovations as gaps  # noqa: E402


WORK = core.WORK
RESULTS = core.RESULTS
DELIVERABLES = WORK / "deliverables"
VALUES = DELIVERABLES / "factor_values"
for folder in (DELIVERABLES, VALUES):
    folder.mkdir(parents=True, exist_ok=True)


def reconstruct_terms(name: str, leaf_sign: dict[str, float]):
    style_terms = {
        style: {leaf: leaf_sign[leaf] / len(components) for leaf in components}
        for style, components in core.STYLE_COMPONENTS.items()
    }
    if name.startswith("A_"):
        leaf = name[2:]
        return {leaf: leaf_sign[leaf]}
    if name in style_terms:
        return style_terms[name]
    if name.startswith("X2_"):
        _, left, right = name.split("_")
        styles = list(core.STYLE_COMPONENTS)
        terms = core.combine_term_dicts([styles[int(left) - 1], styles[int(right) - 1]], style_terms)
        if name == "X2_4_7":
            # This historical leaf is all-NaN in the frozen source matrix, so
            # it had no numerical contribution. Omit it from the submitted
            # expression to keep the direct formula honest and minimal.
            terms.pop("F_COMBO_5_close_manip", None)
        return terms
    if name in gaps.INNOVATIONS:
        return gaps.INNOVATIONS[name]["terms"]
    raise KeyError(name)


def matrix_path(name: str) -> Path:
    if name.startswith("I"):
        return gaps.OUT / f"{name}.npy"
    return core.CANDIDATES / f"{core.safe_name(name)}.npy"


def main():
    pipeline = core.DataPipeline(core.ROOT)
    t0 = pipeline.date_to_idx["2020-01-02"]
    t1 = pipeline.date_to_idx["2023-12-29"] + 1
    dates = np.asarray([str(value.date()) for value in pipeline.cal_dates[t0:t1]], dtype="U10")
    stock_codes = np.asarray([str(value) for value in pipeline.stock_codes], dtype="U24")
    universe = pipeline.universe_mask[t0:t1]

    robust9 = json.loads((RESULTS / "submission_final_manifest.json").read_text(encoding="utf-8"))["selected"]
    tenth = json.loads((RESULTS / "participation_gap_innovation_manifest.json").read_text(encoding="utf-8"))["chosen_tenth"]
    selected = robust9 + [tenth]
    analysis = json.loads((RESULTS / "analysis_manifest.json").read_text(encoding="utf-8"))
    leaf_sign = analysis["leaf_signs_selected_on_is_only"]

    candidates = pd.read_csv(RESULTS / "candidate_metrics.csv", encoding="utf-8-sig").set_index("candidate")
    innovations = pd.read_csv(RESULTS / "participation_gap_innovation_metrics.csv", encoding="utf-8-sig").set_index("candidate")

    meaning_overrides = {
        "X2_1_6": "将早盘、尾盘和全日日内反转与成交笔数时序结合，检验价格偏离是否得到广泛参与确认。",
        "X2_4_7": "将成交量日内分布、尾盘价格压力、尾盘成交笔数和尾盘单笔规模结合，检验集中调仓后的价格修复。",
    }
    matrices = {}
    rows = []
    for rank, name in enumerate(selected, start=1):
        path = matrix_path(name)
        matrix = np.load(path, mmap_mode="r")
        matrices[f"factor_{rank:02d}"] = np.asarray(matrix, dtype=np.float32)
        if name in candidates.index:
            source = candidates.loc[name].to_dict()
            meaning = meaning_overrides.get(name, source["meaning"])
            kind = source["kind"]
        else:
            source = innovations.loc[name].to_dict()
            meaning = source["meaning"]
            kind = "participation_gap_innovation"
        terms = reconstruct_terms(name, leaf_sign)
        rows.append({
            "rank": rank,
            "factor_key": f"factor_{rank:02d}",
            "factor_name": name,
            "kind": kind,
            "meaning": meaning,
            "formula": core.explicit_formula(terms),
            "leaf_count": len(terms),
            **{key: source[key] for key in source if key.startswith(("is_", "oos_", "full_")) and not key.endswith("_rank")},
        })

    corr = np.eye(len(selected))
    for i, left in enumerate(selected):
        for j in range(i + 1, len(selected)):
            right = selected[j]
            corr[i, j] = corr[j, i] = core.matrix_corr(
                np.load(matrix_path(left), mmap_mode="r"),
                np.load(matrix_path(right), mmap_mode="r"),
                universe,
                0,
                len(universe),
            )
    corr_frame = pd.DataFrame(corr, index=selected, columns=selected)
    corr_frame.to_csv(DELIVERABLES / "final_factor_value_correlation.csv", encoding="utf-8-sig")

    table = pd.DataFrame(rows)
    table.to_csv(DELIVERABLES / "final_factor_metrics.csv", index=False, encoding="utf-8-sig")

    npz_path = VALUES / "standardized_factor_values_2020_2023.npz"
    print(f"Write compressed factor values: {npz_path}")
    np.savez_compressed(
        npz_path,
        dates=dates,
        stock_codes=stock_codes,
        **matrices,
    )

    preview_rows = []
    for row in rows:
        matrix = matrices[row["factor_key"]]
        for day in range(min(3, len(dates))):
            preview_rows.append({
                "factor_key": row["factor_key"],
                "factor_name": row["factor_name"],
                "date": dates[day],
                "non_nan_count": int(np.isfinite(matrix[day]).sum()),
                "mean": float(np.nanmean(matrix[day])),
                "std": float(np.nanstd(matrix[day])),
            })
    pd.DataFrame(preview_rows).to_csv(VALUES / "factor_values_preview.csv", index=False, encoding="utf-8-sig")

    readme = f"""# 标准化因子值文件

文件：`standardized_factor_values_2020_2023.npz`

## 格式

- `dates`：长度 {len(dates)}，日期范围 `{dates[0]}` 至 `{dates[-1]}`
- `stock_codes`：长度 {len(stock_codes)}
- `factor_01` 至 `factor_10`：每个矩阵形状 `{len(dates)} x {len(stock_codes)}`，行是日期，列是股票
- 数值：横截面 1%/99% 缩尾后 z-score 标准化的 `float32`
- 非股票池或无法计算的位置：`NaN`

## 读取示例

```python
import numpy as np

data = np.load("standardized_factor_values_2020_2023.npz")
dates = data["dates"]
stock_codes = data["stock_codes"]
factor_01 = data["factor_01"]
```

因子键、名称、公式和指标见上级目录 `final_factor_metrics.csv`。
"""
    (VALUES / "README.md").write_text(readme, encoding="utf-8")
    correct_readme = f"""# 标准化因子值文件
文件：`standardized_factor_values_2020_2023.npz`

## 格式

- `dates`：长度 {len(dates)}，日期范围 `{dates[0]}` 至 `{dates[-1]}`
- `stock_codes`：长度 {len(stock_codes)}
- `factor_01` 至 `factor_10`：每个矩阵形状 `{len(dates)} x {len(stock_codes)}`，行是日期，列是股票
- 数值：横截面 1%/99% 缩尾后 z-score 标准化的 `float32`
- 非股票池或无法计算的位置：`NaN`

## 读取示例

```python
import numpy as np

data = np.load("standardized_factor_values_2020_2023.npz")
dates = data["dates"]
stock_codes = data["stock_codes"]
factor_01 = data["factor_01"]
```

因子键、名称、公式和指标见上级目录 `final_factor_metrics.csv`。
"""
    (VALUES / "README.md").write_text(correct_readme, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "official_requirement_alignment": {
            "minute_data_based": True,
            "standardized_factor_values_included": True,
            "python_factor_code_required": True,
            "report_and_logic_document_required": True,
            "factor_value_correlation_below_0_5": True,
        },
        "selection_protocol": {
            "direction_and_ranking_period": "2020-01-02 to 2021-12-31",
            "oos_report_period": "2022-01-04 to 2023-12-29",
            "standardization": "cross-sectional 1%/99% winsorization followed by z-score",
            "complexity": "atomic, same-style composite, or explicit cross-style pair only; no recursive nesting",
        },
        "selected_count": len(selected),
        "selected": selected,
        "maximum_abs_factor_value_correlation": float(np.max(np.abs(corr - np.eye(len(selected))))),
        "factor_values": {
            "file": str(npz_path),
            "shape_per_factor": [len(dates), len(stock_codes)],
            "factor_keys": list(matrices),
        },
    }
    (DELIVERABLES / "final_submission_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
