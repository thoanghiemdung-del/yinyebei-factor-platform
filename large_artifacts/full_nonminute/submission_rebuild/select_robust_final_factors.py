#!/usr/bin/env python3
"""Select a diverse, interpretable final factor set with bounded complexity."""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


sys.path.insert(0, r"D:\yyb\submission_rebuild")
import analyze_explainable_submission as core  # noqa: E402


RESULTS = core.RESULTS
CACHE_PATH = RESULTS / "robust_pairwise_corr_cache.json"


def main():
    pipeline = core.DataPipeline(core.ROOT)
    t0 = pipeline.date_to_idx["2020-01-02"]
    t1 = pipeline.date_to_idx["2023-12-29"] + 1
    universe = pipeline.universe_mask[t0:t1]
    frame = pd.read_csv(RESULTS / "candidate_metrics.csv", encoding="utf-8-sig")
    robust = frame[
        (frame["kind"] != "cross_style_triple")
        & (frame["is_pearson_ic"] > 0)
        & (frame["oos_pearson_ic"] > 0)
        & (frame["oos_annual_excess"] > 0)
    ].copy()
    robust = robust.sort_values("is_balanced_score", ascending=False)
    rows = robust.set_index("candidate").to_dict("index")
    names = robust["candidate"].tolist()

    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    else:
        cache = {}

    def matrix(name):
        return np.load(core.CANDIDATES / f"{core.safe_name(name)}.npy", mmap_mode="r")

    def corr(left, right):
        key = "||".join(sorted([left, right]))
        if key not in cache:
            value = abs(core.matrix_corr(matrix(left), matrix(right), universe, 0, len(universe)))
            cache[key] = value
            if len(cache) % 25 == 0:
                CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"Cached {len(cache)} pairwise correlations")
        return float(cache[key])

    quotas = {"atomic": 6, "same_style": 4, "cross_style_pair": 3}
    complexity_penalty = {"atomic": 0.00, "same_style": 0.015, "cross_style_pair": 0.08}
    random.seed(20260602)

    def attempt(order):
        selected = []
        kinds = Counter()
        for name in order:
            kind = rows[name]["kind"]
            if kinds[kind] >= quotas[kind]:
                continue
            if any(corr(name, old) >= 0.50 for old in selected):
                continue
            selected.append(name)
            kinds[kind] += 1
            if len(selected) >= 10:
                break
        score = sum(float(rows[name]["is_balanced_score"]) - complexity_penalty[rows[name]["kind"]] for name in selected)
        score += 0.15 * len(selected)
        score += 0.04 * len(set(rows[name]["style"] for name in selected))
        return score, selected

    base = sorted(names, key=lambda name: float(rows[name]["is_balanced_score"]) - complexity_penalty[rows[name]["kind"]], reverse=True)
    best = attempt(base)
    for _ in range(1500):
        order = sorted(
            names,
            key=lambda name: float(rows[name]["is_balanced_score"])
            - complexity_penalty[rows[name]["kind"]]
            + random.gauss(0, 0.20),
            reverse=True,
        )
        result = attempt(order)
        if (len(result[1]), result[0]) > (len(best[1]), best[0]):
            best = result

    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    selected = best[1]
    final = robust.set_index("candidate").loc[selected].reset_index()

    matrix_corr = np.eye(len(selected))
    for i, left in enumerate(selected):
        for j in range(i + 1, len(selected)):
            matrix_corr[i, j] = matrix_corr[j, i] = corr(left, selected[j])
    corr_frame = pd.DataFrame(matrix_corr, index=selected, columns=selected)
    corr_frame.to_csv(RESULTS / "submission_final_factor_value_correlation.csv", encoding="utf-8-sig")

    final["selection_rank"] = np.arange(1, len(final) + 1)
    final.to_csv(RESULTS / "submission_final_factors.csv", index=False, encoding="utf-8-sig")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "selection_policy": {
            "robustness_filter": "IS Pearson IC > 0; OOS Pearson IC > 0; OOS annual Top10%-market excess > 0",
            "factor_value_correlation": "absolute aligned full-period Pearson correlation < 0.50",
            "complexity": "atomic <= 6; same-style composites <= 4; explicit cross-style pairs <= 3; no triples; no recursive nesting",
            "ranking": "IS balanced score with complexity penalty; randomized greedy search; OOS magnitudes not used for ordering",
        },
        "candidate_pool_count": len(names),
        "selected_count": len(selected),
        "selected": selected,
        "selected_kind_counts": dict(Counter(rows[name]["kind"] for name in selected)),
        "maximum_abs_factor_value_correlation": float(np.max(np.abs(matrix_corr - np.eye(len(selected))))) if len(selected) > 1 else 0.0,
        "correlation_cache_pairs": len(cache),
    }
    (RESULTS / "submission_final_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
