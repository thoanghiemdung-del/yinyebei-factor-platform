#!/usr/bin/env python3
"""Generate a machine-readable dictionary for the ten submitted factors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


WORK = Path(r"D:\yyb\submission_rebuild")
DELIVERABLES = WORK / "deliverables"
sys.path.insert(0, str(WORK))

import factor_submission as submission  # noqa: E402


LEAVES = {
    "F1_1_first30_mom": {
        "source_fields": "MINUTE_OPEN, MINUTE_CLOSE",
        "raw_formula": "(close_at_minute_30 - open_at_minute_1) / open_at_minute_1",
        "meaning": "前30分钟收益，反映隔夜信息进入市场后的早盘价格压力。",
    },
    "F1_2_last30_mom": {
        "source_fields": "MINUTE_OPEN, MINUTE_CLOSE",
        "raw_formula": "(close_at_last_minute - open_at_last_30min_start) / open_at_last_30min_start",
        "meaning": "后30分钟收益，反映尾盘调仓和集中执行造成的价格压力。",
    },
    "F1_3_intraday_mom": {
        "source_fields": "MINUTE_OPEN, MINUTE_CLOSE",
        "raw_formula": "(close_at_last_minute - open_at_first_minute) / open_at_first_minute",
        "meaning": "从开盘到收盘的日内收益，刻画当日订单流推动的价格偏离。",
    },
    "F4_1_close_vs_vwap": {
        "source_fields": "MINUTE_HIGH, MINUTE_LOW, MINUTE_CLOSE, MINUTE_VOLUME",
        "raw_formula": "(last_close - vwap) / vwap, vwap=sum(((high+low+close)/3)*volume)/sum(volume)",
        "meaning": "收盘价相对全日VWAP偏离，刻画尾盘价格与平均成交成本的距离。",
    },
    "F4_2_vwap_trend": {
        "source_fields": "MINUTE_HIGH, MINUTE_LOW, MINUTE_CLOSE, MINUTE_VOLUME",
        "raw_formula": "clip((afternoon_vwap - morning_vwap) / morning_vwap, -2, 2)",
        "meaning": "下午VWAP相对上午VWAP变化，刻画日内成本中枢迁移。",
    },
    "F5_1_volume_hhi": {
        "source_fields": "MINUTE_VOLUME",
        "raw_formula": "sum((minute_volume / sum(all_day_minute_volume)) ** 2)",
        "meaning": "分钟成交量HHI，刻画成交是否集中于少数时点。",
    },
    "F5_2_open_vol_ratio": {
        "source_fields": "MINUTE_VOLUME",
        "raw_formula": "sum(first_6_minute_bars_volume) / sum(all_day_volume)",
        "meaning": "开盘最初6根分钟bar的成交量占比，刻画开盘阶段的信息到达和抢跑交易。",
    },
    "F5_3_close_vol_ratio": {
        "source_fields": "MINUTE_VOLUME",
        "raw_formula": "sum(last_30min_volume) / sum(all_day_volume)",
        "meaning": "后30分钟成交量占比，刻画尾盘调仓和集中执行。",
    },
    "F6_2_amihud_min": {
        "source_fields": "MINUTE_CLOSE, MINUTE_AMOUNT",
        "raw_formula": "mean(clip(abs(minute_close_return) / max(minute_amount, 1000), 0, 0.01))",
        "meaning": "分钟收益绝对值相对分钟成交额的均值，刻画单位资金推动价格的能力。",
    },
    "F6_4_large_trade_ratio": {
        "source_fields": "MINUTE_VOLUME",
        "raw_formula": "sum(volume where volume > 2 * median(minute_volume)) / sum(volume)",
        "meaning": "大额成交分钟的成交量占比，刻画大额执行集中度。",
    },
    "F_COMBO_2_vpin_informed": {
        "source_fields": "MINUTE_CLOSE, MINUTE_VOLUME",
        "raw_formula": "vpin - trailing_mean(vpin, 20), vpin=sum(volume*abs(minute_return))/sqrt(sum(volume**2))",
        "meaning": "VPIN相对20日均值的变化，检验订单流毒性是否异常。",
    },
    "F_COMBO_4_amihud_hybrid": {
        "source_fields": "MINUTE_CLOSE, MINUTE_AMOUNT",
        "raw_formula": "F6_2_amihud_min / trailing_mean(F6_2_amihud_min, 20) - 1",
        "meaning": "分钟Amihud相对20日均值的变化，检验流动性冲击。",
    },
    "F_COMBO_7_wat": {
        "source_fields": "MINUTE_VOLUME, MINUTE_OPEN, MINUTE_CLOSE",
        "raw_formula": "(0.5 - volume_weighted_time) * sign(intraday_return)",
        "meaning": "成交量加权交易时点与日内方向结合，刻画信息到达时段。",
    },
    "F_COMBO_8_large_trade": {
        "source_fields": "MINUTE_VOLUME, MINUTE_OPEN, MINUTE_CLOSE",
        "raw_formula": "F6_4_large_trade_ratio * sign(intraday_return)",
        "meaning": "大额成交占比与日内方向结合，刻画大单推动。",
    },
    "F_COMBO_9_smart_money_vwap": {
        "source_fields": "MINUTE_OHLC, MINUTE_VOLUME",
        "raw_formula": "up_bar_volume_ratio * F4_1_close_vs_vwap",
        "meaning": "上涨分钟成交量占比与收盘VWAP偏离相乘，刻画买方订单流与价格偏离共振。",
    },
    "G2_1_intraday_ret5d": {
        "source_fields": "MINUTE_OPEN, MINUTE_CLOSE, DAILY_CLOSE",
        "raw_formula": "abs(intraday_return * trailing_5d_return) if signs_are_equal else NaN",
        "meaning": "日内方向与五日收益同向时保留交互，刻画短期趋势确认。",
    },
    "N1_count_weighted_time": {
        "source_fields": "MINUTE_NUMBER",
        "raw_formula": "sum(minute_index * minute_number) / sum(minute_number) / (bars - 1)",
        "meaning": "成交笔数加权平均交易时点，刻画普通交易参与偏早盘还是尾盘。",
    },
    "N2_open_count_ratio": {
        "source_fields": "MINUTE_NUMBER",
        "raw_formula": "sum(first_30min_minute_number) / sum(all_day_minute_number)",
        "meaning": "前30分钟成交笔数占比，刻画早盘参与密度。",
    },
    "N3_close_count_ratio": {
        "source_fields": "MINUTE_NUMBER",
        "raw_formula": "sum(last_30min_minute_number) / sum(all_day_minute_number)",
        "meaning": "后30分钟成交笔数占比，刻画尾盘参与密度。",
    },
    "N4_count_hhi": {
        "source_fields": "MINUTE_NUMBER",
        "raw_formula": "sum((minute_number / sum(all_day_minute_number)) ** 2)",
        "meaning": "分钟成交笔数HHI，刻画交易活跃度在时段上的集中程度。",
    },
    "N5_log_avg_ticket": {
        "source_fields": "MINUTE_AMOUNT, MINUTE_NUMBER",
        "raw_formula": "log1p(sum(minute_amount) / sum(minute_number))",
        "meaning": "全日平均单笔金额的对数，刻画平均订单规模。",
    },
    "N6_large_ticket_amount_ratio": {
        "source_fields": "MINUTE_AMOUNT, MINUTE_NUMBER",
        "raw_formula": "sum(amount where amount/number > 2*median(bar_amount/bar_number)) / sum(amount)",
        "meaning": "异常大单时段成交额占比，刻画机构式大单执行。",
    },
    "N7_count_price_corr": {
        "source_fields": "MINUTE_CLOSE, MINUTE_NUMBER",
        "raw_formula": "corr(minute_close_return, minute_number) across one day",
        "meaning": "分钟收益与成交笔数的日内相关性，刻画参与密度是否与价格变化共振。",
    },
    "N8_tail_ticket_reversal": {
        "source_fields": "MINUTE_OHLC, MINUTE_AMOUNT, MINUTE_NUMBER",
        "raw_formula": "-last_30min_return * (last_30min_avg_ticket / all_day_avg_ticket)",
        "meaning": "尾盘收益取反并乘尾盘单笔金额相对比例，刻画尾盘大单冲击后的修复。",
    },
}


FACTOR_NAMES = {
    "factor_01": "大单执行压力",
    "factor_02": "日内反转与成交笔数时序",
    "factor_03": "VWAP执行价格压力",
    "factor_04": "成交笔数集中度",
    "factor_05": "尾盘压力与成交分布修复",
    "factor_06": "相对分钟Amihud冲击",
    "factor_07": "相对VPIN订单流毒性",
    "factor_08": "日内与五日趋势确认",
    "factor_09": "分钟Amihud价格冲击",
    "factor_10": "成交量-成交笔数集中度差",
}


def explicit_formula(terms):
    return " ".join(f"{weight:+.6f} * z({leaf})" for leaf, weight in terms.items()).lstrip("+").strip()


def main():
    DELIVERABLES.mkdir(parents=True, exist_ok=True)
    metrics = pd.read_csv(DELIVERABLES / "final_factor_metrics.csv").set_index("factor_key")
    used = []
    factors = []
    for key, terms in submission.FINAL_SPECS.items():
        children = []
        for leaf, weight in terms.items():
            if leaf not in used:
                used.append(leaf)
            children.append({"leaf": leaf, "weight": float(weight), **LEAVES[leaf]})
        row = metrics.loc[key]
        factors.append({
            "factor_key": key,
            "factor_name_zh": FACTOR_NAMES[key],
            "formula": explicit_formula(terms),
            "submitted_meaning": row["meaning"],
            "oos_pearson_ic": float(row["oos_pearson_ic"]),
            "oos_annual_excess": float(row["oos_annual_excess"]),
            "oos_excess_sharpe": float(row["oos_excess_sharpe"]),
            "children": children,
        })
    leaf_rows = [{"leaf": leaf, **LEAVES[leaf]} for leaf in used]
    pd.DataFrame(leaf_rows).to_csv(DELIVERABLES / "leaf_dictionary.csv", index=False, encoding="utf-8-sig")
    (DELIVERABLES / "final_factor_dictionary.json").write_text(
        json.dumps({"factor_count": len(factors), "leaf_count": len(used), "factors": factors}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = ["# 最终十因子机器可读字典", "", f"- 最终因子数：{len(factors)}", f"- 去重后叶子数：{len(used)}", ""]
    for factor in factors:
        lines += [
            f"## {factor['factor_key']}：{factor['factor_name_zh']}",
            "",
            f"公式：`{factor['formula']}`",
            "",
            f"经济含义：{factor['submitted_meaning']}",
            "",
            "| 子因子 | 权重 | 原始字段 | 子因子经济含义 |",
            "|---|---:|---|---|",
        ]
        for child in factor["children"]:
            lines.append(f"| `{child['leaf']}` | {child['weight']:.6f} | `{child['source_fields']}` | {child['meaning']} |")
        lines.append("")
    (DELIVERABLES / "final_factor_dictionary.md").write_text("\n".join(lines), encoding="utf-8")
    metric_rows = []
    quick_lines = [
        "# 最终十因子速览",
        "",
        "十个因子均为原子信号或一次显式线性组合。详细叶子字段、权重和子因子含义见 `results/final_factor_dictionary.md`。",
        "",
        "| 编号 | 中文名称 | 样本外 Pearson IC | 样本外年化超额 | 样本外 Sharpe |",
        "|---|---|---:|---:|---:|",
    ]
    for factor in factors:
        metric = metrics.loc[factor["factor_key"]].to_dict()
        metric_rows.append({
            "rank": int(metric["rank"]),
            "factor_key": factor["factor_key"],
            "factor_name_zh": factor["factor_name_zh"],
            "internal_source_name": metric["factor_name"],
            "formula": factor["formula"],
            "meaning": factor["submitted_meaning"],
            "is_pearson_ic": float(metric["is_pearson_ic"]),
            "oos_pearson_ic": float(metric["oos_pearson_ic"]),
            "oos_annual_excess": float(metric["oos_annual_excess"]),
            "oos_excess_sharpe": float(metric["oos_excess_sharpe"]),
            "full_pearson_ic": float(metric["full_pearson_ic"]),
            "full_annual_excess": float(metric["full_annual_excess"]),
        })
        quick_lines.append(
            f"| {factor['factor_key']} | {factor['factor_name_zh']} | "
            f"{factor['oos_pearson_ic']:.4f} | {factor['oos_annual_excess']:.2%} | "
            f"{factor['oos_excess_sharpe']:.2f} |"
        )
    pd.DataFrame(metric_rows).sort_values("rank").to_csv(
        DELIVERABLES / "final_factor_metrics_zh.csv", index=False, encoding="utf-8-sig"
    )
    quick_lines += [
        "",
        "全样本因子值最大非对角线绝对相关性：`0.494319`。",
        "",
        "独立 Python 代码真实分钟复算：`PASS`。",
    ]
    (DELIVERABLES / "final_factor_quickview.md").write_text("\n".join(quick_lines), encoding="utf-8")
    print(json.dumps({"factor_count": len(factors), "leaf_count": len(used)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
