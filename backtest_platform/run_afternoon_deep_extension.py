#!/usr/bin/env python3
"""Second sequential afternoon search: weighted cross-style blends and deeper nesting."""

import itertools
import json
import os
import pathlib
import time

import run_afternoon_extension_experiments as core


BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "experiment_results"
FIRST_FINAL = OUT / "afternoon_extension_results.json"
core.LOG = pathlib.Path(r"D:\yyb\logs\afternoon_deep_runner.log")
core.JSONL = OUT / "afternoon_deep_experiments.jsonl"
core.STATUS = OUT / "afternoon_deep_status.json"
core.FINAL = OUT / "afternoon_deep_results.json"
core.DONE = core.completed_rows()


def call_direct(opener, label, expressions, weights, neutralize, phase, metadata=None, use_ids=False):
    if label in core.DONE:
        core.log(f"reuse {label}")
        return core.DONE[label]
    core.ensure_memory()
    before = core.latest_superalpha_id()
    payload = {
        ("alpha_ids" if use_ids else "expressions"): list(expressions),
        "weights": list(weights), "method": "custom",
        "neutralize": neutralize, "oos_only": True,
        "sub_alpha_limit": min(10, len(expressions)),
    }
    core.log(f"run {label} n={len(expressions)} custom neutralize={neutralize} free_gb={core.free_gb():.2f}")
    response, error = {}, None
    for attempt in (1, 2):
        try:
            response = core.request_json(opener, "/api/superalpha", payload)
            error = None
            break
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            core.log(f"attempt={attempt} failed {label}: {error}")
            if attempt == 1:
                core.restart_flask()
                opener = core.login()
    after = core.latest_superalpha_id()
    metrics = response.get("combined_metrics") or {}
    row = {
        "time": core.now(), "label": label, "phase": phase, "method": "custom",
        "neutralize": neutralize, "expressions": list(expressions), "weights": list(weights),
        "history_id": after if after != before else None,
        "success": bool(response.get("success")), "metrics": {
            key: metrics.get(key) for key in (
                "pearson_ic", "icir", "fitness", "annual_excess", "sharpe",
                "max_drawdown", "turnover", "win_rate", "n_days",
            )
        }, "pnl_series": metrics.get("pnl_series") or [],
        "metadata": metadata or {}, "error": error or response.get("error"),
    }
    core.append_jsonl(row)
    core.DONE[label] = row
    core.log(f"done {label} success={row['success']} sharpe={core.safe_float(metrics.get('sharpe')):.3f}")
    core.write_status(phase, len(core.DONE))
    return row


def successful_ids(results, minimum=7.0):
    ids = []
    for row in results:
        if row.get("success") and row.get("history_id") and core.safe_float(row.get("metrics", {}).get("sharpe")) > minimum:
            ids.append(row["history_id"])
    return ids


def unique(items):
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def run():
    while not FIRST_FINAL.exists():
        time.sleep(30)
    core.PAUSE_FLAG.write_text(f"{core.now()} afternoon deep extension owns experiment slot\n", encoding="utf-8")
    if not core.url_ok() or core.free_gb() < core.RESUME_FREE_GB:
        core.restart_flask()
    opener = core.login()
    rows, _ = core.write_status("start", len(core.DONE))
    core.log(f"deep extension start history={len(rows)} strict_gt8_lowcorr={len(core.strict_select(rows))}")

    # Weighted leaf-level blends: preserve explicit custom weights in lineage.
    cached = [
        row for row in rows
        if row["type"] == "superalpha" and (BASE / "cache" / f"ew_{row['id']}.npy").exists()
    ]
    grouped = {style: [row for row in cached if row["theme"] == style] for style in core.THEMES}
    styles = [style for style in core.THEMES if grouped[style]]
    weight_profiles = {
        "balanced": {style: 1.0 for style in styles},
        "liquidity_tilt": {style: (2.0 if style == "liquidity" else 1.0) for style in styles},
        "reversal_tilt": {style: (2.0 if style == "reversal" else 1.0) for style in styles},
        "risk_tilt": {style: (2.0 if style == "volatility" else 1.0) for style in styles},
    }
    for offset in range(6):
        # Rotate a two-style basket so leaf-level custom weighting stays
        # bounded in memory without collapsing the cross-style search.
        rotated_styles = [styles[(offset + index) % len(styles)] for index in range(min(2, len(styles)))]
        basket = [grouped[style][offset % len(grouped[style])] for style in rotated_styles]
        expressions = [row["id"] for row in basket]
        for profile, style_weights in weight_profiles.items():
            weights = [style_weights[style] for style in rotated_styles]
            for neutralize in ("none", "market_cap", "beta", "market_cap_beta"):
                call_direct(
                    opener, f"deep_weighted_o{offset}_{profile}_{neutralize}",
                    expressions, weights, neutralize, "weighted_cross_style",
                    {"offset": offset, "profile": profile, "styles": rotated_styles},
                    use_ids=True,
                )

    # True pair/triple nesting over successful measured first-round combos.
    first = json.loads(FIRST_FINAL.read_text(encoding="utf-8"))
    first_ids = successful_ids(first.get("results", []), 7.5)
    rows = core.load_history()
    by_id = {row["id"]: row for row in rows}
    ranked = [by_id[aid] for aid in unique(first_ids) if aid in by_id]
    ranked.sort(key=lambda row: -core.safe_float(row["metrics"].get("sharpe")))
    anchors = core.greedy(ranked, 7, 0.75)
    anchor_ids = core.id_list(anchors)
    nested_results = []
    for size in (2, 3):
        for index, ids in enumerate(itertools.combinations(anchor_ids[:6], size)):
            for neutralize in ("none", "market_cap", "beta", "market_cap_beta"):
                nested_results.append(core.call_combo(
                    opener, f"deep_nest_s{size}_{index}_{neutralize}", ids, "equal",
                    neutralize, "deep_pair_triple_nesting", {"layer": 3, "size": size},
                ))

    # L4 meta nesting: blend the best distinct nested matrices.
    candidate_ids = successful_ids(nested_results, 7.5)
    rows = core.load_history()
    by_id = {row["id"]: row for row in rows}
    ranked = [by_id[aid] for aid in unique(candidate_ids) if aid in by_id]
    ranked.sort(key=lambda row: -core.safe_float(row["metrics"].get("sharpe")))
    meta = core.greedy(ranked, 3, 0.7)
    if len(meta) >= 2:
        for take in range(2, len(meta) + 1):
            for neutralize in ("none", "market_cap", "beta", "market_cap_beta", "market_cap_regression"):
                core.call_combo(
                    opener, f"deep_meta_l4_n{take}_{neutralize}", core.id_list(meta[:take]),
                    "equal", neutralize, "deep_meta_nesting", {"layer": 4, "n_inputs": take},
                )

    rows, strict = core.write_status("complete", len(core.DONE))
    core.atomic_json(core.FINAL, {
        "generated_at": core.now(), "completed_experiments": len(core.DONE),
        "strict_gt8_lowcorr_count": len(strict), "strict_gt8_lowcorr": strict,
        "results": list(core.DONE.values()),
        "note": "Exploratory OOS search; real measurements only. Requires future walk-forward confirmation.",
    })
    core.log(f"deep extension complete experiments={len(core.DONE)} strict_gt8_lowcorr={len(strict)}")


if __name__ == "__main__":
    run()
