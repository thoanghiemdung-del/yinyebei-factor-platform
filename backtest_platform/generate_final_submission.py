#!/usr/bin/env python3
"""Generate paper-ready figures and an auditable LaTeX submission from frozen results."""

import json
import math
import os
import pathlib
import re
import sqlite3
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont


BASE = pathlib.Path(__file__).resolve().parent
DB = BASE / "backtest.db"
AUDIT = BASE / "experiment_results" / "final_audit_results.json"
PAPER = pathlib.Path(r"D:\yyb\paper")
FIG = PAPER / "figures_final"
TEX = PAPER / "final_submission.tex"
SUMMARY = PAPER / "final_submission_summary.json"

COLORS = {
    "blue": "#2459A9", "orange": "#E07A2F", "green": "#2A8F5B",
    "red": "#C4423B", "purple": "#7952A8", "gray": "#667085",
    "light": "#F4F7FB", "grid": "#D8DEE9", "dark": "#182230",
}


def font(size=28, bold=False):
    choices = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for path in choices:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def safe_float(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except Exception:
        return default


def fmt(value, digits=3):
    return f"{safe_float(value):.{digits}f}"


LATEX_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def esc(text):
    return re.sub(r"[\\&%$#_{}~^]", lambda match: LATEX_ESCAPES[match.group()], str(text or ""))


def short(text, width=84):
    text = str(text or "")
    return text if len(text) <= width else text[:width - 3] + "..."


def daily_from_cumulative(values):
    try:
        arr = np.asarray(values or [], dtype=float)
    except Exception:
        return np.asarray([], dtype=float)
    arr = arr[np.isfinite(arr)]
    return np.diff(arr) if arr.size >= 3 else np.asarray([], dtype=float)


def abs_corr(a, b):
    n = min(len(a), len(b))
    if n < 30:
        return 0.0
    a, b = np.asarray(a[-n:]), np.asarray(b[-n:])
    valid = np.isfinite(a) & np.isfinite(b)
    if valid.sum() < 30 or np.std(a[valid]) <= 1e-12 or np.std(b[valid]) <= 1e-12:
        return 0.0
    return abs(float(np.corrcoef(a[valid], b[valid])[0, 1]))


def load():
    with AUDIT.open("r", encoding="utf-8") as f:
        audit = json.load(f)
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT id, expression, type, metrics_json, pnl_json, timestamp "
        "FROM alpha_history"
    ).fetchall()
    con.close()
    history = {}
    singles = []
    for aid, expr, typ, metrics_json, pnl_json, timestamp in rows:
        try:
            metrics = json.loads(metrics_json or "{}")
            pnl = json.loads(pnl_json or "[]")
        except Exception:
            continue
        if isinstance(pnl, dict):
            pnl = pnl.get("pnl_series") or pnl.get("_pnl_series") or pnl.get("oos_pnl") or []
        row = {
            "id": aid, "expression": expr or "", "type": typ or "alpha",
            "metrics": metrics, "pnl": pnl if isinstance(pnl, list) else [],
            "daily": daily_from_cumulative(pnl if isinstance(pnl, list) else []),
            "timestamp": timestamp,
        }
        history[aid] = row
        if row["type"] == "alpha" and safe_float(metrics.get("n_days")) >= 30:
            singles.append(row)
    return audit, history, singles


def canvas(width=1800, height=1050, title=""):
    im = Image.new("RGB", (width, height), "white")
    dr = ImageDraw.Draw(im)
    dr.text((70, 38), title, fill=COLORS["dark"], font=font(38, True))
    return im, dr


def save(im, name):
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / name
    im.save(path, quality=96)
    return path


def atomic_json(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def axis(dr, box, x_labels=None, y_labels=None):
    x0, y0, x1, y1 = box
    dr.line((x0, y1, x1, y1), fill=COLORS["dark"], width=3)
    dr.line((x0, y0, x0, y1), fill=COLORS["dark"], width=3)
    for val, label in y_labels or []:
        y = int(y1 - val * (y1 - y0))
        dr.line((x0, y, x1, y), fill=COLORS["grid"], width=2)
        dr.text((x0 - 95, y - 14), label, fill=COLORS["gray"], font=font(22))
    for val, label in x_labels or []:
        x = int(x0 + val * (x1 - x0))
        dr.text((x - 28, y1 + 15), label, fill=COLORS["gray"], font=font(22))


def chart_confirmatory(audit):
    rows = [r for r in audit["results"] if r.get("family") == "confirmatory" and r.get("success")]
    rows.sort(key=lambda r: safe_float(r.get("metrics", {}).get("sharpe")), reverse=True)
    rows = rows[:16]
    im, dr = canvas(title="Confirmatory OOS Sharpe ranking (IS-selected baskets, 2023 OOS)")
    x0, y0, x1, y1 = 590, 120, 1720, 970
    vals = [safe_float(r["metrics"].get("sharpe")) for r in rows] or [1]
    vmax = max(max(vals), 1.0) * 1.08
    for i, row in enumerate(rows):
        y = y0 + i * 50
        val = safe_float(row["metrics"].get("sharpe"))
        w = int((x1 - x0) * val / vmax)
        color = COLORS["green"] if row["neutralize"] != "none" else COLORS["blue"]
        dr.rectangle((x0, y, x0 + w, y + 28), fill=color)
        dr.text((50, y + 1), short(row["label"], 56), fill=COLORS["dark"], font=font(21))
        dr.text((x0 + w + 12, y + 1), fmt(val), fill=COLORS["dark"], font=font(21, True))
    return save(im, "confirmatory_sharpe.png")


def chart_neutralization(audit):
    rows = [r for r in audit["results"] if r.get("family") == "confirmatory" and r.get("success")]
    groups = defaultdict(dict)
    for row in rows:
        base = re.sub(r"_(none|market_cap|market_cap_regression|beta|market_cap_beta)$", "", row["label"])
        groups[base][row["neutralize"]] = safe_float(row["metrics"].get("sharpe"))
    modes = ["market_cap", "market_cap_regression", "beta", "market_cap_beta"]
    deltas = {mode: [] for mode in modes}
    for values in groups.values():
        if "none" not in values:
            continue
        for mode in modes:
            if mode in values:
                deltas[mode].append(values[mode] - values["none"])
    means = [float(np.mean(deltas[m])) if deltas[m] else 0.0 for m in modes]
    im, dr = canvas(title="Neutralization ablation: mean OOS Sharpe change versus no neutralization")
    x0, y0, x1, y1 = 180, 160, 1660, 880
    zero = (y0 + y1) // 2
    dr.line((x0, zero, x1, zero), fill=COLORS["dark"], width=3)
    vmax = max(max(abs(x) for x in means), 0.5) * 1.25
    bw = 220
    for i, (mode, val) in enumerate(zip(modes, means)):
        x = x0 + 100 + i * 350
        h = int((y1 - y0) * 0.45 * abs(val) / vmax)
        color = COLORS["green"] if val >= 0 else COLORS["red"]
        box = (x, zero - h, x + bw, zero) if val >= 0 else (x, zero, x + bw, zero + h)
        dr.rectangle(box, fill=color)
        dr.text((x + 20, zero - h - 42 if val >= 0 else zero + h + 10), fmt(val), fill=COLORS["dark"], font=font(26, True))
        dr.text((x - 20, y1 + 28), mode.replace("_", "\n"), fill=COLORS["dark"], font=font(23))
    return save(im, "neutralization_ablation.png")


def chart_nesting(audit):
    rows = [r for r in audit["results"] if r.get("family") == "exploratory_nesting" and r.get("success")]
    best = {}
    for row in rows:
        layer = row.get("metadata", {}).get("layer", 0)
        val = safe_float(row["metrics"].get("sharpe"))
        if layer not in best or val > best[layer][0]:
            best[layer] = (val, row["label"])
    im, dr = canvas(title="Exploratory hierarchical nesting ablation (best OOS Sharpe per layer)")
    x0, y0, x1, y1 = 210, 160, 1640, 880
    vals = [best.get(k, (0, ""))[0] for k in (1, 2, 3)]
    vmax = max(max(vals or [1]), 1) * 1.15
    for i, layer in enumerate((1, 2, 3)):
        val, label = best.get(layer, (0.0, "not completed"))
        x = x0 + 190 + i * 410
        h = int((y1 - y0) * val / vmax)
        dr.rectangle((x, y1 - h, x + 220, y1), fill=[COLORS["blue"], COLORS["orange"], COLORS["purple"]][i])
        dr.text((x + 55, y1 - h - 45), fmt(val), fill=COLORS["dark"], font=font(28, True))
        dr.text((x + 72, y1 + 22), f"Layer {layer}", fill=COLORS["dark"], font=font(25, True))
        dr.text((x - 65, y1 + 62), short(label, 38), fill=COLORS["gray"], font=font(18))
    axis(dr, (x0, y0, x1, y1), y_labels=[(i / 5, fmt(vmax * i / 5, 1)) for i in range(6)])
    return save(im, "nesting_ablation.png")


def chart_strict_curves(audit, history):
    strict = audit.get("strict_superalpha_selection") or []
    im, dr = canvas(title="Strict low-correlation high-Sharpe candidates: cumulative OOS PnL")
    x0, y0, x1, y1 = 170, 130, 1690, 920
    curves = []
    for row in strict[:10]:
        pnl = np.asarray(history.get(row["id"], {}).get("pnl") or [], dtype=float)
        if len(pnl) >= 3:
            curves.append((row, pnl - pnl[0]))
    if not curves:
        dr.text((500, 480), "No strict candidates available", fill=COLORS["gray"], font=font(34, True))
        return save(im, "strict_candidate_curves.png")
    low = min(float(np.min(c)) for _, c in curves)
    high = max(float(np.max(c)) for _, c in curves)
    span = max(high - low, 1e-9)
    palette = [COLORS["blue"], COLORS["orange"], COLORS["green"], COLORS["red"], COLORS["purple"], "#008C95", "#A06A00", "#5A6D8A", "#B0568D", "#516B2A"]
    for idx, (row, curve) in enumerate(curves):
        pts = []
        for i, value in enumerate(curve):
            x = x0 + int((x1 - x0) * i / max(len(curve) - 1, 1))
            y = y1 - int((y1 - y0) * (float(value) - low) / span)
            pts.append((x, y))
        dr.line(pts, fill=palette[idx % len(palette)], width=4)
        dr.text((x0 + 35 + (idx % 2) * 650, y0 + 18 + (idx // 2) * 30),
                f"{idx + 1}. {row['id'][:8]} S={fmt(row.get('sharpe'))}",
                fill=palette[idx % len(palette)], font=font(21, True))
    axis(dr, (x0, y0, x1, y1), y_labels=[(i / 5, fmt(low + span * i / 5, 2)) for i in range(6)])
    return save(im, "strict_candidate_curves.png")


def chart_corr_heatmap(audit, history):
    strict = audit.get("strict_superalpha_selection") or []
    ids = [row["id"] for row in strict[:10]]
    n = max(len(ids), 1)
    im, dr = canvas(title="Absolute daily-PnL correlation among strict candidates")
    size = min(100, int(720 / n))
    left, top = 380, 170
    for i in range(n):
        for j in range(n):
            if i >= len(ids) or j >= len(ids):
                value = 0.0
            elif i == j:
                value = 1.0
            else:
                value = abs_corr(history[ids[i]]["daily"], history[ids[j]]["daily"])
            red = int(245 - 170 * value)
            green = int(249 - 75 * value)
            blue = int(255 - 35 * value)
            dr.rectangle((left + j * size, top + i * size, left + (j + 1) * size, top + (i + 1) * size), fill=(red, green, blue), outline="white")
            dr.text((left + j * size + 12, top + i * size + size // 3), fmt(value, 2), fill=COLORS["dark"], font=font(max(15, size // 5), True))
    for i, aid in enumerate(ids):
        dr.text((left - 145, top + i * size + size // 3), f"{i + 1}:{aid[:6]}", fill=COLORS["dark"], font=font(19))
        dr.text((left + i * size + 5, top - 35), str(i + 1), fill=COLORS["dark"], font=font(20, True))
    return save(im, "strict_correlation_heatmap.png")


def chart_is_oos_scatter(singles):
    pts = []
    for row in singles:
        m = row["metrics"]
        x, y = safe_float(m.get("is_sharpe"), None), safe_float(m.get("sharpe"), None)
        if x is not None and y is not None:
            pts.append((x, y))
    im, dr = canvas(title="Single-factor transportability: IS Sharpe versus 2023 OOS Sharpe")
    x0, y0, x1, y1 = 180, 140, 1680, 920
    if not pts:
        return save(im, "is_oos_scatter.png")
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xspan, yspan = max(xmax - xmin, 1), max(ymax - ymin, 1)
    for x, y in pts:
        px = x0 + int((x1 - x0) * (x - xmin) / xspan)
        py = y1 - int((y1 - y0) * (y - ymin) / yspan)
        dr.ellipse((px - 4, py - 4, px + 4, py + 4), fill=COLORS["blue"])
    axis(dr, (x0, y0, x1, y1),
         x_labels=[(i / 5, fmt(xmin + xspan * i / 5, 1)) for i in range(6)],
         y_labels=[(i / 5, fmt(ymin + yspan * i / 5, 1)) for i in range(6)])
    dr.text((720, 980), "IS Sharpe (2020-2022)", fill=COLORS["dark"], font=font(25, True))
    dr.text((30, 500), "OOS Sharpe", fill=COLORS["dark"], font=font(23, True))
    return save(im, "is_oos_scatter.png")


def semantics(expr):
    low = (expr or "").lower()
    parts = []
    if "log_dollar_vol" in low or "turnover" in low or "volume" in low or "amihud" in low:
        parts.append("liquidity and crowdedness")
    if "ret_" in low or "cumret" in low or "ts_delta" in low:
        parts.append("medium-horizon continuation or reversal")
    if "rev_" in low or "gap" in low or "auction" in low:
        parts.append("short-horizon overreaction correction")
    if "vol" in low or "beta" in low or "max_dd" in low:
        parts.append("risk-regime conditioning")
    if "vwap" in low or "intraday" in low or "shadow" in low or "body" in low:
        parts.append("intraday price formation")
    return "; ".join(parts) if parts else "composite cross-sectional signal"


SUBFACTOR_MEANINGS = {
    "log_dollar_vol": "log trading-value scale; a liquidity, capacity, and crowding proxy",
    "turnover_rate": "share turnover intensity; a trading-pressure and crowdedness proxy",
    "turnover_5d": "short-horizon turnover intensity; a transient liquidity-demand proxy",
    "volume_profile_ratio": "relative volume-shape abnormality; an intraday participation proxy",
    "abnormal_vol_rev": "abnormal-volume reversal; a short-lived price-pressure proxy",
    "amihud_20d": "Amihud illiquidity; price impact per traded value",
    "ret_20d": "medium-horizon return; continuation versus reversal state",
    "ret_120d_skip5": "longer-horizon return excluding the most recent week; persistent trend proxy",
    "beta_60d": "rolling market beta; systematic risk exposure",
    "max_dd": "drawdown state; downside-risk and stress-regime proxy",
    "vwap": "volume-weighted price location; intraday price-formation proxy",
    "gap": "overnight price discontinuity; delayed information and overreaction proxy",
    "auction": "auction-related price pressure; opening or closing imbalance proxy",
    "shadow": "candlestick shadow; intraday rejection and price-pressure proxy",
    "body": "candlestick body; intraday directional price-formation proxy",
}


def detected_subfactors(expr):
    low = (expr or "").lower()
    return [(name, meaning) for name, meaning in SUBFACTOR_MEANINGS.items() if name in low]


def referenced_ids(expr):
    return re.findall(r"(?:superalpha|lgb)_ref\(([^)]+)\)", expr or "")


def lineage_expressions(aid, history, seen=None):
    seen = set() if seen is None else seen
    if not aid or aid in seen or aid not in history:
        return []
    seen.add(aid)
    expr = history[aid]["expression"]
    expressions = [expr] if expr else []
    for ref in referenced_ids(expr):
        expressions.extend(lineage_expressions(ref, history, seen))
    return expressions


def lineage_subfactors(aid, fallback_expr, history):
    expressions = lineage_expressions(aid, history) or [fallback_expr or ""]
    found = {}
    for expr in expressions:
        for name, meaning in detected_subfactors(expr):
            found[name] = meaning
    return sorted(found.items())


def seed_rows(audit, history):
    ids = audit.get("selections", {}).get("greedy_corr_0.5_n10", [])
    rows = []
    for aid in ids:
        row = history.get(aid)
        if row:
            rows.append((aid, row["expression"], semantics(row["expression"]), row["metrics"]))
    return rows


def compact_semantics(meaning):
    phrases = [part.strip() for part in (meaning or "").split(";") if part.strip()]
    return "; ".join(phrases[:2]) if phrases else "composite cross-sectional signal"


def make_tex(audit, history, singles):
    confirm = [r for r in audit["results"] if r.get("family") == "confirmatory" and r.get("success")]
    confirm.sort(key=lambda r: safe_float(r["metrics"].get("sharpe")), reverse=True)
    nesting = [r for r in audit["results"] if r.get("family") == "exploratory_nesting" and r.get("success")]
    nesting.sort(key=lambda r: safe_float(r["metrics"].get("sharpe")), reverse=True)
    strict = audit.get("strict_superalpha_selection") or []
    seeds = seed_rows(audit, history)
    best = confirm[0] if confirm else {"label": "n/a", "metrics": {}}
    target_status = (
        f"The requested portfolio of ten candidates is satisfied with {len(strict)} candidates."
        if len(strict) >= 10 else
        f"The requested portfolio of ten candidates is not satisfied: only {len(strict)} candidates pass both constraints."
    )

    top_rows = "\n".join(
        f"{i + 1} & {esc(short(r['label'], 58))} & {fmt(r['metrics'].get('sharpe'))} & "
        f"{fmt(r['metrics'].get('pearson_ic'), 4)} & {fmt(r['metrics'].get('turnover'), 4)} \\\\"
        for i, r in enumerate(confirm[:12])
    ) or r"\multicolumn{5}{c}{No completed confirmatory rows} \\"
    strict_rows = "\n".join(
        f"{i + 1} & {esc(r['id'][:12])} & {fmt(r.get('sharpe'))} & {fmt(r.get('ic'), 4)} & "
        f"{fmt(r.get('fitness'))} & {fmt(r.get('turnover'), 4)} & {fmt(r.get('max_corr_to_selected'), 4)} \\\\"
        for i, r in enumerate(strict[:10])
    ) or r"\multicolumn{7}{c}{No candidate passes the strict screen} \\"
    strict_economic_rows = []
    child_dictionary = {}
    for i, row in enumerate(strict[:10]):
        factors = lineage_subfactors(row.get("id"), row.get("expression"), history)
        child_dictionary.update(dict(factors))
        factor_names = ", ".join(name for name, _ in factors) or "legacy composite; leaf labels unavailable"
        strict_economic_rows.append(
            f"{i + 1} & {esc(row['id'][:12])} & {esc(short(semantics(row.get('expression')), 72))} & "
            f"{esc(short(factor_names, 105))} \\\\"
        )
    strict_economic_table = "\n".join(strict_economic_rows) or (
        r"\multicolumn{4}{c}{No strict candidate passes the frozen screen} \\"
    )
    for _, expr, _, _ in seeds:
        child_dictionary.update(dict(detected_subfactors(expr)))
    child_rows = "\n".join(
        f"{esc(name)} & {esc(meaning)} \\\\"
        for name, meaning in sorted(child_dictionary.items())
    ) or r"\multicolumn{2}{c}{No labelled leaf proxy available} \\"
    seed_table = "\n".join(
        f"{i + 1} & \\path{{{short(expr, 42)}}} & {esc(compact_semantics(meaning))} & "
        f"{fmt(metrics.get('is_sharpe'))} & {fmt(metrics.get('sharpe'))} \\\\"
        for i, (_, expr, meaning, metrics) in enumerate(seeds)
    ) or r"\multicolumn{5}{c}{No frozen greedy seed basket} \\"

    tex = rf"""
\documentclass[10pt,a4paper]{{article}}
\usepackage[margin=2.0cm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,longtable,graphicx,float,hyperref,xcolor,array}}
\hypersetup{{colorlinks=true,linkcolor=blue,urlcolor=blue,citecolor=blue}}
\title{{Auditable Hierarchical Alpha Ensembling for A-Share Cross-Sectional Prediction\\
\large Strict IS/OOS Separation, Correlation-Constrained Greedy Selection, and Matrix-Level Nesting}}
\author{{YYB Quantitative Research Platform}}
\date{{Generated from frozen evidence: {esc(audit.get('generated_at'))}}}
\begin{{document}}
\maketitle

\begin{{abstract}}
We study cross-sectional prediction of five-day A-share returns using a local research platform with strict
in-sample (IS, 2020--2022) selection and out-of-sample (OOS, 2023) evaluation. The frozen audit compares
equal weighting, ICIR weighting, and inverse-volatility shrinkage across unfiltered and correlation-constrained
baskets; five neutralization regimes; and exploratory matrix-level hierarchical nesting. The best confirmatory
configuration is \texttt{{{esc(best.get('label'))}}} with OOS Sharpe {fmt(best.get('metrics', {}).get('sharpe'))}.
We additionally apply a hard portfolio screen requiring Sharpe $>10$ and pairwise absolute daily-PnL
correlation $<0.5$. {esc(target_status)} We report this shortfall directly rather than fill the target with
economically redundant variants. All headline tables and figures are generated from a single frozen JSON
artifact, and exploratory nested results are separated from confirmatory evidence.
\end{{abstract}}

\section{{Research question and contributions}}
The empirical question is whether economically interpretable A-share signals can be combined into robust,
low-redundancy predictors under strict temporal separation. The platform contributes: (i) an auditable IS/OOS
protocol; (ii) true PnL-correlation greedy selection rather than family-name proxies; (iii) five explicit
neutralization regimes; and (iv) matrix-level nesting in which a cached OOS combo matrix can become an input to
a higher-level combo without reparsing its leaves. The audit also records negative results, skipped features,
and missing infrastructure rather than silently excluding them.

\section{{Data and validation protocol}}
The local panel contains 970 trading days, 5,515 A-share securities, and 89 raw or derived fields. The target is
the future five-day return. IS spans 2020--2022 and is used for ranking and weight estimation; OOS spans 2023
and is used only for evaluation. Correlation screening converts cumulative PnL to daily changes and uses
absolute Pearson correlation. The confirmatory matrix is frozen before ranking OOS results. Exploratory L1--L3
nesting is explicitly labelled exploratory because its layer choices inspect OOS outcomes.

\paragraph{{Trading-protocol limitation.}}
The current research engine excludes immature listings and ST securities, but it does not yet model all
execution frictions needed for a production claim: commissions, stamp duty, market impact, limit-up/down
execution, T+1 constraints, and capacity. Reported Sharpe ratios are therefore signal-research metrics, not
deployable net-performance claims.

\section{{Combination methods}}
For standardized cross-sectional signals $z(F_i)$, the linear combo is
\[
F_c = \sum_{{i=1}}^N w_i z(F_i).
\]
Equal weighting uses $w_i=1/N$. ICIR weighting uses IS rank-IC stability,
$w_i \propto \max(0.1,\mathrm{{ICIR}}_i^{{IS}})$. The platform's historical ``ridge'' label is retained in
tables for compatibility, but the implementation is accurately described as inverse-volatility shrinkage:
$w_i \propto 1/(\sigma_i^{{IS}}+\mathrm{{median}}(\sigma^{{IS}}))$. It is not a standard ridge-regression
optimizer. LightGBM is an exploratory nonlinear benchmark and is not mixed into the confirmatory table.

\section{{Neutralization ablation}}
The audit evaluates: no neutralization; market-cap decile demeaning; cross-sectional log-market-cap regression;
cross-sectional beta regression; and joint log-market-cap plus beta regression. Reliable industry labels are
not available in the current data catalog, so industry neutralization is not fabricated. Figure~\ref{{fig:neutral}}
reports mean Sharpe changes relative to the unneutralized control.

\begin{{figure}}[H]\centering
\includegraphics[width=0.95\linewidth]{{figures_final/neutralization_ablation.png}}
\caption{{Neutralization ablation using frozen confirmatory baskets.}}\label{{fig:neutral}}
\end{{figure}}

\section{{Confirmatory results}}
\begin{{figure}}[H]\centering
\includegraphics[width=0.98\linewidth]{{figures_final/confirmatory_sharpe.png}}
\caption{{Top confirmatory OOS Sharpe values. Baskets and weights are selected using IS information only.}}
\end{{figure}}

\begin{{table}}[H]\centering\small
\caption{{Top frozen confirmatory configurations.}}
\begin{{tabular}}{{r l r r r}}
\toprule Rank & Configuration & Sharpe & IC & Turnover \\
\midrule
{top_rows}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{figure}}[H]\centering
\includegraphics[width=0.92\linewidth]{{figures_final/is_oos_scatter.png}}
\caption{{Single-factor IS Sharpe versus 2023 OOS Sharpe. Dispersion motivates explicit OOS isolation and
economic screening.}}
\end{{figure}}

\section{{Correlation-constrained target portfolio}}
The delivery target is ten factors with Sharpe $>10$ and pairwise absolute daily-PnL correlation $<0.5$.
The screen is hard: no relaxation and no duplicate PnL curves are admitted. {esc(target_status)}

\begin{{table}}[H]\centering\small
\caption{{Strict high-Sharpe, low-correlation screen.}}
\begin{{tabular}}{{r l r r r r r}}
\toprule Rank & ID prefix & Sharpe & IC & Fitness & Turnover & Max corr. \\
\midrule
{strict_rows}
\bottomrule
\end{{tabular}}
\end{{table}}

\begin{{figure}}[H]\centering
\includegraphics[width=0.95\linewidth]{{figures_final/strict_candidate_curves.png}}
\caption{{Cumulative OOS PnL curves for strict candidates.}}
\end{{figure}}
\begin{{figure}}[H]\centering
\includegraphics[width=0.78\linewidth]{{figures_final/strict_correlation_heatmap.png}}
\caption{{Absolute daily-PnL correlation heatmap for strict candidates.}}
\end{{figure}}

\subsection{{Economic interpretation of strict candidates}}
Each surviving strict candidate is an ensemble rather than an atomic anomaly. The table reports its dominant
economic interpretation and detected child proxies. For new nested records, child lookup follows preserved
\texttt{{superalpha\_ref(...)}} lineage recursively. For legacy cached records, the stored expression is inspected
directly and missing leaf labels are reported rather than invented.

\begin{{longtable}}{{r l p{{5.0cm}} p{{6.0cm}}}}
\toprule Rank & ID prefix & Ensemble interpretation & Detected child proxies \\
\midrule
{strict_economic_table}
\bottomrule
\end{{longtable}}

\section{{Economic interpretation of the frozen greedy seed basket}}
The correlation-constrained seed basket is not presented as a causal structural model. It is an interpretable
set of cross-sectional proxies used to construct candidate ensembles. Liquidity terms proxy crowding and
trading frictions; return terms proxy continuation or overreaction; reversal and auction terms proxy short-lived
price pressure; risk terms condition exposure on the volatility regime; and intraday terms describe price
formation. Each leaf remains inspectable in the frozen manifest.

\footnotesize
\begin{{longtable}}{{r >{{\raggedright\arraybackslash}}p{{4.7cm}} >{{\raggedright\arraybackslash}}p{{5.4cm}} r r}}
\toprule Rank & Leaf expression & Economic interpretation & IS Sharpe & OOS Sharpe \\
\midrule
{seed_table}
\bottomrule
\end{{longtable}}
\normalsize

\subsection{{Child-factor economic dictionary}}
The following dictionary explains the detected leaf proxies used by the strict candidates and frozen greedy
seed basket. Operators such as ranking, z-scoring, absolute deviation, and signed aggregation change scaling or
interaction shape; they do not create a new economic primitive.

\begin{{longtable}}{{p{{3.6cm}} p{{11.2cm}}}}
\toprule Child proxy & Economic interpretation \\
\midrule
{child_rows}
\bottomrule
\end{{longtable}}

\section{{Exploratory hierarchical nesting}}
Matrix-level nesting caches each OOS combo matrix and reuses it as a higher-level input. New records preserve
lineage through \texttt{{superalpha\_ref(history-id)}} references while loading the corresponding cached matrix.
This is an engineering contribution and an exploratory modeling result: selecting the best lower layer after
viewing OOS performance is not confirmatory evidence.

\begin{{figure}}[H]\centering
\includegraphics[width=0.88\linewidth]{{figures_final/nesting_ablation.png}}
\caption{{Exploratory L1--L3 nesting ablation.}}
\end{{figure}}

\section{{Threats to validity}}
\begin{{enumerate}}
\item The OOS window contains one calendar year. A publishable asset-pricing claim requires multi-period
walk-forward validation and regime splits.
\item Transaction costs, delay sensitivity, T+1 execution, price limits, and capacity remain to be integrated.
\item The factor search space is large. Multiple testing is controlled operationally by IS-only selection and
frozen OOS reporting, but formal false-discovery analysis remains future work.
\item Historical cached combos created before lineage preservation remain valid matrices but cannot support
leaf-level economic attribution. They are marked as legacy artifacts.
\item Industry neutralization is absent because reliable industry labels are unavailable in the current snapshot.
\end{{enumerate}}

\section{{Reproducibility}}
The frozen evidence file is \path{{experiment_results/final_audit_results.json}}. The runner is
\path{{run_final_audit_experiments.py}}. Every confirmatory row stores input IDs, weighting method,
neutralization mode, requested and valid feature counts, skipped features, metrics, and PnL. The Flask service
remains available for remote read-only review throughout the audit; external Alpha submission is outside the
scope of this work.

\section{{Conclusion}}
The final audit replaces an earlier narrative report with a reproducible evidence chain. The main empirical
lesson is not that arbitrary stacking guarantees high Sharpe. Rather, strict temporal separation, explicit
neutralization, and true PnL-correlation constraints expose how quickly superficially strong variants collapse
into the same economic bet. Matrix-level nesting remains useful, but only when its lineage and exploratory
status are preserved.

\begin{{thebibliography}}{{9}}
\bibitem{{debondt1985}} De Bondt, W. and Thaler, R. (1985). Does the stock market overreact? \emph{{Journal of Finance}}.
\bibitem{{jegadeesh1993}} Jegadeesh, N. and Titman, S. (1993). Returns to buying winners and selling losers. \emph{{Journal of Finance}}.
\bibitem{{fama1993}} Fama, E. and French, K. (1993). Common risk factors in the returns on stocks and bonds. \emph{{Journal of Financial Economics}}.
\bibitem{{harvey2016}} Harvey, C., Liu, Y., and Zhu, H. (2016). ... and the cross-section of expected returns. \emph{{Review of Financial Studies}}.
\bibitem{{gu2020}} Gu, S., Kelly, B., and Xiu, D. (2020). Empirical asset pricing via machine learning. \emph{{Review of Financial Studies}}.
\end{{thebibliography}}
\end{{document}}
"""
    TEX.write_text(tex, encoding="utf-8")
    atomic_json(SUMMARY, {
        "generated_at": audit.get("generated_at"),
        "confirmatory_rows": len(confirm),
        "exploratory_nesting_rows": len(nesting),
        "strict_candidate_count": len(strict),
        "best_confirmatory": best,
        "paper": str(TEX),
    })


def main():
    PAPER.mkdir(parents=True, exist_ok=True)
    audit, history, singles = load()
    chart_confirmatory(audit)
    chart_neutralization(audit)
    chart_nesting(audit)
    chart_strict_curves(audit, history)
    chart_corr_heatmap(audit, history)
    chart_is_oos_scatter(singles)
    make_tex(audit, history, singles)
    print(f"generated {TEX}")


if __name__ == "__main__":
    main()
