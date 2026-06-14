#!/usr/bin/env python3
"""Build and evaluate explicit minute-factor candidates for the competition package."""

from __future__ import annotations

import gc
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import rankdata


ROOT = Path(r"D:\yyb")
WORK = ROOT / "submission_rebuild"
NORMALIZED = WORK / "normalized_leaves"
CANDIDATES = WORK / "candidate_matrices"
RESULTS = WORK / "results"
for folder in (NORMALIZED, CANDIDATES, RESULTS):
    folder.mkdir(parents=True, exist_ok=True)

MODEL = next(ROOT.rglob("all_factors.pkl")).parent
sys.path.insert(0, str(MODEL))
from data_pipeline import DataPipeline  # noqa: E402


LEAVES = {
    "F1_1_first30_mom": ("日内价格", "开盘前30分钟收益，反映隔夜信息进入市场后的早盘价格压力。"),
    "F1_2_last30_mom": ("日内价格", "收盘前30分钟收益，反映尾盘调仓和集中执行造成的价格压力。"),
    "F1_3_intraday_mom": ("日内价格", "从开盘到收盘的日内收益，刻画当日订单流推动的价格偏离。"),
    "F3_1_realized_vol": ("日内波动", "分钟收益平方和构造的已实现波动率，刻画日内不确定性。"),
    "F3_2_vol_skew": ("日内波动", "上午与下午分钟波动率之比，刻画风险释放的时段不对称。"),
    "F4_1_close_vs_vwap": ("VWAP偏离", "收盘价相对全日VWAP的偏离，刻画尾盘价格与平均成交成本的距离。"),
    "F4_2_vwap_trend": ("VWAP偏离", "下午VWAP相对上午VWAP的变化，刻画订单流推动的日内成本中枢迁移。"),
    "F5_1_volume_hhi": ("成交分布", "分钟成交量HHI，刻画成交是否集中于少数时点。"),
    "F5_2_open_vol_ratio": ("成交分布", "开盘最初6根分钟bar成交量占比，刻画开盘阶段的信息到达和抢跑交易。"),
    "F5_3_close_vol_ratio": ("成交分布", "后30分钟成交量占比，刻画尾盘调仓和集中执行。"),
    "F5_5_smart_money_vol": ("订单流", "上涨分钟成交量占比，刻画买方订单流强弱。"),
    "F6_2_amihud_min": ("流动性", "分钟收益绝对值相对分钟成交额的均值，刻画单位资金推动价格的能力。"),
    "F6_3_vpin": ("订单流", "成交量加权绝对分钟收益相对成交量平方和，刻画订单流毒性。"),
    "F6_4_large_trade_ratio": ("订单流", "成交量超过分钟中位数两倍的成交占比，刻画大额执行集中度。"),
    "F6_5_roll_spread": ("流动性", "分钟收益负自协方差推导的Roll价差代理，刻画隐含交易成本。"),
    "F_COMBO_1_opening_confirm": ("显式分钟组合", "早盘与尾盘同方向时保留开盘驱动，检验全天方向确认。"),
    "F_COMBO_2_vpin_informed": ("显式分钟组合", "VPIN相对20日均值的变化，检验订单流毒性是否异常。"),
    "F_COMBO_4_amihud_hybrid": ("显式分钟组合", "分钟Amihud相对20日均值的变化，检验流动性冲击。"),
    "F_COMBO_5_close_manip": ("显式分钟组合", "尾盘价格变化与尾盘成交量不匹配时做反向处理，检验尾盘压力修复。"),
    "F_COMBO_7_wat": ("显式分钟组合", "成交量加权平均交易时点与日内方向结合，刻画信息到达时段。"),
    "F_COMBO_8_large_trade": ("显式分钟组合", "大额成交占比与日内方向结合，刻画大单推动。"),
    "F_COMBO_9_smart_money_vwap": ("显式分钟组合", "上涨分钟成交量占比与收盘VWAP偏离相乘，刻画买方订单流与价格偏离共振。"),
    "G2_1_intraday_ret5d": ("分钟×基础行情", "日内方向与5日收益同向时保留交互，刻画短期趋势确认。"),
    "G2_3_vwap_close_mom": ("分钟×基础行情", "收盘VWAP偏离与5日收益相乘，刻画短期趋势与执行价格共振。"),
    "G2_5_smart_money_rev": ("分钟×基础行情", "上涨分钟成交量占比乘以1日反转，刻画订单流确认后的价格修复。"),
    "N1_count_weighted_time": ("成交笔数", "成交笔数加权平均交易时点，刻画交易活跃度集中在早盘还是尾盘。"),
    "N2_open_count_ratio": ("成交笔数", "前30分钟成交笔数占比，刻画早盘交易参与度。"),
    "N3_close_count_ratio": ("成交笔数", "后30分钟成交笔数占比，刻画尾盘交易参与度。"),
    "N4_count_hhi": ("成交笔数", "分钟成交笔数HHI，刻画交易活跃度在时段上的集中程度。"),
    "N5_log_avg_ticket": ("成交笔数", "全天平均单笔金额的对数，刻画订单规模结构。"),
    "N6_large_ticket_amount_ratio": ("成交笔数", "高于两倍分钟中位单笔金额的成交额占比，刻画大单资金参与。"),
    "N7_count_price_corr": ("成交笔数", "分钟收益与成交笔数的相关性，刻画上涨或下跌时交易参与是否同步放大。"),
    "N8_tail_ticket_reversal": ("成交笔数", "尾盘收益反向乘以尾盘平均单笔金额相对全天水平，刻画尾盘大单压力后的修复。"),
}

STYLE_COMPONENTS = {
    "S1_intraday_reversal": ["F1_1_first30_mom", "F1_2_last30_mom", "F1_3_intraday_mom"],
    "S2_vwap_pressure": ["F4_1_close_vs_vwap", "F4_2_vwap_trend", "F_COMBO_9_smart_money_vwap"],
    "S3_liquidity_toxicity": ["F6_2_amihud_min", "F6_3_vpin", "F_COMBO_2_vpin_informed", "F_COMBO_4_amihud_hybrid"],
    "S4_volume_profile": ["F5_1_volume_hhi", "F5_2_open_vol_ratio", "F5_3_close_vol_ratio", "F_COMBO_7_wat"],
    "S5_large_ticket_flow": ["F6_4_large_trade_ratio", "F_COMBO_8_large_trade", "N5_log_avg_ticket", "N6_large_ticket_amount_ratio"],
    "S6_trade_count_profile": ["N1_count_weighted_time", "N2_open_count_ratio", "N3_close_count_ratio", "N4_count_hhi", "N7_count_price_corr"],
    "S7_closing_pressure": ["F1_2_last30_mom", "F5_3_close_vol_ratio", "F_COMBO_5_close_manip", "N3_close_count_ratio", "N8_tail_ticket_reversal"],
    "S8_cross_modal_reversal": ["G2_1_intraday_ret5d", "G2_3_vwap_close_mom", "G2_5_smart_money_rev"],
}

STYLE_MEANINGS = {
    "S1_intraday_reversal": "对早盘、尾盘和全天价格压力做反向处理，检验短期订单失衡后的价格修复。",
    "S2_vwap_pressure": "综合收盘-VWAP偏离、上午-下午VWAP迁移和聪明钱VWAP共振，检验执行价格偏离后的修复。",
    "S3_liquidity_toxicity": "综合分钟Amihud、VPIN及其异常变化，检验流动性冲击和订单流毒性。",
    "S4_volume_profile": "综合成交量集中度、开收盘成交量占比和成交量加权时点，检验交易时段结构。",
    "S5_large_ticket_flow": "综合大额成交占比、方向性大单和平均单笔金额，检验机构式大单执行压力。",
    "S6_trade_count_profile": "综合成交笔数时点、集中度和价格相关性，直接利用题目提供的成交笔数字段。",
    "S7_closing_pressure": "综合尾盘收益、尾盘量、尾盘异常和尾盘单笔金额，检验收盘前集中交易后的修复。",
    "S8_cross_modal_reversal": "把分钟订单流和基础行情的短期收益结合，检验日内确认与短期反转。",
}


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)


def open_output(path: Path, shape):
    mm = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=shape)
    mm[:] = np.nan
    return mm


def cs_standardize(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, np.nan, dtype=np.float32)
    valid = mask & np.isfinite(values)
    if valid.sum() < 30:
        return out
    data = values[valid].astype(np.float64, copy=False)
    lo, hi = np.percentile(data, [1.0, 99.0])
    clipped = np.clip(data, lo, hi)
    std = clipped.std()
    if std <= 1e-12:
        return out
    out[valid] = ((clipped - clipped.mean()) / std).astype(np.float32)
    return out


def normalize_source(name: str, source: np.ndarray, mask: np.ndarray, t0: int, t1: int) -> Path:
    path = NORMALIZED / f"{safe_name(name)}.npy"
    if path.exists():
        cached = np.load(path, mmap_mode="r")
        if cached.shape == (t1 - t0, source.shape[1]):
            return path
    print(f"Normalize leaf: {name}")
    out = open_output(path, (t1 - t0, source.shape[1]))
    for local_t, raw_t in enumerate(range(t0, t1)):
        out[local_t] = cs_standardize(source[raw_t], mask[raw_t])
    out.flush()
    del out
    return path


def metrics(matrix: np.ndarray, label: np.ndarray, universe: np.ndarray, start: int, stop: int) -> dict:
    pearson, rank_ic, daily_excess = [], [], []
    for t in range(start, stop):
        factor = matrix[t]
        lbl = label[t]
        valid = universe[t] & np.isfinite(factor) & np.isfinite(lbl)
        n = int(valid.sum())
        if n < 100:
            continue
        fv = factor[valid].astype(np.float64, copy=False)
        lv = lbl[valid].astype(np.float64, copy=False)
        pearson.append(float(np.corrcoef(fv, lv)[0, 1]))
        rank_ic.append(float(np.corrcoef(rankdata(fv), rankdata(lv))[0, 1]))
        n_top = max(1, int(n * 0.10))
        top = np.argpartition(fv, -n_top)[-n_top:]
        daily_excess.append(float(lv[top].mean() - lv.mean()))
    ex = np.asarray(daily_excess, dtype=float)
    if len(ex) < 30:
        return {"n_days": len(ex)}
    cumulative = np.cumsum(ex)
    drawdown = np.maximum.accumulate(cumulative) - cumulative
    return {
        "n_days": len(ex),
        "pearson_ic": float(np.nanmean(pearson)),
        "rank_ic": float(np.nanmean(rank_ic)),
        "icir": float(np.nanmean(rank_ic) / (np.nanstd(rank_ic) + 1e-12)),
        "annual_excess": float(np.nanmean(ex) * 250),
        "excess_sharpe": float(np.nanmean(ex) / (np.nanstd(ex) + 1e-12) * np.sqrt(250)),
        "max_drawdown": float(np.nanmax(drawdown)),
        "positive_day_ratio": float(np.mean(ex > 0)),
    }


def matrix_corr(a: np.ndarray, b: np.ndarray, universe: np.ndarray, start: int, stop: int) -> float:
    count = 0
    sx = sy = sxx = syy = sxy = 0.0
    for t in range(start, stop):
        valid = universe[t] & np.isfinite(a[t]) & np.isfinite(b[t])
        if not valid.any():
            continue
        x = a[t][valid].astype(np.float64, copy=False)
        y = b[t][valid].astype(np.float64, copy=False)
        count += len(x)
        sx += float(x.sum())
        sy += float(y.sum())
        sxx += float(x @ x)
        syy += float(y @ y)
        sxy += float(x @ y)
    if count < 100:
        return 1.0
    cov = sxy - sx * sy / count
    vx = sxx - sx * sx / count
    vy = syy - sy * sy / count
    if vx <= 1e-12 or vy <= 1e-12:
        return 1.0
    return float(cov / math.sqrt(vx * vy))


def build_matrix(name: str, terms: dict[str, float], leaf_paths: dict[str, Path], universe: np.ndarray) -> Path:
    path = CANDIDATES / f"{safe_name(name)}.npy"
    sources = {leaf: np.load(leaf_paths[leaf], mmap_mode="r") for leaf in terms}
    shape = next(iter(sources.values())).shape
    out = open_output(path, shape)
    for t in range(shape[0]):
        row = np.zeros(shape[1], dtype=np.float64)
        valid_any = np.zeros(shape[1], dtype=bool)
        for leaf, weight in terms.items():
            values = sources[leaf][t]
            valid = np.isfinite(values)
            row[valid] += weight * values[valid]
            valid_any |= valid
        row[~valid_any] = np.nan
        out[t] = cs_standardize(row, universe[t])
    out.flush()
    del out
    return path


def combine_term_dicts(component_names: list[str], candidate_terms: dict[str, dict[str, float]], weights=None):
    if weights is None:
        weights = [1.0 / len(component_names)] * len(component_names)
    combined = defaultdict(float)
    for component, outer_weight in zip(component_names, weights):
        for leaf, inner_weight in candidate_terms[component].items():
            combined[leaf] += outer_weight * inner_weight
    scale = sum(abs(value) for value in combined.values()) or 1.0
    return {key: value / scale for key, value in combined.items()}


def explicit_formula(terms: dict[str, float]) -> str:
    pieces = [f"{weight:+.6f} * z({leaf})" for leaf, weight in sorted(terms.items())]
    return " ".join(pieces).lstrip("+").strip()


def build_ridge_terms(style_names, style_terms, paths, label, universe, is_stop, ridge_lambda=50.0):
    matrices = [np.load(paths[name], mmap_mode="r") for name in style_names]
    n = len(matrices)
    xtx = np.zeros((n, n), dtype=np.float64)
    xty = np.zeros(n, dtype=np.float64)
    for t in range(is_stop):
        valid = universe[t] & np.isfinite(label[t])
        for matrix in matrices:
            valid &= np.isfinite(matrix[t])
        if valid.sum() < 100:
            continue
        x = np.column_stack([matrix[t][valid] for matrix in matrices]).astype(np.float64, copy=False)
        y = label[t][valid].astype(np.float64, copy=False)
        xtx += x.T @ x
        xty += x.T @ y
    coef = np.linalg.solve(xtx + ridge_lambda * np.eye(n), xty)
    if np.abs(coef).sum() <= 1e-12:
        coef = np.ones(n)
    weights = coef / np.abs(coef).sum()
    return combine_term_dicts(style_names, style_terms, weights), weights.tolist()


def main():
    print("Load alignment metadata and factor memmaps...")
    pipeline = DataPipeline(ROOT)
    raw = joblib.load(MODEL / "all_factors.pkl", mmap_mode="r")
    innovations = {path.stem: np.load(path, mmap_mode="r") for path in (WORK / "innovations").glob("N*.npy")}
    raw.update(innovations)

    t0 = pipeline.date_to_idx["2020-01-02"]
    is_stop_abs = pipeline.date_to_idx["2021-12-31"] + 1
    t1 = pipeline.date_to_idx["2023-12-29"] + 1
    is_stop = is_stop_abs - t0
    label = pipeline.fields["Label"][t0:t1]
    universe = pipeline.universe_mask[t0:t1]

    leaf_paths = {}
    for leaf in LEAVES:
        leaf_paths[leaf] = normalize_source(leaf, raw[leaf], pipeline.universe_mask, t0, t1)

    print("Determine leaf directions on 2020-2021 only...")
    leaf_rows = []
    leaf_sign = {}
    for leaf in LEAVES:
        matrix = np.load(leaf_paths[leaf], mmap_mode="r")
        is_metrics = metrics(matrix, label, universe, 0, is_stop)
        sign = 1.0 if is_metrics.get("pearson_ic", 0.0) >= 0 else -1.0
        leaf_sign[leaf] = sign
        oos_metrics = metrics(matrix * sign, label, universe, is_stop, len(label))
        leaf_rows.append({
            "candidate": leaf,
            "style": LEAVES[leaf][0],
            "meaning": LEAVES[leaf][1],
            "direction": int(sign),
            **{f"is_{key}": value for key, value in metrics(matrix * sign, label, universe, 0, is_stop).items()},
            **{f"oos_{key}": value for key, value in oos_metrics.items()},
        })
    pd.DataFrame(leaf_rows).to_csv(RESULTS / "leaf_metrics.csv", index=False, encoding="utf-8-sig")

    candidate_terms = {}
    candidate_meta = {}
    candidate_paths = {}

    def register(name: str, terms: dict[str, float], kind: str, style: str, meaning: str):
        candidate_terms[name] = terms
        candidate_meta[name] = {"kind": kind, "style": style, "meaning": meaning}
        candidate_paths[name] = build_matrix(name, terms, leaf_paths, universe)

    print("Build oriented atomic candidates...")
    for leaf, (style, meaning) in LEAVES.items():
        register(f"A_{leaf}", {leaf: leaf_sign[leaf]}, "atomic", style, meaning)

    print("Build same-style explicit composites...")
    for style, components in STYLE_COMPONENTS.items():
        terms = {leaf: leaf_sign[leaf] / len(components) for leaf in components}
        register(style, terms, "same_style", style, STYLE_MEANINGS[style])

    print("Build explicit cross-style pairs and triples...")
    style_names = list(STYLE_COMPONENTS)
    for i in range(len(style_names)):
        for j in range(i + 1, len(style_names)):
            names = [style_names[i], style_names[j]]
            name = f"X2_{i+1}_{j+1}"
            register(name, combine_term_dicts(names, candidate_terms), "cross_style_pair", name,
                     f"等权合并 {style_names[i]} 与 {style_names[j]}，保持叶子公式完全展开。")
    chosen_triples = [(0, 1, 2), (0, 5, 6), (1, 4, 7), (2, 5, 7), (3, 4, 6), (0, 2, 7), (1, 5, 6), (2, 4, 7)]
    for a, b, c in chosen_triples:
        names = [style_names[a], style_names[b], style_names[c]]
        name = f"X3_{a+1}_{b+1}_{c+1}"
        register(name, combine_term_dicts(names, candidate_terms), "cross_style_triple", name,
                 f"等权合并 {', '.join(names)}，保持叶子公式完全展开。")

    print("Evaluate candidates...")
    rows = []
    for index, name in enumerate(candidate_paths, start=1):
        matrix = np.load(candidate_paths[name], mmap_mode="r")
        row = {"candidate": name, **candidate_meta[name], "formula": explicit_formula(candidate_terms[name])}
        for prefix, start, stop in (("is", 0, is_stop), ("oos", is_stop, len(label)), ("full", 0, len(label))):
            for key, value in metrics(matrix, label, universe, start, stop).items():
                row[f"{prefix}_{key}"] = value
        rows.append(row)
        if index % 10 == 0:
            print(f"Evaluated {index}/{len(candidate_paths)} candidates")
    frame = pd.DataFrame(rows)
    frame["is_ic_rank"] = frame["is_pearson_ic"].rank(pct=True)
    frame["is_excess_rank"] = frame["is_annual_excess"].rank(pct=True)
    frame["is_balanced_score"] = 0.5 * frame["is_ic_rank"] + 0.5 * frame["is_excess_rank"]
    frame = frame.sort_values(["is_balanced_score", "is_pearson_ic"], ascending=False)
    frame.to_csv(RESULTS / "candidate_metrics.csv", index=False, encoding="utf-8-sig")

    print("Build weighting-method comparison...")
    style_eval = frame[frame["kind"] == "same_style"].set_index("candidate")
    icir_weights = np.abs(style_eval.loc[style_names, "is_icir"].fillna(0).to_numpy(dtype=float))
    icir_weights = icir_weights / (icir_weights.sum() or 1.0)
    weighting = {
        "W_equal": (combine_term_dicts(style_names, candidate_terms), [1.0 / len(style_names)] * len(style_names)),
        "W_icir": (combine_term_dicts(style_names, candidate_terms, icir_weights), icir_weights.tolist()),
    }
    ridge_terms, ridge_weights = build_ridge_terms(style_names, candidate_terms, candidate_paths, label, universe, is_stop)
    weighting["W_ridge"] = (ridge_terms, ridge_weights)
    weight_rows = []
    for name, (terms, weights) in weighting.items():
        path = build_matrix(name, terms, leaf_paths, universe)
        candidate_paths[name] = path
        candidate_terms[name] = terms
        matrix = np.load(path, mmap_mode="r")
        row = {"method": name, "style_weights": json.dumps(dict(zip(style_names, weights)), ensure_ascii=False), "formula": explicit_formula(terms)}
        for prefix, start, stop in (("is", 0, is_stop), ("oos", is_stop, len(label)), ("full", 0, len(label))):
            for key, value in metrics(matrix, label, universe, start, stop).items():
                row[f"{prefix}_{key}"] = value
        weight_rows.append(row)

    lgb = np.load(MODEL / "ensemble_lgb.npy", mmap_mode="r")
    lgb_row = {"method": "W_lightgbm_benchmark", "style_weights": "opaque nonlinear benchmark; not submitted", "formula": "Purged walk-forward LightGBM benchmark"}
    for prefix, start, stop in (("is", 0, is_stop), ("oos", is_stop, len(label)), ("full", 0, len(label))):
        for key, value in metrics(lgb, label, universe, start, stop).items():
            lgb_row[f"{prefix}_{key}"] = value
    weight_rows.append(lgb_row)
    pd.DataFrame(weight_rows).to_csv(RESULTS / "weighting_method_comparison.csv", index=False, encoding="utf-8-sig")

    print("Run transparent greedy comparisons...")
    path_map = dict(candidate_paths)
    metric_map = frame.set_index("candidate").to_dict("index")
    pool = frame[frame["kind"].isin(["atomic", "same_style", "cross_style_pair", "cross_style_triple"])]["candidate"].tolist()

    def greedy(sort_metric: str, threshold: float, max_items=20):
        ordered = sorted(pool, key=lambda name: metric_map[name].get(sort_metric, -999), reverse=True)
        selected = []
        for name in ordered:
            matrix = np.load(path_map[name], mmap_mode="r")
            corrs = [abs(matrix_corr(matrix, np.load(path_map[old], mmap_mode="r"), universe, 0, len(label))) for old in selected]
            if not corrs or max(corrs) < threshold:
                selected.append(name)
            if len(selected) >= max_items:
                break
        return selected

    greedy_rows = []
    for sort_metric in ["is_pearson_ic", "is_annual_excess", "is_excess_sharpe", "is_balanced_score"]:
        selected = greedy(sort_metric, 0.50)
        subset = frame.set_index("candidate").loc[selected]
        greedy_rows.append({
            "sort_metric": sort_metric,
            "threshold": 0.50,
            "selected_count": len(selected),
            "selected": json.dumps(selected, ensure_ascii=False),
            "mean_oos_pearson_ic": subset["oos_pearson_ic"].mean(),
            "mean_oos_annual_excess": subset["oos_annual_excess"].mean(),
            "mean_oos_excess_sharpe": subset["oos_excess_sharpe"].mean(),
        })
    for threshold in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        selected = greedy("is_balanced_score", threshold)
        subset = frame.set_index("candidate").loc[selected]
        greedy_rows.append({
            "sort_metric": "is_balanced_score",
            "threshold": threshold,
            "selected_count": len(selected),
            "selected": json.dumps(selected, ensure_ascii=False),
            "mean_oos_pearson_ic": subset["oos_pearson_ic"].mean(),
            "mean_oos_annual_excess": subset["oos_annual_excess"].mean(),
            "mean_oos_excess_sharpe": subset["oos_excess_sharpe"].mean(),
        })
    pd.DataFrame(greedy_rows).to_csv(RESULTS / "greedy_comparison.csv", index=False, encoding="utf-8-sig")

    print("Select explainable final portfolio with complexity quotas...")
    quotas = {"atomic": 6, "same_style": 4, "cross_style_pair": 2, "cross_style_triple": 0}
    used = defaultdict(int)
    selected = []
    corr_rows = []
    for name in pool:
        meta = metric_map[name]
        kind = meta["kind"]
        if used[kind] >= quotas.get(kind, 0):
            continue
        matrix = np.load(path_map[name], mmap_mode="r")
        corrs = [(old, abs(matrix_corr(matrix, np.load(path_map[old], mmap_mode="r"), universe, 0, len(label)))) for old in selected]
        max_corr = max([value for _, value in corrs] or [0.0])
        if max_corr >= 0.50:
            continue
        selected.append(name)
        used[kind] += 1
        corr_rows.append({"candidate": name, "max_corr_to_previous": max_corr})
        if len(selected) >= 10:
            break

    final = frame.set_index("candidate").loc[selected].reset_index()
    final = final.merge(pd.DataFrame(corr_rows), on="candidate", how="left")
    final["formula"] = [explicit_formula(candidate_terms[name]) for name in final["candidate"]]
    final.to_csv(RESULTS / "final_explainable_factors.csv", index=False, encoding="utf-8-sig")

    corr_matrix = np.eye(len(selected))
    for i, left in enumerate(selected):
        for j in range(i + 1, len(selected)):
            right = selected[j]
            value = matrix_corr(np.load(path_map[left], mmap_mode="r"), np.load(path_map[right], mmap_mode="r"), universe, 0, len(label))
            corr_matrix[i, j] = corr_matrix[j, i] = value
    pd.DataFrame(corr_matrix, index=selected, columns=selected).to_csv(RESULTS / "final_factor_value_correlation.csv", encoding="utf-8-sig")

    by_kind = frame.groupby("kind").agg(
        candidates=("candidate", "count"),
        mean_oos_pearson_ic=("oos_pearson_ic", "mean"),
        median_oos_pearson_ic=("oos_pearson_ic", "median"),
        mean_oos_annual_excess=("oos_annual_excess", "mean"),
        median_oos_annual_excess=("oos_annual_excess", "median"),
        mean_oos_excess_sharpe=("oos_excess_sharpe", "mean"),
    ).reset_index()
    by_kind.to_csv(RESULTS / "same_cross_style_comparison.csv", index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": {
            "selection_period": "2020-01-02 to 2021-12-31",
            "oos_report_period": "2022-01-04 to 2023-12-29",
            "standardization": "cross-sectional 1%/99% winsorization followed by z-score",
            "selection_score": "0.5 * percentile_rank(IS Pearson IC) + 0.5 * percentile_rank(IS annual Top10%-market excess)",
            "final_factor_value_correlation_constraint": "absolute full-period aligned factor-value Pearson correlation < 0.50",
            "complexity_policy": "explicit flattened formulas only; maximum one combination layer; no UUID nesting",
        },
        "selected": selected,
        "maximum_abs_factor_value_correlation": float(np.max(np.abs(corr_matrix - np.eye(len(selected))))) if len(selected) > 1 else 0.0,
        "candidate_count": len(frame),
        "leaf_count": len(LEAVES),
        "leaf_signs_selected_on_is_only": leaf_sign,
        "leaf_definitions": {name: {"style": style, "meaning": meaning} for name, (style, meaning) in LEAVES.items()},
        "style_definitions": STYLE_MEANINGS,
    }
    (RESULTS / "analysis_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    gc.collect()


if __name__ == "__main__":
    main()
