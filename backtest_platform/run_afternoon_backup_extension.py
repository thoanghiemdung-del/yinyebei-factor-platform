#!/usr/bin/env python3
"""Low-memory cached backup audit for the afternoon strict portfolio."""

import itertools
import json
import pathlib
import time

import run_afternoon_extension_experiments as core


BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "experiment_results"
WAIT_FOR = OUT / "afternoon_deep_results.json"
core.LOG = pathlib.Path(r"D:\yyb\logs\afternoon_backup_runner.log")
core.JSONL = OUT / "afternoon_backup_experiments.jsonl"
core.STATUS = OUT / "afternoon_backup_status.json"
core.FINAL = OUT / "afternoon_backup_results.json"
core.DONE = core.completed_rows()


def cached(row):
    return row["type"] == "superalpha" and (BASE / "cache" / f"ew_{row['id']}.npy").exists()


def unique(items):
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def successful_ids(rows, minimum=8.0):
    return unique(
        row.get("history_id")
        for row in rows
        if row.get("success")
        and row.get("history_id")
        and core.safe_float(row.get("metrics", {}).get("sharpe")) > minimum
    )


def portfolio_counts(rows):
    ordered = sorted(
        rows,
        key=lambda row: (-core.safe_float(row["metrics"].get("sharpe")), row["id"]),
    )
    counts = {}
    for threshold in (0.35, 0.40, 0.45, 0.50, 0.55):
        selected = []
        for row in ordered:
            if core.safe_float(row["metrics"].get("sharpe")) <= 8.0:
                continue
            if all(core.abs_corr(row["daily"], old["daily"]) < threshold for old in selected):
                selected.append(row)
        counts[f"{threshold:.2f}"] = len(selected)
    return counts


def call_grid(opener, prefix, combos, neutralizations, phase):
    results = []
    for index, combo in enumerate(combos):
        ids = core.id_list(combo)
        themes = sorted({row["theme"] for row in combo})
        for neutralize in neutralizations:
            results.append(
                core.call_combo(
                    opener,
                    f"{prefix}_{index}_{neutralize}",
                    ids,
                    "equal",
                    neutralize,
                    phase,
                    {"themes": themes, "size": len(ids), "cached_only": True},
                )
            )
    return results


def run():
    while not WAIT_FOR.exists():
        time.sleep(30)
    core.PAUSE_FLAG.write_text(
        f"{core.now()} afternoon backup extension owns experiment slot\n",
        encoding="utf-8",
    )
    if not core.url_ok() or core.free_gb() < core.RESUME_FREE_GB:
        core.restart_flask()
    opener = core.login()
    rows, _ = core.write_status("start", len(core.DONE))
    strict = [row for row in core.strict_select(rows) if cached(row)]
    strict.sort(key=lambda row: -core.safe_float(row["metrics"].get("sharpe")))
    core.log(f"backup extension start history={len(rows)} strict_cached={len(strict)}")

    # Cross-style pairs from the measured strict pool.
    pair_candidates = []
    for left, right in itertools.combinations(strict[:14], 2):
        if left["theme"] == right["theme"]:
            continue
        if core.abs_corr(left["daily"], right["daily"]) >= 0.65:
            continue
        pair_candidates.append((left, right))
    pair_candidates.sort(
        key=lambda combo: (
            core.abs_corr(combo[0]["daily"], combo[1]["daily"]),
            -sum(core.safe_float(row["metrics"].get("sharpe")) for row in combo),
        )
    )
    measured = call_grid(
        opener,
        "backup_pair",
        pair_candidates[:24],
        ("none", "market_cap", "beta", "market_cap_beta"),
        "backup_cross_style_pair",
    )

    # Distinct-theme triples add a backup hierarchy without broad raw-leaf parsing.
    triple_candidates = []
    for combo in itertools.combinations(strict[:14], 3):
        if len({row["theme"] for row in combo}) < 3:
            continue
        if max(
            core.abs_corr(left["daily"], right["daily"])
            for left, right in itertools.combinations(combo, 2)
        ) >= 0.65:
            continue
        triple_candidates.append(combo)
    triple_candidates.sort(
        key=lambda combo: (
            max(
                core.abs_corr(left["daily"], right["daily"])
                for left, right in itertools.combinations(combo, 2)
            ),
            -sum(core.safe_float(row["metrics"].get("sharpe")) for row in combo),
        )
    )
    measured.extend(
        call_grid(
            opener,
            "backup_triple",
            triple_candidates[:18],
            ("none", "market_cap", "beta", "market_cap_beta"),
            "backup_cross_style_triple",
        )
    )

    # Small L4 backup: only cached matrices from the strongest newly measured rows.
    candidate_ids = successful_ids(measured, 9.5)
    rows = core.load_history()
    by_id = {row["id"]: row for row in rows}
    ranked = [by_id[aid] for aid in candidate_ids if aid in by_id and cached(by_id[aid])]
    ranked.sort(key=lambda row: -core.safe_float(row["metrics"].get("sharpe")))
    meta = core.greedy(ranked, 3, 0.72)
    if len(meta) >= 2:
        for take in range(2, len(meta) + 1):
            for neutralize in ("none", "market_cap", "beta", "market_cap_beta", "market_cap_regression"):
                core.call_combo(
                    opener,
                    f"backup_meta_l4_n{take}_{neutralize}",
                    core.id_list(meta[:take]),
                    "equal",
                    neutralize,
                    "backup_meta_nesting",
                    {"layer": 4, "n_inputs": take, "cached_only": True},
                )

    rows, strict_manifest = core.write_status("complete", len(core.DONE))
    core.atomic_json(
        core.FINAL,
        {
            "generated_at": core.now(),
            "completed_experiments": len(core.DONE),
            "strict_gt8_lowcorr_count": len(strict_manifest),
            "strict_gt8_lowcorr": strict_manifest,
            "portfolio_counts_by_corr_threshold": portfolio_counts(rows),
            "results": list(core.DONE.values()),
            "note": "Low-memory cached backup audit; exploratory OOS measurements only.",
        },
    )
    core.log(
        f"backup extension complete experiments={len(core.DONE)} "
        f"strict_gt8_lowcorr={len(strict_manifest)}"
    )


if __name__ == "__main__":
    run()
