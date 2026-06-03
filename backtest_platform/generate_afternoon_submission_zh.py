#!/usr/bin/env python3
"""Generate the Chinese afternoon paper without mutating the frozen English bundle."""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BASE = Path(__file__).resolve().parent
DB = BASE / "backtest.db"
PAPER = Path(r"D:\yyb\paper")
FIG = PAPER / "afternoon_figures_zh"
MANIFEST = PAPER / "afternoon_final_factors.json"
PHASE_AUDIT = PAPER / "afternoon_phase_audit.json"
REGIME_AUDIT = PAPER / "afternoon_regime_audit.json"
TEX = PAPER / "afternoon_final_submission_zh.tex"
PDF = PAPER / "afternoon_final_submission_zh.pdf"
DETAIL_JSON = PAPER / "afternoon_final_factor_economics_zh.json"
DETAIL_MD = PAPER / "afternoon_final_factor_economics_zh.md"
DETAIL_TSV = PAPER / "afternoon_final_factors_zh.tsv"

COLORS = {
    "blue": "#2459A9",
    "orange": "#E07A2F",
    "green": "#2A8F5B",
    "red": "#C4423B",
    "purple": "#7952A8",
    "gray": "#667085",
    "dark": "#182230",
}

CHILD_FACTORS = {
    "ret_20d": "过去 20 个交易日收益率。它刻画中期价格延续状态，也可用于区分信息缓慢扩散与短期过度反应。",
    "ret_120d_skip5": "剔除最近 5 个交易日后的 120 日收益率。它保留较持久的趋势信息，同时降低最近一周反转噪声的干扰。",
    "rev_5d": "过去 5 个交易日的短期反转代理。它用于捕捉流动性冲击、追涨杀跌或临时订单失衡后的修复。",
    "turnover_rate": "换手率强度。它既反映交易需求和信息到达速度，也反映拥挤度；在组合中通常用于抑制过热暴露。",
    "turnover_5d": "近 5 日换手率。它更贴近短期流动性需求与订单冲击，适合与反转信号结合。",
    "amihud_20d": "20 日 Amihud 非流动性指标，即单位成交金额对应的价格冲击。它用于刻画流动性风险、可交易容量和冲击成本。",
    "log_dollar_vol": "成交金额的对数尺度。它是容量、流动性和拥挤交易的重要控制量，可避免组合只押注于难以成交的股票。",
    "auction_return": "集合竞价或开收盘附近的价格变化代理。它反映集中撮合时段的订单失衡、价格发现噪声和短暂压力。",
    "abnormal_vol_rev": "异常成交量条件下的反转代理。它关注放量后价格冲击是否回吐，用于识别非信息型交易造成的临时偏离。",
    "volume_profile_ratio": "成交量在日内或近期窗口中的相对分布异常。它刻画参与者结构、交易时点和订单流形态变化。",
}

FACTOR_DETAILS = {
    1: {
        "name": "流动性约束下的中期趋势延续",
        "summary": "在中期收益延续信号上叠加换手率、Amihud 非流动性与成交金额尺度控制，优先保留有趋势但不过度拥挤、仍具可交易容量的股票。",
        "mechanism": "中期价格延续通常来自信息缓慢扩散、机构分批建仓和投资者反应不足。单独追逐趋势容易集中到高换手拥挤标的；流动性与容量子因子对其进行筛选，使收益来源更接近可执行的慢速信息吸收，而不是短暂追涨。",
        "risk": "趋势行情急转、拥挤交易同步平仓或小盘流动性骤降时，收益可能明显衰减。该因子仍包含流动性风险溢价，不应把高 Sharpe 直接解释为无风险套利。",
    },
    2: {
        "name": "异常成交量冲击后的流动性反转",
        "summary": "识别近端换手率和异常成交量所代表的临时交易压力，再结合 Amihud 与成交金额控制，寻找压力释放后的价格回归。",
        "mechanism": "被动调仓、流动性需求和非信息型大单会在短时间内推动价格偏离均衡值。若成交量异常但缺乏持续信息支持，价格冲击往往部分回吐。流动性尺度用于区分可交易的修复机会与纯粹的难交易风险。",
        "risk": "财报、重大公告或宏观冲击期间，放量可能是新信息而非噪声；此时反转假设容易失效，甚至与基本面重估方向相反。",
    },
    3: {
        "name": "竞价压力与流动性风险的组合修复",
        "summary": "把竞价收益、换手率和 Amihud 非流动性合并，捕捉集中撮合阶段订单失衡造成的短暂偏离。",
        "mechanism": "开盘或收盘竞价承接了指数调仓、被动基金和隔夜订单。集中撮合能提高价格发现效率，也会产生短时供需不平衡。该组合试图区分需要后续修复的压力与有信息含量的价格变动。",
        "risk": "竞价机制变化、指数调仓日和事件日可能抬高尾部风险；组合换手率也相对较高，必须把冲击成本纳入独立容量测试。",
    },
    4: {
        "name": "长期趋势、竞价反转与容量约束",
        "summary": "同时使用剔除近端噪声的长期趋势、竞价压力修复以及成交金额和非流动性控制，区分慢趋势与快噪声。",
        "mechanism": "较长周期趋势可代表基本面信息逐步进入价格；竞价收益则更接近局部订单冲击。两者组合的经济意图是保留慢速信息延续，同时对短时价格压力进行修正。",
        "risk": "若市场进入剧烈风格切换，长期趋势与短期反转可能同时失效；不同子信号的有效期限不同，实盘需要动态监控贡献度。",
    },
    5: {
        "name": "多周期动量与拥挤度折价",
        "summary": "合并 20 日和跳过最近一周的 120 日趋势，再用换手率与成交金额刻画拥挤度和容量。",
        "mechanism": "20 日收益更敏感，120 日跳空窗口更稳定。两个周期同时指向同一方向时，趋势更可能来自持续信息扩散；换手率折价则抑制已经被大量交易者追逐的部分。",
        "risk": "动量崩溃、宏观拐点和快速均值回归阶段是主要风险。该因子与其他趋势类组合存在经济暴露重叠，即使全窗口相关性约束已经满足。",
    },
    6: {
        "name": "跨期限订单流分解型混合因子",
        "summary": "将中长期趋势、5 日反转、异常成交量反转、成交量形态、Amihud 与成交金额放在同一套组合中，区分持久信息与暂时订单流。",
        "mechanism": "价格变化可粗略拆成持久成分和临时成分：趋势代理偏向前者，短反转和异常成交量代理偏向后者，成交量形态与流动性指标则判断冲击是否可交易。该因子是 10 个因子中经济来源最分散的一项。",
        "risk": "结构较复杂，解释依赖子因子代理而非严格的结构模型。若各子信号在新样本中同时衰减，复杂组合会放大估计误差。",
    },
    7: {
        "name": "低拥挤中期动量桥接因子",
        "summary": "在缓存组合上显式加入 zscore(ret_20d) - zscore(turnover_rate)，偏好 20 日收益较强但换手率不过热的股票。",
        "mechanism": "中期收益延续与低拥挤筛选的组合，意在寻找仍处于信息扩散阶段、尚未被高频交易需求完全挤满的趋势。显式减去换手率使经济含义比纯黑箱组合更清楚。",
        "risk": "换手率并不总是拥挤度：在基本面信息释放时，高换手也可能是合理的价格发现。过度惩罚换手率会漏掉真实信息趋势。",
    },
    8: {
        "name": "日内成交形态与竞价冲击修复",
        "summary": "结合异常成交量反转、竞价收益、日内成交量形态、近端换手率与 Amihud，寻找多维订单流确认后的短期修复。",
        "mechanism": "单一放量信号容易混淆信息交易和流动性交易。加入竞价与日内成交结构后，组合可以更细致地识别集中交易造成的临时价格冲击，理论上降低误判。",
        "risk": "因子依赖微观结构稳定性。交易制度、竞价参与者或日内执行方式变化后，历史模式可能迁移；实盘交易成本也会比低换手因子更重要。",
    },
    9: {
        "name": "竞价与换手一致性筛选反转",
        "summary": "显式项为 -rank(abs(zscore(turnover_rate) - zscore(auction_return)))：它惩罚换手率与竞价收益之间的极端差异，在基础反转组合上加入稳定性筛选。",
        "mechanism": "若竞价价格变化极端但缺乏相称的交易参与，或换手异常但竞价价格并未确认，信号可能更不稳定。负的绝对差异排名项会压低这类失配暴露，保留较一致的订单流状态。",
        "risk": "这里的显式项更准确地说是稳定性过滤器，而不是独立套利机制。该因子换手率最高，且可能在真正的信息跳跃场景中过度回避有效信号。",
    },
    10: {
        "name": "基础组合增强的低拥挤中期动量",
        "summary": "与第 7 项同样显式使用 zscore(ret_20d) - zscore(turnover_rate)，但连接到不同的缓存基础组合，因此保留了另一条收益来源路径。",
        "mechanism": "20 日收益代理慢速趋势，换手率惩罚代理拥挤折价。不同基础组合使其与第 7 项在经济概念相近的情况下仍保留较低的实测 PnL 相关性。",
        "risk": "该因子与第 7 项共享核心桥接项，不能仅凭全窗口相关性较低就视为完全独立。需要在未触碰留出集和实盘仿真中继续检查条件相关性。",
    },
}

PHASE_NAMES = {
    "backup_cross_style_pair": "扩展跨风格两两组合",
    "backup_cross_style_triple": "扩展跨风格三元组合",
    "backup_meta_nesting": "扩展元套娃",
    "cross_style_bridge": "跨风格桥接",
    "cross_style_offset": "跨风格偏移",
    "deep_meta_nesting": "深层元套娃",
    "deep_pair_triple_nesting": "深层两两及三元套娃",
    "nested_style_anchor": "嵌套风格锚",
    "residualized_near_threshold": "阈值附近残差化",
    "style_anchor": "风格锚",
    "weighted_cross_style": "加权跨风格组合",
}


def tex(value: object) -> str:
    out = str(value)
    for old, new in (
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
    ):
        out = out.replace(old, new)
    return out


def fmt(value: object, digits: int = 3) -> str:
    try:
        number = float(value)
        return f"{number:.{digits}f}" if math.isfinite(number) else "n/a"
    except Exception:
        return "n/a"


def font(size: int = 28, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"
    return ImageFont.truetype(path, size)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pnls(factors: list[dict]) -> dict[str, list[float]]:
    connection = sqlite3.connect(DB)
    out = {}
    for factor in factors:
        row = connection.execute("SELECT pnl_json FROM alpha_history WHERE id=?", (factor["id"],)).fetchone()
        raw = json.loads(row[0]) if row and row[0] else []
        if isinstance(raw, dict):
            raw = raw.get("pnl_series") or raw.get("_pnl_series") or raw.get("oos_pnl") or []
        if len(raw) < 30:
            raise RuntimeError(f"PnL series unavailable for {factor['id']}")
        out[factor["id"]] = [float(value) for value in raw]
    connection.close()
    return out


def canvas(title: str, width: int = 1800, height: int = 1050):
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 38), title, fill=COLORS["dark"], font=font(38, True))
    return image, draw


def save(image: Image.Image, name: str) -> Path:
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / name
    image.save(path, quality=96)
    return path


def chart_sharpe(factors: list[dict]) -> None:
    image, draw = canvas("最终严格组合：实测样本外 Sharpe")
    x0, x1, y0 = 540, 1700, 130
    high = max(float(row["sharpe"]) for row in factors) * 1.08
    for i, row in enumerate(factors):
        y = y0 + 78 * i
        value = float(row["sharpe"])
        draw.rectangle((x0, y, x0 + int((x1 - x0) * value / high), y + 42), fill=COLORS["green"])
        draw.text((70, y + 7), f"{i + 1}. {row['id'][:12]}", fill=COLORS["dark"], font=font(25))
        draw.text((x0 + int((x1 - x0) * value / high) + 10, y + 7), fmt(value), fill=COLORS["dark"], font=font(25, True))
    save(image, "strict_sharpe_zh.png")


def chart_corr(factors: list[dict], matrix: list[list[float]]) -> None:
    image, draw = canvas("最终严格组合：日度 PnL 绝对相关系数")
    n, size, left, top = len(factors), 68, 490, 170
    for i in range(n):
        for j in range(n):
            value = float(matrix[i][j])
            color = (int(240 - 150 * value), int(248 - 80 * value), int(255 - 25 * value))
            draw.rectangle((left + j * size, top + i * size, left + (j + 1) * size, top + (i + 1) * size), fill=color, outline="white")
            draw.text((left + j * size + 12, top + i * size + 23), f"{value:.2f}", fill=COLORS["dark"], font=font(17))
        draw.text((left - 42, top + i * size + 23), str(i + 1), fill=COLORS["dark"], font=font(20, True))
        draw.text((left + i * size + 25, top - 34), str(i + 1), fill=COLORS["dark"], font=font(20, True))
    save(image, "strict_corr_heatmap_zh.png")


def chart_curves(factors: list[dict], pnls: dict[str, list[float]]) -> None:
    image, draw = canvas("最终严格组合：累计样本外 PnL")
    x0, y0, x1, y1 = 170, 135, 1690, 930
    curves = [pnls[row["id"]] for row in factors]
    low = min(min(curve) for curve in curves)
    high = max(max(curve) for curve in curves)
    span = max(high - low, 1e-6)
    draw.line((x0, y1, x1, y1), fill=COLORS["dark"], width=3)
    draw.line((x0, y0, x0, y1), fill=COLORS["dark"], width=3)
    palette = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["red"], COLORS["purple"], "#00A6A6", "#A66F00", "#8A4FFF", "#4D7C0F", "#9B1C31"]
    for index, curve in enumerate(curves):
        points = []
        for i, value in enumerate(curve):
            x = x0 + int((x1 - x0) * i / max(len(curve) - 1, 1))
            y = y1 - int((y1 - y0) * (value - low) / span)
            points.append((x, y))
        draw.line(points, fill=palette[index], width=3)
        draw.text((x0 + 12, y0 + 26 * index), f"{index + 1}. {factors[index]['id'][:8]}", fill=palette[index], font=font(19, True))
    save(image, "strict_curves_zh.png")


def chart_phases(phase_audit: dict) -> None:
    items = sorted(phase_audit["phases"], key=lambda row: float(row["maximum_sharpe"]), reverse=True)[:10]
    image, draw = canvas("创新实验阶段：最高实测样本外 Sharpe")
    x0, x1, y0 = 700, 1700, 135
    high = max(float(row["maximum_sharpe"]) for row in items) * 1.08
    for i, row in enumerate(items):
        y = y0 + 78 * i
        value = float(row["maximum_sharpe"])
        draw.rectangle((x0, y, x0 + int((x1 - x0) * value / high), y + 42), fill=COLORS["purple"])
        label = f"{PHASE_NAMES.get(row['phase'], row['phase'])} (n={row['rows']})"
        draw.text((70, y + 7), label, fill=COLORS["dark"], font=font(22))
        draw.text((x0 + int((x1 - x0) * value / high) + 10, y + 7), fmt(value), fill=COLORS["dark"], font=font(23, True))
    save(image, "innovation_phases_zh.png")


def build_details(manifest: dict) -> list[dict]:
    out = []
    for factor in manifest["factors"]:
        detail = FACTOR_DETAILS[int(factor["rank"])]
        out.append({
            **factor,
            "name_zh": detail["name"],
            "summary_zh": detail["summary"],
            "mechanism_zh": detail["mechanism"],
            "risk_zh": detail["risk"],
            "child_factors_zh": {key: CHILD_FACTORS[key] for key in factor["child_factors"]},
        })
    return out


def write_detail_files(details: list[dict]) -> None:
    DETAIL_JSON.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# YYB 最终 10 因子的经济含义说明",
        "",
        "> 口径说明：以下解释依据冻结表达式、递归引用谱系与可识别叶子代理给出，是机制层面的经济解释，不是因果识别结论。缓存子组合未逐项完全反编译的部分不会被伪装成确定事实。",
        "",
    ]
    for row in details:
        lines += [
            f"## {row['rank']}. {row['name_zh']}",
            "",
            f"- Alpha ID：`{row['id']}`",
            f"- 实测指标：Sharpe `{row['sharpe']:.3f}`，IC `{row['ic']:.4f}`，Turnover `{row['turnover']:.4f}`，入选时最大相关性 `{row['max_corr_to_selected']:.4f}`",
            f"- 表达式：`{row['expression']}`",
            f"- 核心含义：{row['summary_zh']}",
            f"- 经济机制：{row['mechanism_zh']}",
            f"- 主要风险：{row['risk_zh']}",
            "- 可识别子因子：",
        ]
        lines += [f"  - `{name}`：{meaning}" for name, meaning in row["child_factors_zh"].items()]
        lines.append("")
    lines += [
        "## 子因子总字典",
        "",
    ]
    lines += [f"- `{name}`：{meaning}" for name, meaning in CHILD_FACTORS.items()]
    DETAIL_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with DETAIL_TSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["rank", "id", "name_zh", "sharpe", "ic", "fitness", "turnover", "max_corr_to_selected", "summary_zh", "mechanism_zh", "risk_zh", "child_factors"])
        for row in details:
            writer.writerow([
                row["rank"], row["id"], row["name_zh"], row["sharpe"], row["ic"], row["fitness"], row["turnover"],
                row["max_corr_to_selected"], row["summary_zh"], row["mechanism_zh"], row["risk_zh"],
                ", ".join(row["child_factors_zh"]),
            ])


def make_tex(manifest: dict, details: list[dict], phase_audit: dict, regime_audit: dict) -> str:
    factor_rows = "\n".join(
        f"{row['rank']} & {tex(row['id'][:12])} & {tex(row['name_zh'])} & {fmt(row['sharpe'])} & {fmt(row['ic'], 4)} & {fmt(row['turnover'], 4)} & {fmt(row['max_corr_to_selected'], 4)} \\\\"
        for row in details
    )
    phase_rows = "\n".join(
        f"{tex(PHASE_NAMES.get(row['phase'], row['phase']))} & {row['rows']} & {row['sharpe_gt_8_rows']} & {fmt(row['median_sharpe'])} & {fmt(row['p90_sharpe'])} & {fmt(row['maximum_sharpe'])} \\\\"
        for row in phase_audit["phases"]
    )
    neutral_rows = "\n".join(
        f"{tex(row['neutralize'])} & {row['rows']} & {fmt(row['median_sharpe'])} & {fmt(row['p90_sharpe'])} & {fmt(row['maximum_sharpe'])} \\\\"
        for row in phase_audit["neutralizations"]
    )
    regime_rows = "\n".join(
        f"{tex(row['segment'])} & {row['n_days']} & {fmt(row['equal_weight_portfolio_sharpe'])} & {fmt(row['equal_weight_cumulative_pnl'])} & {fmt(row['equal_weight_positive_day_ratio'], 4)} & {fmt(row['maximum_pairwise_abs_daily_pnl_corr'], 4)} \\\\"
        for row in regime_audit["segments"]
    )
    detail_blocks = []
    for row in details:
        children = "；".join(f"\\texttt{{{tex(name)}}}：{tex(CHILD_FACTORS[name])}" for name in row["child_factors_zh"])
        detail_blocks.append(
            rf"""
\subsection{{因子 {row['rank']}：{tex(row['name_zh'])}}}
\textbf{{Alpha ID：}}\texttt{{{tex(row['id'])}}}

\textbf{{表达式：}}\begin{{sloppypar}}\scriptsize\path|{row['expression']}|\end{{sloppypar}}

\textbf{{实测指标：}}Sharpe={fmt(row['sharpe'])}，IC={fmt(row['ic'], 4)}，Fitness={fmt(row['fitness'])}，Turnover={fmt(row['turnover'], 4)}，入选时最大绝对相关系数={fmt(row['max_corr_to_selected'], 4)}。

\textbf{{核心含义：}}{tex(row['summary_zh'])}

\textbf{{经济机制：}}{tex(row['mechanism_zh'])}

\textbf{{可识别子因子：}}{children}

\textbf{{主要风险：}}{tex(row['risk_zh'])}
"""
        )
    dictionary_rows = "\n".join(f"\\texttt{{{tex(name)}}} & {tex(meaning)} \\\\" for name, meaning in CHILD_FACTORS.items())
    return rf"""
\documentclass[10pt,a4paper]{{article}}
\usepackage[UTF8,fontset=windows]{{ctex}}
\usepackage[a4paper,margin=1.75cm]{{geometry}}
\usepackage{{booktabs,longtable,array,graphicx,float,hyperref,url,xcolor}}
\usepackage{{microtype}}
\hypersetup{{colorlinks=true,linkcolor=blue,urlcolor=blue}}
\setlength{{\parindent}}{{2em}}
\setlength{{\parskip}}{{0.35em}}
\renewcommand{{\arraystretch}}{{1.22}}
\title{{YYB A 股因子比赛研究报告\\
\large 从数据平台、因子挖掘、递归套娃到低相关严格组合}}
\author{{YYB Quant Research}}
\date{{2026 年 6 月 2 日}}

\begin{{document}}
\maketitle

\begin{{abstract}}
本文完整记录 YYB A 股因子比赛项目从数据接入、回测平台建设、原子因子研究、组合对照、递归套娃、内存治理到最终审计冻结的全过程。平台使用本地 A 股面板，训练区间为 2020--2022 年，研究阶段样本外观测区间为 2023 年；标签为未来 5 日收益。早期工作建立了 Flask、SQLite 与 NumPy 回测链路，并完成等权、ICIR、Ridge 等组合方式的对照。后续工作修复了市值中性化、组合矩阵缓存写入、缓存读取越界、内联套娃和非浮点字段保护等关键问题，使“组合因子继续作为子因子参与组合”成为可运行的递归机制。

在此基础上，本文围绕贪心选择、中性化、跨风格组合与递归套娃新增 950 条成功实验记录。最终冻结 10 个因子；每个因子的实测样本外 Sharpe 均大于 8，任意两因子的全窗口日度 PnL 绝对 Pearson 相关系数均小于 0.5，最大值为 {fmt(manifest['maximum_pairwise_corr'], 4)}。本文逐项给出最终因子的经济含义、可识别子因子含义、潜在机制与主要失效风险。需要强调：2023 年样本外窗口已被自适应检查，因此本文是内部研究交付稿，而不是对未知未来收益的外部保证；后续必须在预注册、未触碰留出集上验证。
\end{{abstract}}

\section{{比赛任务与研究目标}}
\subsection{{问题定义}}
本项目面向 A 股横截面选股比赛。目标并不是挑出一个看起来最漂亮的单因子，而是建立一套可复现的研究系统，在统一数据和回测口径下持续发现、组合并审计 Alpha。最终交付要求进一步收紧为：给出至少 10 个高 Sharpe 且相互低相关的最终因子，并说明每个因子及其子因子的明确经济含义。

研究对象是每日横截面预测信号。给定交易日 $t$ 的可观测数据，系统生成股票级分数并预测未来 5 日收益。训练区间用于原子因子排序和组合构造；2023 年区间用于研究阶段样本外测量。为了避免只追逐一个同质化方向，最终组合必须同时满足收益质量与多样性约束。

\subsection{{最终硬约束}}
最终入选规则为：
\begin{{enumerate}}
  \item 单因子实测样本外 Sharpe $>8$；
  \item 任意两项日度 PnL 的绝对 Pearson 相关系数 $<0.5$；
  \item 所有数值必须来自真实回测记录，不允许补写或外推；
  \item 禁止提交外部 Alpha，最终组合只作为内部冻结候选。
\end{{enumerate}}
实验使用的 2023 样本外区间已经被多轮自适应查看。因而，Sharpe、IC、相关矩阵和分段表现属于描述性证据，不等同于完全未触碰的验证集结果，更不能直接视为可复制的实盘收益承诺。

\section{{数据与回测平台}}
\subsection{{本地数据口径}}
平台使用本地 A 股面板数据。交接快照记录了 970 个交易日、5,515 只股票和 89 个字段；标签为未来 5 日收益。主研究划分为 2020--2022 年训练区间与 2023 年研究阶段样本外区间。最终组合的累计 PnL 序列包含 242 个累计值，对应 241 个日度变化。

字段既包含价格和收益，也包含换手率、成交金额、成交量形态、竞价收益和流动性代理。分钟级原始文件保留在 D 盘，但最终 10 个因子的解释只使用已经进入冻结谱系、能够确认的代理字段。论文不会把未被最终表达式使用的原始字段写成收益来源。

\subsection{{平台架构}}
平台核心由 Flask 服务、SQLite 历史库、NumPy 矩阵计算和网页审查界面组成。单因子和组合因子统一写入 \texttt{{alpha\_history}}；组合计算结果不仅保存指标，也缓存股票日度矩阵。网页用于浏览、筛选、贪心去重和远程审查。最终论文生成器只读冻结清单和数据库，不会触发外部 Alpha 提交。

\begin{{center}}
\small
\texttt{{原始面板数据 -> 原子因子矩阵 -> 横截面标准化 -> 组合与中性化 -> PnL 评估 -> SQLite 历史库 -> 缓存矩阵 -> 递归套娃 -> 严格贪心冻结}}
\end{{center}}

\subsection{{递归套娃机制}}
本项目最重要的工程创新是把组合因子重新视为可复用的普通因子矩阵。每次组合回测完成后，平台写入历史记录并保存约 $242 \times 5515$ 的 \texttt{{float32}} 缓存矩阵。后续表达式遇到 \texttt{{superalpha\_ref(...)}} 时，内联计算路径直接加载缓存，完成标准化、加权、中性化与重新评估。该链路允许两两组合、三元组合和元套娃逐层展开，而不必为每个组合重复启动昂贵的数据管线。

\begin{{center}}
\small
\texttt{{写缓存：组合计算 -> 写历史记录 -> 保存 ew\_\{{uuid\}}.npy}}\\
\texttt{{读缓存：superalpha\_ref(uuid) -> 加载缓存矩阵 -> 作为普通子因子参与新组合}}\\
\texttt{{内联计算：标准化 -> 加权求和 -> 中性化 -> 评估 -> 再次缓存}}
\end{{center}}

\subsection{{工程修复与资源治理}}
套娃机制并非一开始就可靠。项目过程中完成了以下关键修复：
\begin{{enumerate}}
  \item 修复市值中性化逻辑：由错误残差处理改为市值分组内去均值，并补充市值回归残差化对照；
  \item 修复组合缓存写入：组合完成后直接使用返回 UUID 保存矩阵，不再依赖脆弱的表达式反查；
  \item 修复缓存读取越界：缓存矩阵已是样本外切片，内联路径不再二次切片；
  \item 修复非浮点字段引发的 \texttt{{timedelta64}} 内存问题，对不可计算字段进行保护；
  \item 将套娃回测改为内联加载，减少子进程重复加载大管线造成的内存压力；
  \item 保持 Flask 单实例监听 5000 端口，通过守护与远程隧道维持审查入口。
\end{{enumerate}}
这些修复直接决定了后续 950 条受控实验能否稳定运行。由于机器内存紧张，扩展实验采用单管线、受控串行方式，避免并行加载多个数据管线。

\section{{研究路线：从原子因子到严格组合}}
\subsection{{第一阶段：原子因子与组合基线}}
早期工作先扩充原子因子库，再比较同风格和跨风格组合。基线实验覆盖等权、ICIR 加权和 Ridge 正则化，并比较按训练区间 Sharpe 与按训练区间 IC 排序的差异。阶段性结论包括：训练区间 Sharpe 排序优于单纯 IC 排序；小规模组合优于盲目扩大因子数；动量与反转的互补性较强；单独依赖流动性暴露在 2023 年表现不稳定。

这些结论并非最终答案，而是后续创新的设计依据：一方面保留趋势与反转两种经济期限，另一方面把流动性更多用作筛选、容量控制和拥挤度约束，而不是把它单独当成稳定收益来源。

\subsection{{第二阶段：组合方式对照}}
平台对多种组合方式进行对照。等权组合提供最透明的基线；ICIR 加权强调训练区间预测稳定性；Ridge 通过正则化降低共线性；自定义加权用于显式放大或压低某类风格。最终冻结集合并不依赖单一组合方法，而是来自不同组合与套娃路径的真实回测记录。

\subsection{{第三阶段：中性化对照}}
中性化维度包含不做中性化、Beta 中性化、市值中性化、市值与 Beta 联合中性化以及市值回归残差化。中性化不是机械提升器：它改变暴露来源，也可能压低有效信号，因此本文保留完整对照而不是只报告最优切片。

\subsection{{第四阶段：跨风格组合与递归套娃}}
扩展搜索把原子因子和已缓存组合放在同一个可组合空间中。跨风格桥接用于连接趋势、反转、竞价、异常成交量和流动性约束；风格锚用于保留相对清晰的单一机制；两两与三元套娃用于测试互补路径；元套娃则进一步组合已经经过筛选的高质量组合。套娃提高了表达能力，但也带来过拟合、谱系复杂度和状态相关性抬升的风险，因此必须配合严格审计。

\section{{受控扩展实验}}
\subsection{{创新空间}}
实验覆盖 11 个阶段，包含跨风格桥接、风格偏移、阈值附近残差化、加权组合、两两及三元递归套娃、元套娃和扩展搜索。组合的核心思路是把中期趋势、短期反转、竞价压力、异常成交量、流动性风险和容量控制放入可审计的组合谱系中。

\subsection{{中性化对照}}
中性化维度包含不做中性化、Beta 中性化、市值中性化、市值与 Beta 联合中性化以及市值回归残差化。中性化不是机械提升器：它改变暴露来源，也可能压低有效信号，因此本文保留完整对照而不是只报告最优切片。

\begin{{table}}[H]
\centering
\small
\begin{{tabular}}{{lrrrr}}
\toprule
中性化方式 & 实验数 & Sharpe 中位数 & Sharpe P90 & Sharpe 最大值 \\
\midrule
{neutral_rows}
\bottomrule
\end{{tabular}}
\caption{{中性化方式对照。所有统计均来自已检查窗口，仅作描述性分析。}}
\end{{table}}

市值中性化的最高 Sharpe 为 16.247，高于不做中性化的 15.816；但该表各行的候选混合并不完全相同，因此不能把差异解释为严格因果效应。更准确的结论是：中性化选择值得纳入组合搜索，而不是事先固定为唯一答案。

\subsection{{组合与套娃阶段对照}}
\begin{{longtable}}{{p{{5.8cm}}rrrrr}}
\toprule
阶段 & 实验数 & Sharpe $>8$ 数 & 中位数 & P90 & 最大值 \\
\midrule
\endhead
{phase_rows}
\bottomrule
\caption{{950 条创新实验的阶段统计。}}
\end{{longtable}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.96\textwidth]{{afternoon_figures_zh/innovation_phases_zh.png}}
\caption{{主要创新阶段的最高实测样本外 Sharpe。}}
\end{{figure}}

\subsection{{贪心相关性阈值对照}}
严格组合使用逐项贪心筛选：候选按 Sharpe 降序排列，只有当它与所有已选因子的日度 PnL 绝对相关系数都低于阈值时才加入。阈值越严格，可用候选数越少；阈值越宽松，组合容量增加但同质化风险上升。

\begin{{table}}[H]
\centering
\small
\begin{{tabular}}{{rr}}
\toprule
相关性阈值 & 满足严格条件的候选数 \\
\midrule
0.35 & 8 \\
0.40 & 10 \\
0.45 & 13 \\
0.50 & 22 \\
0.55 & 23 \\
\bottomrule
\end{{tabular}}
\caption{{贪心严格池对日度 PnL 绝对相关性阈值的敏感性。}}
\end{{table}}

\section{{最终严格组合}}
冻结清单中共有 {manifest['strict_available_count']} 个候选满足严格条件，本文展示经贪心选择固定的前 10 项。最终 10 项均满足 Sharpe $>8$；全窗口最大两两绝对相关系数为 {fmt(manifest['maximum_pairwise_corr'], 4)}。

\begin{{longtable}}{{r p{{2.6cm}} p{{5.2cm}} rrrr}}
\toprule
序号 & Alpha ID 前缀 & 经济主题 & Sharpe & IC & Turnover & 最大相关 \\
\midrule
\endhead
{factor_rows}
\bottomrule
\caption{{最终 10 个严格因子。最大相关指该因子加入贪心组合时与已选因子的最大绝对相关系数。}}
\end{{longtable}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.96\textwidth]{{afternoon_figures_zh/strict_sharpe_zh.png}}
\caption{{最终 10 个因子的实测样本外 Sharpe。}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.86\textwidth]{{afternoon_figures_zh/strict_corr_heatmap_zh.png}}
\caption{{最终组合的全窗口日度 PnL 绝对相关系数矩阵。}}
\end{{figure}}

\begin{{figure}}[H]
\centering
\includegraphics[width=0.96\textwidth]{{afternoon_figures_zh/strict_curves_zh.png}}
\caption{{最终 10 个因子的累计样本外 PnL 曲线。}}
\end{{figure}}

\section{{逐因子经济含义}}
以下解释依据冻结表达式、递归引用谱系和可识别叶子代理给出。对于无法完全反编译的缓存子组合，本文只报告能够确认的叶子暴露，不把机制解释写成因果证明。

{''.join(detail_blocks)}

\section{{子因子经济含义字典}}
\begin{{longtable}}{{p{{3.8cm}}p{{12.1cm}}}}
\toprule
子因子 & 明确经济含义 \\
\midrule
\endhead
{dictionary_rows}
\bottomrule
\caption{{最终 10 个因子中可识别叶子代理的经济含义。}}
\end{{longtable}}

\section{{顺序分段审计}}
为检查样本内稳定性，本文对已经被检查过的 2023 样本外窗口进行顺序分段。该步骤能揭示条件相关性抬升和时变风险，但仍不是未触碰留出集验证。

\begin{{longtable}}{{lrrrrr}}
\toprule
区间 & 天数 & 等权组合 Sharpe & 累计 PnL & 正收益日占比 & 最大相关 \\
\midrule
\endhead
{regime_rows}
\bottomrule
\caption{{顺序分段描述性审计。季度窗口中的相关系数可能高于全窗口阈值。}}
\end{{longtable}}

全窗口最大相关性低于 0.5，但 Q4 分段最大相关系数升至 0.7409。这说明低相关约束并非跨状态恒定，实盘前必须把滚动相关性、容量和交易成本纳入持续监控。

\section{{成果边界：是否达到顶会标准}}
当前版本已经达到较强的内部研究交付标准：数据口径可追踪，工程链路可恢复，950 条扩展实验有真实记录，最终 10 因子满足硬约束，中文论文、图表、冻结清单和逐因子解释可以复现。然而，若按量化金融或机器学习顶会的严格实证标准衡量，当前结果仍不足以形成外部可接受的性能主张。核心原因不是文档长度，而是验证边界。

2023 年区间已被用于自适应选择。高 Sharpe 可能同时包含真实结构、数据挖掘和窗口偶然性。正式投稿前仍需要：未触碰留出集、滚动走样验证、交易成本与容量模型、涨跌停和 T+1 执行约束、Block Bootstrap 置信区间、Deflated Sharpe Ratio、多重检验控制，以及对经济暴露和失效状态的系统分析。本文选择把这些缺口写清楚，而不是把内部研究结果包装成已经完成的外部验证。

\section{{局限性与下一步验证}}
\begin{{enumerate}}
  \item 自适应查看会造成研究者过拟合。本文不能把已检查窗口上的高 Sharpe 当作未来收益承诺。
  \item 复杂套娃提高了组合能力，也提高了谱系审计和稳定性验证的重要性。
  \item 多项因子共享流动性、换手率和成交金额代理。即使全窗口 PnL 相关性合格，经济暴露仍可能在压力期同步上升。
  \item 下一步必须使用已经预注册的未触碰留出集，并在打开结果前冻结因子 ID、权重、交易成本、容量假设和失败判据。
\end{{enumerate}}

\section{{从头到尾的项目完成清单}}
\begin{{longtable}}{{p{{2.3cm}}p{{5.2cm}}p{{8.1cm}}}}
\toprule
阶段 & 完成事项 & 作用 \\
\midrule
\endhead
数据接入 & 整理本地 A 股面板、字段与未来 5 日标签 & 建立统一的训练与研究阶段样本外口径。 \\
回测平台 & 建立 Flask、SQLite、NumPy 与网页审查入口 & 使原子因子、组合因子、指标、PnL 和表达式可以统一管理。 \\
原子研究 & 扩充价格、收益、成交量、换手率、竞价与流动性代理 & 为动量、反转、微观结构、容量和拥挤度提供基础积木。 \\
组合基线 & 对比等权、ICIR、Ridge 与自定义加权 & 检查组合方式是否改变稳定性与收益质量。 \\
中性化 & 修复市值中性化，并比较 Beta、市值、联合与回归残差化 & 避免把简单风格暴露误写成新 Alpha。 \\
套娃工程 & 写缓存、读缓存、内联加载、递归引用 & 让组合因子能够继续作为子因子参与更高层组合。 \\
稳定性修复 & 处理缓存写入、读取越界、非浮点字段和内存压力 & 使长时间受控实验可以持续运行。 \\
扩展回测 & 新增 950 条真实记录，覆盖 11 个创新阶段 & 系统比较跨风格桥接、残差化、加权组合和多层套娃。 \\
严格冻结 & 应用 Sharpe $>8$ 与相关性 $<0.5$ 的贪心筛选 & 形成 10 个可审计、低相关的最终候选因子。 \\
风险审计 & 生成全窗口矩阵、顺序分段统计和未触碰留出集预注册 & 明确已验证内容与仍待验证内容。 \\
中文交付 & 生成中文论文、中文图表、逐因子经济解释和机器可读表格 & 形成可以审阅、复现和继续研究的最终交付。 \\
\bottomrule
\caption{{项目全过程完成清单。}}
\end{{longtable}}

\section{{可复现文件}}
中文稿由 \path{{generate_afternoon_submission_zh.py}} 生成，只读取英文冻结清单 \path{{afternoon_final_factors.json}}、回测数据库和审计 JSON，不修改英文冻结快照。逐因子解释同时写入 \path{{afternoon_final_factor_economics_zh.md}}、同名 JSON 与 \path{{afternoon_final_factors_zh.tsv}}。

\section{{结论}}
本项目从数据面板、回测平台和组合缓存机制出发，逐步完成原子因子研究、组合方式对照、中性化对照、跨风格组合、递归套娃、严格贪心冻结和风险审计。最终交付了 10 个 Sharpe 大于 8 且全窗口两两绝对相关性小于 0.5 的真实回测因子。最主要的经济来源不是单一技术指标，而是三类机制的受控组合：慢速信息扩散驱动的趋势延续、订单流冲击后的短期修复、以及流动性和拥挤度约束下的可交易性筛选。

本文没有回避验证缺口。当前结果足以作为高质量内部研究冻结点，但还不是可以直接对外宣称顶会级实证结论的终点。下一步应严格执行已经冻结的未触碰留出集协议，把成本、容量、状态相关性和多重检验纳入统一审计。

\begin{{thebibliography}}{{9}}
\bibitem{{debondt1985}} De Bondt, W. and Thaler, R. (1985). Does the stock market overreact? \emph{{Journal of Finance}}.
\bibitem{{jegadeesh1993}} Jegadeesh, N. and Titman, S. (1993). Returns to buying winners and selling losers. \emph{{Journal of Finance}}.
\bibitem{{fama1993}} Fama, E. and French, K. (1993). Common risk factors in the returns on stocks and bonds. \emph{{Journal of Financial Economics}}.
\bibitem{{harvey2016}} Harvey, C., Liu, Y., and Zhu, H. (2016). ... and the cross-section of expected returns. \emph{{Review of Financial Studies}}.
\bibitem{{gu2020}} Gu, S., Kelly, B., and Xiu, D. (2020). Empirical asset pricing via machine learning. \emph{{Review of Financial Studies}}.
\bibitem{{white2000}} White, H. (2000). A reality check for data snooping. \emph{{Econometrica}}.
\bibitem{{hansen2005}} Hansen, P. (2005). A test for superior predictive ability. \emph{{Journal of Business and Economic Statistics}}.
\bibitem{{bailey2014}} Bailey, D. and L{{\'o}}pez de Prado, M. (2014). The deflated Sharpe ratio: correcting for selection bias, backtest overfitting, and non-normality. \emph{{Journal of Portfolio Management}}.
\bibitem{{frazzini2018}} Frazzini, A., Israel, R., and Moskowitz, T. (2018). Trading costs of asset pricing anomalies. Working paper.
\end{{thebibliography}}

\end{{document}}
"""


def main() -> None:
    manifest = load_json(MANIFEST)
    phase_audit = load_json(PHASE_AUDIT)
    regime_audit = load_json(REGIME_AUDIT)
    factors = manifest["factors"]
    if len(factors) != 10:
        raise RuntimeError(f"Expected 10 frozen factors, found {len(factors)}")
    if any(float(row["sharpe"]) <= 8 for row in factors):
        raise RuntimeError("Frozen portfolio contains Sharpe <= 8")
    if float(manifest["maximum_pairwise_corr"]) >= 0.5:
        raise RuntimeError("Frozen portfolio violates correlation threshold")
    pnls = load_pnls(factors)
    details = build_details(manifest)
    chart_sharpe(factors)
    chart_corr(factors, manifest["correlation_matrix"])
    chart_curves(factors, pnls)
    chart_phases(phase_audit)
    write_detail_files(details)
    TEX.write_text(make_tex(manifest, details, phase_audit, regime_audit), encoding="utf-8")
    print(json.dumps({
        "tex": str(TEX),
        "pdf": str(PDF),
        "detail_md": str(DETAIL_MD),
        "detail_json": str(DETAIL_JSON),
        "detail_tsv": str(DETAIL_TSV),
        "figures": str(FIG),
        "factors": len(factors),
        "maximum_pairwise_corr": manifest["maximum_pairwise_corr"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
