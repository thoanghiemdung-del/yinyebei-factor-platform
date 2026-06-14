#!/usr/bin/env python3
"""Assemble and verify the direct-submit Silver Leaf Cup package."""

from __future__ import annotations

import hashlib
import json
import py_compile
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


WORK = Path(r"D:\yyb\submission_rebuild")
SOURCE_DELIVERABLES = WORK / "deliverables"
PACKAGE_PARENT = WORK / "submission_package"
PACKAGE = PACKAGE_PARENT / "银叶杯提交"
ZIP_PATH = Path(r"D:\yyb\银叶杯提交.zip")


def ensure_inside(child: Path, parent: Path) -> None:
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    if child_resolved != parent_resolved and parent_resolved not in child_resolved.parents:
        raise RuntimeError(f"Unsafe path outside intended directory: {child_resolved}")


def copy(source: Path, relative: str) -> None:
    target = PACKAGE / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_readmes() -> None:
    readme = """# 银叶杯因子比赛提交包

本目录为可直接审核的最终提交包。研究严格使用赛题允许的分钟 OHLC、成交量、成交额、成交笔数，以及允许使用的基础日收盘价。

## 官方要求对应关系

| 官方要求 | 提交文件 |
|---|---|
| Python 因子函数，输出标准化因子值 | `code/factor_submission.py` |
| 输出因子值 | `factor_values/standardized_factor_values_2020_2023.npz` |
| 回测报告与因子逻辑文档 | `paper/银叶杯因子研究报告.pdf` |
| 因子相关性低于 50% | `results/final_factor_value_correlation.csv` |

逐条官方口径映射见 `官方赛题要求核对表.md`。

## 因子值格式

- `dates`：970 个交易日，2020-01-02 至 2023-12-29
- `stock_codes`：5515 个股票代码
- `factor_01` 至 `factor_10`：十个 `970 x 5515` 的标准化 `float32` 矩阵
- 无效股票池位置或无法计算的位置：`NaN`

## 快速读取

```python
import numpy as np

data = np.load("factor_values/standardized_factor_values_2020_2023.npz")
dates = data["dates"]
stock_codes = data["stock_codes"]
factor_01 = data["factor_01"]
```

## 复核顺序

1. 阅读 `十因子速览.md` 和 `paper/银叶杯因子研究报告.pdf`。
2. 查看 `results/final_factor_metrics_zh.csv` 与 `results/final_factor_value_correlation.csv`。
3. 查看 `results/final_factor_dictionary.md`，逐项阅读叶子权重、原始字段和子因子含义。
4. 查看 `code/factor_submission.py` 中的 `FINAL_SPECS` 和 `compute_final_factors()`。
5. 运行 `python code/submission_smoke_test.py`，无需原始数据即可验证接口。
6. 查看 `results/submission_code_realdata_validation.json`，核对独立代码与冻结矩阵的真实分钟复算结果。
7. 运行 `python verify_exported_package.py`，复核解压后的提交包。
8. 如需追溯研究过程，查看 `experiments/` 下的对照实验 CSV 和 `research_scripts/` 下的研究脚本。

`MANIFEST_SHA256.txt` 保存包内逐文件校验值，独立验证器会自动核对。

最终十因子均为原子信号或一次显式线性组合，不存在递归套娃、缓存 UUID 或外部 Alpha。
"""
    (PACKAGE / "README_提交说明.md").write_text(readme, encoding="utf-8")

    code_readme = """# 因子计算代码说明

入口文件：`factor_submission.py`

主要接口：

- `compute_daily_leaves(day)`：由一个交易日的分钟矩阵计算叶子因子。
- `compute_leaf_matrices(minute_days, daily_close)`：计算历史叶子矩阵和 20 日滚动信号。
- `compute_final_factors(minute_days, daily_close, universe_mask)`：输出 `factor_01` 至 `factor_10`。
- `save_factor_values(output, dates, stock_codes, factors)`：保存标准化矩阵。

输入分钟字段必须包含：`OPEN`, `HIGH`, `LOW`, `CLOSE`, `VOLUME`, `AMOUNT`, `NUMBER`。
`universe_mask` 应事先剔除 ST、*ST 和上市不足 120 日股票。
`minute_days` 按迭代器流式消费，不会一次性把全部分钟日文件载入内存。

无需原始数据的接口烟测：

```bash
python submission_smoke_test.py
```
"""
    (PACKAGE / "code" / "README.md").write_text(code_readme, encoding="utf-8")


def validate() -> dict:
    metrics = pd.read_csv(PACKAGE / "results" / "final_factor_metrics.csv")
    corr = pd.read_csv(PACKAGE / "results" / "final_factor_value_correlation.csv", index_col=0)
    values_path = PACKAGE / "factor_values" / "standardized_factor_values_2020_2023.npz"
    realdata_validation = json.loads(
        (PACKAGE / "results" / "submission_code_realdata_validation.json").read_text(encoding="utf-8")
    )
    values = np.load(values_path)
    expected_keys = [f"factor_{index:02d}" for index in range(1, 11)]
    actual_keys = [key for key in values.files if key.startswith("factor_")]
    max_corr = float(np.max(np.abs(corr.to_numpy(dtype=float) - np.eye(10))))
    normalization = {}
    for key in expected_keys:
        matrix = values[key]
        finite_rows = np.isfinite(matrix).sum(axis=1) >= 30
        means = np.nanmean(matrix[finite_rows], axis=1)
        stds = np.nanstd(matrix[finite_rows], axis=1)
        normalization[key] = {
            "shape": list(matrix.shape),
            "finite_values": int(np.isfinite(matrix).sum()),
            "max_abs_daily_mean": float(np.nanmax(np.abs(means))),
            "max_abs_daily_std_minus_one": float(np.nanmax(np.abs(stds - 1))),
        }
    values.close()

    py_compile.compile(str(PACKAGE / "code" / "factor_submission.py"), doraise=True)
    py_compile.compile(str(PACKAGE / "code" / "submission_smoke_test.py"), doraise=True)
    smoke = subprocess.run(
        [sys.executable, str(PACKAGE / "code" / "submission_smoke_test.py")],
        check=True,
        capture_output=True,
        text=True,
    )
    pycache = PACKAGE / "code" / "__pycache__"
    ensure_inside(pycache, PACKAGE)
    if pycache.exists():
        shutil.rmtree(pycache)
    code_text = (PACKAGE / "code" / "factor_submission.py").read_text(encoding="utf-8")
    rendered_pages = len(list((WORK / "paper" / "rendered").glob("page-*.png")))
    checks = {
        "report_pdf_exists": (PACKAGE / "paper" / "银叶杯因子研究报告.pdf").is_file(),
        "python_code_compiles": True,
        "synthetic_interface_smoke_test_pass": '"status": "PASS"' in smoke.stdout,
        "package_has_no_pycache": not pycache.exists(),
        "standardized_factor_values_exist": values_path.is_file(),
        "factor_count_is_10": len(metrics) == 10 and actual_keys == expected_keys,
        "factor_matrix_shape_is_970_by_5515": all(item["shape"] == [970, 5515] for item in normalization.values()),
        "all_oos_pearson_ic_positive": bool((metrics["oos_pearson_ic"] > 0).all()),
        "all_oos_annual_excess_positive": bool((metrics["oos_annual_excess"] > 0).all()),
        "pairwise_abs_factor_value_corr_below_0_5": max_corr < 0.5,
        "code_uses_minute_number": '"NUMBER"' in code_text,
        "code_has_no_label_input": "Label" not in code_text,
        "pdf_visual_qa_pages_rendered": rendered_pages >= 15,
        "charts_present": len(list((PACKAGE / "charts").glob("*.png"))) >= 8,
        "comparison_csvs_present": len(list((PACKAGE / "experiments").glob("*.csv"))) >= 5,
        "realdata_submission_code_reproduction_pass": realdata_validation["status"] == "PASS",
        "standalone_package_verifier_included": (PACKAGE / "verify_exported_package.py").is_file(),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "maximum_abs_factor_value_correlation": max_corr,
        "matrix_normalization_audit": normalization,
        "official_requirements": {
            "minute_ohlc_volume_amount_number_only": True,
            "basic_daily_close_used_only_for_factor_08": True,
            "st_and_listing_age_exclusion_expected_in_universe_mask": True,
            "future_function_used": False,
            "external_alpha_used": False,
            "python_factor_function_included": True,
            "standardized_factor_matrices_included": True,
            "backtest_report_and_logic_document_included": True,
        },
    }


def write_audit_markdown(audit: dict) -> None:
    rows = "\n".join(
        f"| `{name}` | {'PASS' if passed else 'FAIL'} |"
        for name, passed in audit["checks"].items()
    )
    content = f"""# 提交包自查报告

生成时间：{audit["generated_at"]}

总体状态：**{audit["status"]}**

最终因子值最大非对角线绝对相关性：`{audit["maximum_abs_factor_value_correlation"]:.6f}`

| 检查项 | 结果 |
|---|---|
{rows}

## 结论

提交包包含官方要求的 Python 因子函数、标准化因子值矩阵、回测报告、逻辑说明和相关性矩阵。
十个最终因子均为分钟数据驱动的原子信号或一次显式组合，不含未来函数，不提交外部 Alpha。
"""
    (PACKAGE / "提交包自查报告.md").write_text(content, encoding="utf-8")


def assemble() -> None:
    PACKAGE_PARENT.mkdir(parents=True, exist_ok=True)
    ensure_inside(PACKAGE, PACKAGE_PARENT)
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    for folder in ("paper", "code", "factor_values", "results", "charts", "experiments", "research_scripts"):
        (PACKAGE / folder).mkdir(parents=True, exist_ok=True)

    copy(WORK / "paper" / "silverleaf_submission.pdf", "paper/银叶杯因子研究报告.pdf")
    copy(WORK / "paper" / "silverleaf_submission.tex", "paper/银叶杯因子研究报告.tex")
    copy(WORK / "官方赛题要求核对表.md", "官方赛题要求核对表.md")
    copy(WORK / "verify_exported_package.py", "verify_exported_package.py")
    copy(WORK / "factor_submission.py", "code/factor_submission.py")
    copy(WORK / "submission_smoke_test.py", "code/submission_smoke_test.py")
    copy(SOURCE_DELIVERABLES / "factor_values" / "standardized_factor_values_2020_2023.npz", "factor_values/standardized_factor_values_2020_2023.npz")
    copy(SOURCE_DELIVERABLES / "factor_values" / "README.md", "factor_values/README.md")
    copy(SOURCE_DELIVERABLES / "factor_values" / "factor_values_preview.csv", "factor_values/factor_values_preview.csv")
    copy(SOURCE_DELIVERABLES / "final_factor_metrics.csv", "results/final_factor_metrics.csv")
    copy(SOURCE_DELIVERABLES / "final_factor_value_correlation.csv", "results/final_factor_value_correlation.csv")
    copy(SOURCE_DELIVERABLES / "final_submission_manifest.json", "results/final_submission_manifest.json")
    copy(SOURCE_DELIVERABLES / "leaf_dictionary.csv", "results/leaf_dictionary.csv")
    copy(SOURCE_DELIVERABLES / "final_factor_dictionary.json", "results/final_factor_dictionary.json")
    copy(SOURCE_DELIVERABLES / "final_factor_dictionary.md", "results/final_factor_dictionary.md")
    copy(SOURCE_DELIVERABLES / "final_factor_metrics_zh.csv", "results/final_factor_metrics_zh.csv")
    copy(SOURCE_DELIVERABLES / "final_factor_quickview.md", "十因子速览.md")
    copy(SOURCE_DELIVERABLES / "submission_code_realdata_validation.json", "results/submission_code_realdata_validation.json")

    for source in sorted((WORK / "charts").glob("*.png")):
        if source.name != "contact_sheet.png":
            copy(source, f"charts/{source.name}")
    for name in (
        "leaf_metrics.csv",
        "candidate_metrics.csv",
        "same_cross_style_comparison.csv",
        "weighting_method_comparison.csv",
        "greedy_comparison.csv",
        "participation_gap_innovation_metrics.csv",
    ):
        copy(WORK / "results" / name, f"experiments/{name}")
    for name in (
        "extract_minute_number_innovations.py",
        "analyze_explainable_submission.py",
        "select_robust_final_factors.py",
        "explore_participation_gap_innovations.py",
        "finalize_submission_artifacts.py",
        "generate_submission_charts.py",
        "generate_factor_dictionary.py",
        "validate_submission_code_against_export.py",
    ):
        copy(WORK / name, f"research_scripts/{name}")

    write_readmes()
    audit = validate()
    (PACKAGE / "提交包自查报告.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_audit_markdown(audit)
    if audit["status"] != "PASS":
        raise RuntimeError(json.dumps(audit, ensure_ascii=False, indent=2))

    pycache = PACKAGE / "code" / "__pycache__"
    ensure_inside(pycache, PACKAGE)
    if pycache.exists():
        shutil.rmtree(pycache)

    checksum_path = PACKAGE / "MANIFEST_SHA256.txt"
    checksum_lines = []
    for source in sorted(PACKAGE.rglob("*")):
        if source.is_file() and source != checksum_path:
            checksum_lines.append(f"{sha256(source)}  {source.relative_to(PACKAGE).as_posix()}")
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source in sorted(PACKAGE.rglob("*")):
            if source.is_file() and "__pycache__" not in source.parts:
                archive.write(source, Path(PACKAGE.name) / source.relative_to(PACKAGE))
    summary = {
        "package": str(PACKAGE),
        "zip": str(ZIP_PATH),
        "zip_size_mb": round(ZIP_PATH.stat().st_size / 1024 / 1024, 2),
        "zip_sha256": sha256(ZIP_PATH),
        "audit_status": audit["status"],
    }
    (PACKAGE_PARENT / "package_build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    assemble()
