#!/usr/bin/env python3
"""Generate submission-ready PNG charts without external plotting packages."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


WORK = Path(r"D:\yyb\submission_rebuild")
RESULTS = WORK / "results"
DELIVERABLES = WORK / "deliverables"
OUT = WORK / "charts"
OUT.mkdir(parents=True, exist_ok=True)

FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD_PATH = Path(r"C:\Windows\Fonts\msyhbd.ttc")
COLORS = ["#2E6E9E", "#D97A2B", "#4B8B5A", "#9B5CA5", "#C44E52", "#8172B2", "#55A868", "#CCB974", "#4C72B0", "#64B5CD"]
BG = "#FAFBFD"
INK = "#25313C"
GRID = "#D9E0E6"


def font(size: int, bold: bool = False):
    path = FONT_BOLD_PATH if bold and FONT_BOLD_PATH.exists() else FONT_PATH
    return ImageFont.truetype(str(path), size=size)


def canvas(title: str, subtitle: str = ""):
    image = Image.new("RGB", (1800, 1050), BG)
    draw = ImageDraw.Draw(image)
    draw.text((75, 38), title, fill=INK, font=font(42, True))
    if subtitle:
        draw.text((78, 96), subtitle, fill="#63717E", font=font(22))
    return image, draw


def text(draw, xy, value, size=22, fill=INK, bold=False, anchor=None):
    draw.text(xy, str(value), fill=fill, font=font(size, bold), anchor=anchor)


def scaled_y(value: float, lo: float, hi: float, top: int, bottom: int):
    if hi <= lo:
        return bottom
    return bottom - (value - lo) / (hi - lo) * (bottom - top)


def draw_bar_panel(draw, box, labels, values, panel_title, value_format="{:.3f}", color=None):
    left, top, right, bottom = box
    color = color or COLORS[0]
    vals = np.asarray(values, dtype=float)
    lo = min(0.0, float(np.nanmin(vals)) * 1.15)
    hi = max(0.01, float(np.nanmax(vals)) * 1.15)
    if lo == hi:
        hi += 1
    zero_y = scaled_y(0, lo, hi, top + 70, bottom - 120)
    text(draw, (left, top), panel_title, 27, bold=True)
    draw.line((left + 85, zero_y, right - 15, zero_y), fill="#83909C", width=2)
    n = len(labels)
    plot_left, plot_right = left + 95, right - 20
    step = (plot_right - plot_left) / max(n, 1)
    width = max(18, min(78, int(step * 0.55)))
    for index, (label, value) in enumerate(zip(labels, vals)):
        x = plot_left + step * (index + 0.5)
        y = scaled_y(value, lo, hi, top + 70, bottom - 120)
        y0, y1 = sorted((zero_y, y))
        draw.rounded_rectangle((x - width / 2, y0, x + width / 2, y1), radius=5, fill=color)
        text(draw, (x, y - 12 if value >= 0 else y + 12), value_format.format(value), 18, fill=INK, anchor="ms" if value >= 0 else "ma")
        text(draw, (x, bottom - 95), label, 18, fill=INK, anchor="ma")
    for tick in np.linspace(lo, hi, 5):
        y = scaled_y(tick, lo, hi, top + 70, bottom - 120)
        draw.line((left + 75, y, right - 15, y), fill=GRID, width=1)
        text(draw, (left + 66, y), value_format.format(tick), 16, fill="#71808D", anchor="rm")


def draw_line_panel(draw, box, xvalues, series, panel_title, y_format="{:.3f}"):
    left, top, right, bottom = box
    text(draw, (left, top), panel_title, 27, bold=True)
    all_values = np.concatenate([np.asarray(values, float) for _, values, _ in series])
    lo = min(0.0, float(np.nanmin(all_values)) * 1.15)
    hi = max(0.01, float(np.nanmax(all_values)) * 1.15)
    plot_left, plot_right = left + 95, right - 30
    plot_top, plot_bottom = top + 70, bottom - 100
    for tick in np.linspace(lo, hi, 5):
        y = scaled_y(tick, lo, hi, plot_top, plot_bottom)
        draw.line((plot_left, y, plot_right, y), fill=GRID, width=1)
        text(draw, (plot_left - 12, y), y_format.format(tick), 16, fill="#71808D", anchor="rm")
    xvalues = np.asarray(xvalues, float)
    xmin, xmax = float(xvalues.min()), float(xvalues.max())
    def xcoord(value):
        return plot_left + (value - xmin) / max(xmax - xmin, 1e-10) * (plot_right - plot_left)
    for value in xvalues:
        x = xcoord(value)
        text(draw, (x, plot_bottom + 30), f"{value:g}", 17, fill=INK, anchor="ma")
    for name, values, color in series:
        points = [(xcoord(x), scaled_y(float(y), lo, hi, plot_top, plot_bottom)) for x, y in zip(xvalues, values)]
        draw.line(points, fill=color, width=5, joint="curve")
        for x, y in points:
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)
    legend_x = plot_left
    for name, _, color in series:
        draw.rounded_rectangle((legend_x, bottom - 55, legend_x + 28, bottom - 35), radius=4, fill=color)
        text(draw, (legend_x + 38, bottom - 59), name, 18)
        legend_x += 235


def save(image, name):
    path = OUT / name
    image.save(path, optimize=True)
    return str(path)


def final_overview():
    frame = pd.read_csv(DELIVERABLES / "final_factor_metrics.csv")
    labels = [f"F{i:02d}" for i in frame["rank"]]
    image, draw = canvas("最终十因子：样本外指标概览", "样本外区间：2022-01-04 至 2023-12-29；年化超额收益为 Top10% 组合相对全 A 均值")
    draw_bar_panel(draw, (70, 170, 885, 970), labels, frame["oos_pearson_ic"], "样本外 Pearson IC", "{:.3f}", COLORS[0])
    draw_bar_panel(draw, (930, 170, 1740, 970), labels, frame["oos_annual_excess"] * 100, "样本外年化超额收益（%）", "{:.1f}", COLORS[2])
    return save(image, "01_final_metric_overview.png")


def corr_heatmap():
    frame = pd.read_csv(DELIVERABLES / "final_factor_value_correlation.csv", index_col=0)
    values = frame.to_numpy(float)
    image, draw = canvas("最终十因子：因子值相关性热力图", "所有非对角线绝对相关性均小于 0.50；最大值为 0.4943")
    left, top, cell = 355, 180, 72
    labels = [f"F{i:02d}" for i in range(1, 11)]
    for i, label in enumerate(labels):
        text(draw, (left - 18, top + i * cell + cell / 2), label, 20, anchor="rm")
        text(draw, (left + i * cell + cell / 2, top - 18), label, 20, anchor="ms")
    for row in range(10):
        for col in range(10):
            value = values[row, col]
            if row == col:
                color = "#D7DEE5"
            else:
                intensity = min(abs(value) / 0.5, 1.0)
                color = tuple(int(247 * (1 - intensity) + channel * intensity) for channel in (46, 110, 158))
            x0, y0 = left + col * cell, top + row * cell
            draw.rectangle((x0, y0, x0 + cell - 2, y0 + cell - 2), fill=color)
            text(draw, (x0 + cell / 2, y0 + cell / 2), f"{value:.2f}", 16, fill="#FFFFFF" if row != col and abs(value) > 0.25 else INK, anchor="mm")
    text(draw, (1180, 305), "筛选约束", 30, bold=True)
    text(draw, (1180, 375), "|corr(Fi, Fj)| < 0.50", 27, fill=COLORS[0], bold=True)
    text(draw, (1180, 450), f"最大非对角线绝对值：{np.max(np.abs(values - np.eye(10))):.4f}", 22)
    text(draw, (1180, 510), "相关性基于全样本期标准化因子值计算", 20, fill="#63717E")
    return save(image, "02_final_corr_heatmap.png")


def same_cross_style():
    frame = pd.read_csv(RESULTS / "same_cross_style_comparison.csv")
    order = ["atomic", "same_style", "cross_style_pair", "cross_style_triple"]
    frame = frame.set_index("kind").loc[order]
    labels = ["原子", "同风格", "跨风格双因子", "跨风格三因子"]
    image, draw = canvas("组合结构对照：跨风格组合优于机械堆叠", "统计对象为候选池；最终提交仍限制在原子、同风格和可解释跨风格双因子")
    draw_bar_panel(draw, (70, 170, 885, 970), labels, frame["mean_oos_pearson_ic"], "候选平均样本外 Pearson IC", "{:.3f}", COLORS[0])
    draw_bar_panel(draw, (930, 170, 1740, 970), labels, frame["mean_oos_annual_excess"] * 100, "候选平均样本外年化超额收益（%）", "{:.1f}", COLORS[1])
    return save(image, "03_same_cross_style_comparison.png")


def weighting_methods():
    frame = pd.read_csv(RESULTS / "weighting_method_comparison.csv")
    labels = ["等权", "ICIR 加权", "Ridge", "LightGBM\n对照"]
    image, draw = canvas("加权方式对照：透明组合与 LightGBM 基准", "LightGBM 仅作非线性研究基准，不作为最终提交因子")
    draw_bar_panel(draw, (70, 170, 885, 970), labels, frame["oos_pearson_ic"], "样本外 Pearson IC", "{:.3f}", COLORS[0])
    draw_bar_panel(draw, (930, 170, 1740, 970), labels, frame["oos_annual_excess"] * 100, "样本外年化超额收益（%）", "{:.1f}", COLORS[2])
    return save(image, "04_weighting_method_comparison.png")


def greedy_rankings():
    frame = pd.read_csv(RESULTS / "greedy_comparison.csv")
    frame = frame[(frame["threshold"] == 0.5) & frame["sort_metric"].isin(["is_pearson_ic", "is_annual_excess", "is_excess_sharpe", "is_balanced_score"])]
    labels = ["IC", "年化超额", "Sharpe", "平衡分"]
    image, draw = canvas("贪心排序标准对照", "相关性阈值固定为 0.50；排序只使用 2020-2021 样本内信息")
    draw_bar_panel(draw, (70, 170, 885, 970), labels, frame["mean_oos_pearson_ic"], "入选池平均样本外 Pearson IC", "{:.3f}", COLORS[0])
    draw_bar_panel(draw, (930, 170, 1740, 970), labels, frame["mean_oos_annual_excess"] * 100, "入选池平均样本外年化超额收益（%）", "{:.1f}", COLORS[1])
    return save(image, "05_greedy_ranking_comparison.png")


def threshold_sensitivity():
    frame = pd.read_csv(RESULTS / "greedy_comparison.csv")
    frame = frame[(frame["sort_metric"] == "is_balanced_score") & frame["threshold"].between(0.25, 0.60)].sort_values("threshold")
    x = frame["threshold"].to_numpy(float)
    image, draw = canvas("贪心相关性阈值敏感性", "排序标准固定为样本内平衡分；阈值越宽松，数量增加但平均质量并不单调改善")
    draw_line_panel(draw, (70, 170, 885, 970), x, [
        ("平均样本外 Pearson IC", frame["mean_oos_pearson_ic"], COLORS[0]),
    ], "平均样本外 Pearson IC", "{:.3f}")
    draw_line_panel(draw, (930, 170, 1740, 970), x, [
        ("因子数量 / 20", frame["selected_count"] / 20, COLORS[3]),
        ("平均样本外 Sharpe / 3", frame["mean_oos_excess_sharpe"] / 3, COLORS[1]),
    ], "数量与 Sharpe（归一化展示）", "{:.2f}")
    return save(image, "06_corr_threshold_sensitivity.png")


def participation_innovations():
    frame = pd.read_csv(RESULTS / "participation_gap_innovation_metrics.csv").sort_values("oos_pearson_ic", ascending=False).head(10)
    labels = [name.replace("_", "\n")[:22] for name in frame["candidate"]]
    image, draw = canvas("成交笔数创新候选对照", "新增 NUMBER 字段创新池；最终选择 I10 以兼顾经济含义、稳定性和相关性约束")
    draw_bar_panel(draw, (70, 170, 885, 970), labels, frame["oos_pearson_ic"], "样本外 Pearson IC", "{:.3f}", COLORS[0])
    draw_bar_panel(draw, (930, 170, 1740, 970), labels, frame["oos_annual_excess"] * 100, "样本外年化超额收益（%）", "{:.1f}", COLORS[2])
    return save(image, "07_number_innovation_comparison.png")


def stability():
    frame = pd.read_csv(DELIVERABLES / "final_factor_metrics.csv")
    labels = [f"F{i:02d}" for i in frame["rank"]]
    image, draw = canvas("最终因子稳定性：样本内与样本外 Pearson IC", "方向只使用 2020-2021 样本内信息确定；2022-2023 作为留出区间报告")
    left, top, right, bottom = 110, 190, 1690, 925
    vals = np.concatenate([frame["is_pearson_ic"].to_numpy(), frame["oos_pearson_ic"].to_numpy()])
    lo, hi = 0.0, float(vals.max()) * 1.20
    zero_y = scaled_y(0, lo, hi, top + 40, bottom - 120)
    step = (right - left - 90) / len(labels)
    for tick in np.linspace(lo, hi, 6):
        y = scaled_y(tick, lo, hi, top + 40, bottom - 120)
        draw.line((left + 70, y, right, y), fill=GRID, width=1)
        text(draw, (left + 55, y), f"{tick:.3f}", 17, fill="#71808D", anchor="rm")
    for index, label in enumerate(labels):
        x = left + 90 + step * (index + 0.5)
        for offset, value, color in [(-18, frame.iloc[index]["is_pearson_ic"], COLORS[0]), (18, frame.iloc[index]["oos_pearson_ic"], COLORS[1])]:
            y = scaled_y(value, lo, hi, top + 40, bottom - 120)
            draw.rounded_rectangle((x + offset - 15, y, x + offset + 15, zero_y), radius=4, fill=color)
        text(draw, (x, bottom - 90), label, 19, anchor="ma")
    draw.rounded_rectangle((660, 940, 688, 960), radius=3, fill=COLORS[0])
    text(draw, (700, 936), "样本内 2020-2021", 19)
    draw.rounded_rectangle((930, 940, 958, 960), radius=3, fill=COLORS[1])
    text(draw, (970, 936), "样本外 2022-2023", 19)
    return save(image, "08_is_oos_stability.png")


def main():
    paths = [
        final_overview(),
        corr_heatmap(),
        same_cross_style(),
        weighting_methods(),
        greedy_rankings(),
        threshold_sensitivity(),
        participation_innovations(),
        stability(),
    ]
    (OUT / "chart_manifest.json").write_text(json.dumps(paths, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

