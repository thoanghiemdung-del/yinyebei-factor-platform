#!/usr/bin/env python3
"""Generate the afternoon evidence bundle and LaTeX paper from measured DB history."""

import csv
import json
import math
import os
import pathlib
import re
import sqlite3
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont


BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "backtest.db"
RESULTS = BASE / "experiment_results"
PAPER = pathlib.Path(r"D:\yyb\paper")
FIG = PAPER / "afternoon_figures"
TEX = PAPER / "afternoon_final_submission.tex"
SUMMARY = PAPER / "afternoon_final_summary.json"
MANIFEST = PAPER / "afternoon_final_factors.json"
TSV = PAPER / "afternoon_final_factors.tsv"

COLORS = {
    "blue": "#2459A9", "orange": "#E07A2F", "green": "#2A8F5B",
    "red": "#C4423B", "purple": "#7952A8", "gray": "#667085",
    "grid": "#D8DEE9", "dark": "#182230",
}

LEAF_MEANINGS = {
    "ret_20d": "medium-horizon continuation versus reversal state",
    "ret_120d_skip5": "persistent trend excluding the most recent trading week",
    "turnover_rate": "share-turnover intensity and crowdedness",
    "turnover_5d": "short-horizon liquidity demand",
    "volume_profile_ratio": "relative volume-shape abnormality and intraday participation",
    "abnormal_vol_rev": "abnormal-volume reversal and transient price pressure",
    "amihud_20d": "Amihud illiquidity and price impact per traded value",
    "log_dollar_vol": "trading-value scale, capacity, and crowding",
    "auction_return": "auction imbalance and short-lived price pressure",
    "rev_5d": "short-horizon return reversal",
    "rev_1d": "one-day overreaction correction",
    "bollinger_pos": "price location within a recent volatility envelope",
    "beta_60d": "rolling systematic market exposure",
}

LATEX = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def esc(value):
    return re.sub(r"[\\&%$#_{}~^]", lambda match: LATEX[match.group()], str(value or ""))


def font(size=28, bold=False):
    options = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for path in options:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def sf(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def fmt(value, digits=3):
    return f"{sf(value):.{digits}f}"


def parse_pnl(raw):
    try:
        values = json.loads(raw or "[]")
    except Exception:
        return []
    if isinstance(values, dict):
        values = values.get("pnl_series") or values.get("_pnl_series") or values.get("oos_pnl") or []
    return values if isinstance(values, list) else []


def daily(values):
    arr = np.asarray(values or [], dtype=float)
    return np.diff(arr) if arr.size >= 3 else np.asarray([], dtype=float)


def abs_corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return 1.0
    aa, bb = np.asarray(a[-n:]), np.asarray(b[-n:])
    valid = np.isfinite(aa) & np.isfinite(bb)
    if valid.sum() < 30 or np.std(aa[valid]) <= 1e-12 or np.std(bb[valid]) <= 1e-12:
        return 1.0
    return abs(float(np.corrcoef(aa[valid], bb[valid])[0, 1]))


def theme(expression):
    low = (expression or "").lower()
    groups = {
        "reversal": ("rev_", "auction", "bollinger", "gap"),
        "momentum": ("ret_", "cumret", "trend", "breakout"),
        "liquidity": ("turnover", "volume", "amihud", "dollar"),
        "risk": ("beta", "vol", "downside", "max_dd"),
        "microstructure": ("vwap", "intraday", "shadow", "auction"),
    }
    scores = [(sum(key in low for key in keys), name) for name, keys in groups.items()]
    score, name = max(scores)
    return name if score else "composite"


def load_history():
    connection = sqlite3.connect(DB)
    rows = connection.execute(
        "SELECT id, expression, COALESCE(type,'alpha'), metrics_json, pnl_json, timestamp "
        "FROM alpha_history WHERE pnl_json IS NOT NULL AND length(pnl_json)>5"
    ).fetchall()
    connection.close()
    out = {}
    for aid, expression, kind, metrics_json, pnl_json, timestamp in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
        except Exception:
            continue
        pnl = parse_pnl(pnl_json)
        changes = daily(pnl)
        if len(changes) < 30 or sf(metrics.get("n_days")) < 30:
            continue
        out[aid] = {
            "id": aid, "expression": expression or "", "type": kind,
            "theme": theme(expression), "metrics": metrics, "pnl": pnl,
            "daily": changes, "timestamp": timestamp,
        }
    return out


def strict_select(history, minimum=8.0, maximum_corr=0.5):
    rows = [row for row in history.values() if sf(row["metrics"].get("sharpe")) > minimum]
    rows.sort(key=lambda row: (-sf(row["metrics"].get("sharpe")), row["id"]))
    selected = []
    for row in rows:
        values = [abs_corr(row["daily"], old["daily"]) for old in selected]
        if all(value < maximum_corr for value in values):
            selected.append({**row, "max_corr": max(values) if values else 0.0})
    return selected


def ref_ids(expression):
    return re.findall(r"(?:superalpha|lgb)_ref\(([^)]+)\)", expression or "")


def lineage_expressions(aid, history, seen=None):
    seen = set() if seen is None else seen
    if aid not in history or aid in seen:
        return []
    seen.add(aid)
    expression = history[aid]["expression"]
    out = [expression] if expression else []
    for ref in ref_ids(expression):
        out.extend(lineage_expressions(ref, history, seen))
    return out


def leaves(aid, history):
    found = {}
    for expression in lineage_expressions(aid, history):
        low = expression.lower()
        for name, meaning in LEAF_MEANINGS.items():
            if name in low:
                found[name] = meaning
    return found


def economic_meaning(aid, history):
    leaf = leaves(aid, history)
    names = set(leaf)
    parts = []
    if names & {"turnover_rate", "turnover_5d", "volume_profile_ratio", "amihud_20d", "log_dollar_vol"}:
        parts.append("liquidity and crowding")
    if names & {"ret_20d", "ret_120d_skip5"}:
        parts.append("trend or continuation")
    if names & {"rev_5d", "rev_1d", "abnormal_vol_rev", "auction_return", "bollinger_pos"}:
        parts.append("short-horizon reversal")
    if names & {"beta_60d"}:
        parts.append("risk residualization")
    return "; ".join(parts) if parts else "legacy cached composite; leaf lineage unavailable"


def load_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def experiments():
    rows = []
    rows += load_jsonl(RESULTS / "afternoon_extension_experiments.jsonl")
    rows += load_jsonl(RESULTS / "afternoon_deep_experiments.jsonl")
    rows += load_jsonl(RESULTS / "afternoon_backup_experiments.jsonl")
    return rows


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def canvas(title, width=1800, height=1050):
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 38), title, fill=COLORS["dark"], font=font(38, True))
    return image, draw


def save_chart(image, name):
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / name
    image.save(path, quality=96)
    return path


def chart_sharpe(rows):
    image, draw = canvas("Final strict portfolio: measured OOS Sharpe")
    x0, x1, y0 = 540, 1700, 130
    high = max(sf(row["metrics"].get("sharpe")) for row in rows) * 1.08
    for i, row in enumerate(rows):
        y = y0 + 78 * i
        value = sf(row["metrics"].get("sharpe"))
        draw.rectangle((x0, y, x0 + int((x1 - x0) * value / high), y + 42), fill=COLORS["green"])
        draw.text((70, y + 7), f"{i + 1}. {row['id'][:12]} [{row['type']}]", fill=COLORS["dark"], font=font(25))
        draw.text((x0 + int((x1 - x0) * value / high) + 10, y + 7), fmt(value), fill=COLORS["dark"], font=font(25, True))
    return save_chart(image, "strict_sharpe.png")


def corr_matrix(rows):
    n = len(rows)
    return [[abs_corr(rows[i]["daily"], rows[j]["daily"]) for j in range(n)] for i in range(n)]


def chart_corr(rows, matrix):
    image, draw = canvas("Absolute daily-PnL correlation: final strict portfolio")
    n, size, left, top = len(rows), 68, 490, 170
    for i in range(n):
        for j in range(n):
            value = matrix[i][j]
            red = int(240 - 150 * value)
            green = int(248 - 80 * value)
            blue = int(255 - 25 * value)
            draw.rectangle((left + j * size, top + i * size, left + (j + 1) * size, top + (i + 1) * size), fill=(red, green, blue), outline="white")
            draw.text((left + j * size + 12, top + i * size + 23), f"{value:.2f}", fill=COLORS["dark"], font=font(17))
        draw.text((left - 42, top + i * size + 23), str(i + 1), fill=COLORS["dark"], font=font(20, True))
        draw.text((left + i * size + 25, top - 34), str(i + 1), fill=COLORS["dark"], font=font(20, True))
    return save_chart(image, "strict_corr_heatmap.png")


def chart_curves(rows):
    image, draw = canvas("Cumulative OOS PnL: final strict portfolio")
    x0, y0, x1, y1 = 170, 135, 1690, 930
    curves = [np.asarray(row["pnl"], dtype=float) for row in rows]
    low = min(float(np.nanmin(curve)) for curve in curves)
    high = max(float(np.nanmax(curve)) for curve in curves)
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
        draw.line(points, fill=palette[index % len(palette)], width=3)
        draw.text((x0 + 12, y0 + 26 * index), f"{index + 1}. {rows[index]['id'][:8]}", fill=palette[index % len(palette)], font=font(19, True))
    return save_chart(image, "strict_curves.png")


def chart_phases(rows):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("success"):
            grouped[row.get("phase", "unlabelled")].append(sf(row.get("metrics", {}).get("sharpe")))
    items = sorted(grouped.items(), key=lambda item: max(item[1]), reverse=True)[:10]
    image, draw = canvas("Exploratory innovation phases: best measured OOS Sharpe")
    x0, x1, y0 = 620, 1700, 135
    high = max([max(values) for _, values in items] or [1]) * 1.08
    for i, (name, values) in enumerate(items):
        y = y0 + 78 * i
        value = max(values)
        draw.rectangle((x0, y, x0 + int((x1 - x0) * value / high), y + 42), fill=COLORS["purple"])
        draw.text((70, y + 7), f"{name} (n={len(values)})", fill=COLORS["dark"], font=font(23))
        draw.text((x0 + int((x1 - x0) * value / high) + 10, y + 7), fmt(value), fill=COLORS["dark"], font=font(23, True))
    return save_chart(image, "innovation_phases.png")


def make_tex(rows, matrix, all_experiments, generated):
    factor_table = "\n".join(
        f"{i + 1} & {esc(row['id'][:12])} & {esc(row['type'])} & {esc(row['theme'])} & "
        f"{fmt(row['metrics'].get('sharpe'))} & {fmt(row['metrics'].get('pearson_ic'), 4)} & "
        f"{fmt(row['metrics'].get('turnover'), 4)} & {fmt(row['max_corr'], 4)} \\\\"
        for i, row in enumerate(rows)
    )
    economic_table = "\n".join(
        f"{i + 1} & {esc(row['id'][:12])} & {esc(economic_meaning(row['id'], history))} & "
        f"{esc(', '.join(leaves(row['id'], history)) or 'legacy cached leaves unavailable')} \\\\"
        for i, row in enumerate(rows)
    )
    dictionary = {}
    for row in rows:
        dictionary.update(leaves(row["id"], history))
    leaf_table = "\n".join(f"{esc(name)} & {esc(meaning)} \\\\" for name, meaning in sorted(dictionary.items()))
    phase_audit = {}
    phase_audit_path = PAPER / "afternoon_phase_audit.json"
    if phase_audit_path.exists():
        try:
            phase_audit = json.loads(phase_audit_path.read_text(encoding="utf-8"))
        except Exception:
            phase_audit = {}
    phase_counts = Counter(row.get("phase", "unlabelled") for row in all_experiments)
    phase_rows = phase_audit.get("phases") or [
        {
            "phase": name,
            "rows": count,
            "sharpe_gt_8_rows": "n/a",
            "median_sharpe": "n/a",
            "p90_sharpe": "n/a",
            "maximum_sharpe": "n/a",
        }
        for name, count in sorted(phase_counts.items())
    ]
    phase_table = "\n".join(
        f"{esc(row['phase'])} & {row['rows']} & {row['sharpe_gt_8_rows']} & "
        f"{fmt(row['median_sharpe'])} & {fmt(row['p90_sharpe'])} & {fmt(row['maximum_sharpe'])} \\\\"
        for row in phase_rows
    )
    neutralization_table = "\n".join(
        f"{esc(row['neutralize'])} & {row['rows']} & {fmt(row['median_sharpe'])} & "
        f"{fmt(row['p90_sharpe'])} & {fmt(row['maximum_sharpe'])} \\\\"
        for row in phase_audit.get("neutralizations", [])
    )
    robustness = {}
    backup_results = RESULTS / "afternoon_backup_results.json"
    if backup_results.exists():
        try:
            robustness = json.loads(backup_results.read_text(encoding="utf-8")).get(
                "portfolio_counts_by_corr_threshold", {}
            )
        except Exception:
            robustness = {}
    robustness_table = "\n".join(
        f"{esc(threshold)} & {count} \\\\" for threshold, count in sorted(robustness.items())
    )
    regime = {}
    regime_path = PAPER / "afternoon_regime_audit.json"
    if regime_path.exists():
        try:
            regime = json.loads(regime_path.read_text(encoding="utf-8"))
        except Exception:
            regime = {}
    regime_segments = regime.get("segments", [])
    regime_table = "\n".join(
        f"{esc(segment['segment'])} & {segment['n_days']} & "
        f"{fmt(segment['equal_weight_portfolio_sharpe'])} & "
        f"{fmt(segment['maximum_pairwise_abs_daily_pnl_corr'], 4)} \\\\"
        for segment in regime_segments
    )
    regime_subperiod_peak = max(
        (
            float(segment["maximum_pairwise_abs_daily_pnl_corr"])
            for segment in regime_segments
            if segment.get("segment") != "Full 2023 OOS"
        ),
        default=float("nan"),
    )
    maximum = max(matrix[i][j] for i in range(len(rows)) for j in range(i)) if len(rows) > 1 else 0
    types = Counter(row["type"] for row in rows)
    tex = rf"""
\documentclass[10pt,a4paper]{{article}}
\usepackage[margin=1.9cm]{{geometry}}
\usepackage{{amsmath,booktabs,longtable,graphicx,float,hyperref,array,xcolor}}
\emergencystretch=2em
\hypersetup{{colorlinks=true,linkcolor=blue,urlcolor=blue}}
\title{{Diverse Alpha Ensembles for A-Share Cross-Sectional Prediction\\
\large Correlation-Constrained Search, Explicit Residualization, and Hierarchical Nesting}}
\author{{YYB Quantitative Research Platform}}
\date{{Generated from measured evidence: {esc(generated)}}}
\begin{{document}}
\maketitle
\begin{{abstract}}
We report an auditable exploratory search for A-share cross-sectional signals using a local panel with strict
2020--2022 in-sample construction and 2023 out-of-sample (OOS) measurement. The afternoon extension expands
the original combination matrix with near-threshold residualization, cross-style bridge portfolios, explicit
weighted style tilts, and hierarchical nesting. A hard screen identifies {len(rows)} displayed factors with OOS
Sharpe greater than 8 and pairwise absolute daily-PnL correlation below 0.5; the maximum observed pairwise
correlation is {maximum:.4f}. The displayed set contains {types.get('alpha', 0)} atomic factors and
{types.get('superalpha', 0)} measured ensembles. Because the extension adaptively inspects the 2023 OOS window,
these results are an exploratory research artifact, not a deployable or publication-ready performance claim.
\end{{abstract}}

\section{{Research status}}
The artifact is designed to be honest about what is and is not established. It improves engineering
reproducibility, economic lineage, and portfolio diversity. It does not yet meet a top-conference empirical
standard: a new untouched holdout, walk-forward regime splits, transaction-cost modeling, capacity analysis,
and formal multiple-testing control remain required.

\section{{Related work and positioning}}
The atomic primitives connect to established return continuation and reversal evidence
\cite{{debondt1985,jegadeesh1993}}. The cross-style ensembles combine momentum, liquidity, crowding, and
nonlinear interactions in the spirit of modern empirical asset-pricing prediction \cite{{gu2020}}. Because the
afternoon workflow adaptively compares many candidates, its reported Sharpe ratios require stronger safeguards
than a conventional train-test split: factor-zoo multiple-testing discipline \cite{{harvey2016}}, White's
reality check \cite{{white2000}}, Hansen's superior-predictive-ability test \cite{{hansen2005}}, and the deflated
Sharpe ratio \cite{{bailey2014}}. Trading-cost and capacity analysis is also essential before deployment
\cite{{frazzini2018}}. The present artifact implements transparent lineage and a frozen next-holdout protocol;
it does not claim those missing tests have already passed.

\section{{Protocol}}
Atomic factors are ranked using IS-only metrics. Ensemble construction standardizes each leaf cross-sectionally
before aggregation. Residualization variants remove market-cap buckets, log-market-cap exposure, rolling beta,
or joint log-market-cap plus beta exposure. Portfolio selection is a greedy hard screen:
\[
  \mathrm{{Sharpe}}_i^{{OOS}}>8,\qquad
  \max_{{j<i}}\left|\mathrm{{Corr}}(\Delta P_i,\Delta P_j)\right|<0.5,
\]
where $P_i$ is cumulative 2023 OOS PnL and $\Delta P_i$ is its daily change.

\section{{Expanded innovation search}}
The afternoon extension executes sequentially in a single Flask pipeline to keep memory bounded. It records
each real API result before proceeding. Search families include: residualized near-threshold candidates;
cross-style bridges; style-specific anchors; nested style anchors; offset cross-style baskets; explicit
weighted style tilts; pair/triple combo nesting; and L4 meta nesting.

\begin{{figure}}[H]\centering
\includegraphics[width=0.96\linewidth]{{afternoon_figures/innovation_phases.png}}
\caption{{Best measured OOS Sharpe by exploratory innovation phase.}}
\end{{figure}}

\begin{{table}}[H]\centering
\caption{{Recorded exploratory experiments by phase.}}
\begin{{tabular}}{{l r r r r r}}\toprule Phase & Rows & Sharpe $>8$ & Median & P90 & Max. \\\midrule
{phase_table}
\bottomrule\end{{tabular}}
\end{{table}}

\begin{{table}}[H]\centering
\caption{{Descriptive neutralization comparison across recorded experiments. Candidate mixtures differ by row.}}
\begin{{tabular}}{{l r r r r}}\toprule Neutralization & Rows & Median & P90 & Max. \\\midrule
{neutralization_table}
\bottomrule\end{{tabular}}
\end{{table}}

\begin{{table}}[H]\centering
\caption{{Greedy strict-pool sensitivity to the absolute daily-PnL correlation threshold.}}
\begin{{tabular}}{{r r}}\toprule Correlation threshold & Strict pool size \\\midrule
{robustness_table}
\bottomrule\end{{tabular}}
\end{{table}}

\section{{Descriptive sequential split audit}}
The following splits are descriptive diagnostics inside the same adaptively inspected 2023 OOS window, not a
new untouched holdout. All ten displayed factors remain positive in both sequential half-year blocks. However,
the full-window diversity screen is not uniformly stable across subperiods: the highest subperiod pairwise
absolute daily-PnL correlation is {regime_subperiod_peak:.4f}.

\begin{{table}}[H]\centering
\caption{{Descriptive sequential splits within the inspected 2023 OOS window.}}
\begin{{tabular}}{{l r r r}}\toprule Segment & Days & Equal-weight Sharpe & Maximum pairwise corr. \\\midrule
{regime_table}
\bottomrule\end{{tabular}}
\end{{table}}

\section{{Strict final portfolio}}
\begin{{figure}}[H]\centering
\includegraphics[width=0.97\linewidth]{{afternoon_figures/strict_sharpe.png}}
\caption{{Measured OOS Sharpe for the displayed strict portfolio.}}
\end{{figure}}

\footnotesize
\begin{{longtable}}{{r l l l r r r r}}
\caption{{Final displayed factors: hard Sharpe and daily-PnL correlation constraints.}}\\
\toprule Rank & ID prefix & Type & Theme & Sharpe & IC & Turnover & Max corr. \\\midrule
{factor_table}
\bottomrule
\end{{longtable}}
\normalsize

\begin{{figure}}[H]\centering
\includegraphics[width=0.82\linewidth]{{afternoon_figures/strict_corr_heatmap.png}}
\caption{{Absolute daily-PnL correlation matrix for the displayed factors.}}
\end{{figure}}
\begin{{figure}}[H]\centering
\includegraphics[width=0.96\linewidth]{{afternoon_figures/strict_curves.png}}
\caption{{Cumulative 2023 OOS PnL curves for the displayed factors.}}
\end{{figure}}

\section{{Economic interpretation}}
The table separates ensemble-level meaning from detected child proxies. New residualized and nested records
preserve lineage through \texttt{{superalpha\_ref(...)}} references. Historical cache placeholders remain
explicitly marked rather than reverse-engineered.

\footnotesize
\begin{{longtable}}{{r l >{{\raggedright\arraybackslash}}p{{5.3cm}} >{{\raggedright\arraybackslash}}p{{5.2cm}}}}
\toprule Rank & ID prefix & Economic interpretation & Detected child proxies \\\midrule
{economic_table}
\bottomrule
\end{{longtable}}
\normalsize

\subsection{{Child-factor dictionary}}
\begin{{longtable}}{{p{{3.6cm}} p{{11.3cm}}}}
\toprule Child proxy & Economic interpretation \\\midrule
{leaf_table}
\bottomrule
\end{{longtable}}

\section{{Threats to validity}}
\begin{{enumerate}}
\item The adaptive afternoon search inspected 2023 OOS outcomes. A new untouched period is mandatory before
making an external performance claim.
\item Reported signal Sharpe excludes commissions, stamp duty, market impact, limit-up/down execution, T+1
constraints, and capacity.
\item The strict portfolio is correlation-diverse in daily PnL, but economic primitives still overlap around
liquidity, crowding, continuation, and reversal.
\item Sequential diagnostics within the inspected OOS window show that correlation diversification is not
uniformly stable: the peak subperiod maximum pairwise correlation is {regime_subperiod_peak:.4f}. Formal
false-discovery-rate analysis and untouched walk-forward regime validation remain future work.
\end{{enumerate}}

\section{{Reproducibility}}
The final manifest is \path{{paper/afternoon_final_factors.json}}. Raw JSONL logs for all three extension stages are
stored under \path{{experiment_results/}}; exact filenames are listed in the handoff. Descriptive phase and
split artifacts are \path{{paper/afternoon_phase_audit.json}} and \path{{paper/afternoon_regime_audit.json}}.
All runs are local research measurements; this workflow performs no external Alpha submission. A static
SHA-256 delivery snapshot is written to
\path{{paper/afternoon_delivery_index.json}}.

\section{{Untouched-holdout preregistration}}
The next validation protocol is frozen in \path{{paper/next_holdout_preregistration.json}}. It preserves the ten
displayed expressions and their order before any new results are opened. The future evaluation must use a
consecutive period disjoint from 2020--2023, prohibit holdout-driven replacement or retuning, and report
transaction-cost, capacity, block-bootstrap, and multiple-testing diagnostics. The preregistration contains no
new performance measurement and must not be represented as validation.

\section{{Conclusion}}
The expanded search establishes a measured, auditable set of at least ten factors satisfying the requested
Sharpe and correlation constraints. The result is materially stronger than the earlier checkpoint because it
adds cross-style ensembles and explicit residualized lineages while preserving negative results. It remains a
research checkpoint rather than a top-conference-ready empirical claim until untouched holdout validation and
execution modeling are complete.

\begin{{thebibliography}}{{9}}
\bibitem{{debondt1985}} De Bondt, W. and Thaler, R. (1985). Does the stock market overreact? \emph{{Journal of Finance}}. \href{{https://doi.org/10.1111/j.1540-6261.1985.tb05004.x}}{{doi}}.
\bibitem{{jegadeesh1993}} Jegadeesh, N. and Titman, S. (1993). Returns to buying winners and selling losers. \emph{{Journal of Finance}}. \href{{https://doi.org/10.1111/j.1540-6261.1993.tb04702.x}}{{doi}}.
\bibitem{{fama1993}} Fama, E. and French, K. (1993). Common risk factors in the returns on stocks and bonds. \emph{{Journal of Financial Economics}}. \href{{https://doi.org/10.1016/0304-405X(93)90023-5}}{{doi}}.
\bibitem{{harvey2016}} Harvey, C., Liu, Y., and Zhu, H. (2016). ... and the cross-section of expected returns. \emph{{Review of Financial Studies}}. \href{{https://doi.org/10.1093/rfs/hhv059}}{{doi}}.
\bibitem{{gu2020}} Gu, S., Kelly, B., and Xiu, D. (2020). Empirical asset pricing via machine learning. \emph{{Review of Financial Studies}}. \href{{https://doi.org/10.1093/rfs/hhaa009}}{{doi}}.
\bibitem{{white2000}} White, H. (2000). A reality check for data snooping. \emph{{Econometrica}}. \href{{https://doi.org/10.1111/1468-0262.00152}}{{doi}}.
\bibitem{{hansen2005}} Hansen, P. (2005). A test for superior predictive ability. \emph{{Journal of Business and Economic Statistics}}. \href{{https://doi.org/10.1198/073500105000000063}}{{doi}}.
\bibitem{{bailey2014}} Bailey, D. and L{{\'o}}pez de Prado, M. (2014). The deflated Sharpe ratio: correcting for selection bias, backtest overfitting, and non-normality. \emph{{Journal of Portfolio Management}}. \href{{https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551}}{{SSRN}}.
\bibitem{{frazzini2018}} Frazzini, A., Israel, R., and Moskowitz, T. (2018). Trading costs of asset pricing anomalies. Working paper. \href{{https://pages.stern.nyu.edu/\string~afrazzin/pdf/Trading\%20Cost\%20of\%20Asset\%20Pricing\%20Anomalies\%20-\%20Frazzini\%2C\%20Israel\%20and\%20Moskowitz.pdf}}{{author PDF}}.
\end{{thebibliography}}
\end{{document}}
"""
    TEX.write_text(tex, encoding="utf-8")


history = {}


def main():
    global history
    PAPER.mkdir(parents=True, exist_ok=True)
    history = load_history()
    strict = strict_select(history)
    displayed = strict[:10]
    if len(displayed) < 10:
        raise RuntimeError(f"strict portfolio incomplete: {len(displayed)}")
    matrix = corr_matrix(displayed)
    all_experiments = experiments()
    generated = max([row.get("time", "") for row in all_experiments] or ["measured DB snapshot"])
    manifest = {
        "generated_at": generated, "criterion": "OOS Sharpe > 8; absolute daily-PnL Pearson correlation < 0.5",
        "strict_available_count": len(strict), "displayed_count": len(displayed),
        "maximum_pairwise_corr": max(matrix[i][j] for i in range(len(displayed)) for j in range(i)),
        "factors": [{
            "rank": i + 1, "id": row["id"], "expression": row["expression"], "type": row["type"],
            "theme": row["theme"], "sharpe": sf(row["metrics"].get("sharpe")),
            "ic": sf(row["metrics"].get("pearson_ic")), "fitness": sf(row["metrics"].get("fitness")),
            "turnover": sf(row["metrics"].get("turnover")), "max_corr_to_selected": row["max_corr"],
            "economic_meaning": economic_meaning(row["id"], history), "child_factors": leaves(row["id"], history),
        } for i, row in enumerate(displayed)],
        "correlation_matrix": matrix,
    }
    save_json(MANIFEST, manifest)
    with TSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["rank", "id", "type", "theme", "sharpe", "ic", "fitness", "turnover", "max_corr", "economic_meaning", "expression"])
        for row in manifest["factors"]:
            writer.writerow([row[key] for key in ("rank", "id", "type", "theme", "sharpe", "ic", "fitness", "turnover", "max_corr_to_selected", "economic_meaning", "expression")])
    chart_sharpe(displayed)
    chart_corr(displayed, matrix)
    chart_curves(displayed)
    chart_phases(all_experiments)
    make_tex(displayed, matrix, all_experiments, generated)
    save_json(SUMMARY, {
        "generated_at": generated, "strict_available_count": len(strict),
        "displayed_count": len(displayed), "maximum_pairwise_corr": manifest["maximum_pairwise_corr"],
        "experiment_rows": len(all_experiments), "tex": str(TEX),
    })
    print(f"generated {TEX} strict_available={len(strict)} displayed={len(displayed)}")


if __name__ == "__main__":
    main()
