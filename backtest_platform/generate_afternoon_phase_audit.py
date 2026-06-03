#!/usr/bin/env python3
"""Summarize all measured afternoon phases without running new experiments."""

import collections
import datetime as dt
import json
import pathlib


BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent
PAPER = ROOT / "paper"
RESULTS = BASE / "experiment_results"
OUTPUT_JSON = PAPER / "afternoon_phase_audit.json"
OUTPUT_TSV = PAPER / "afternoon_phase_audit.tsv"


def percentile(values, q):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def rounded(value):
    return None if value is None else round(float(value), 6)


def main():
    jsonl_paths = [
        RESULTS / "afternoon_extension_experiments.jsonl",
        RESULTS / "afternoon_deep_experiments.jsonl",
        RESULTS / "afternoon_backup_experiments.jsonl",
    ]
    rows = []
    for path in jsonl_paths:
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[row.get("phase", "unlabelled")].append(row)

    phases = []
    for phase, phase_rows in sorted(grouped.items()):
        sharpes = [
            float(row["metrics"]["sharpe"])
            for row in phase_rows
            if row.get("success") and row.get("metrics", {}).get("sharpe") is not None
        ]
        phases.append(
            {
                "phase": phase,
                "rows": len(phase_rows),
                "success_rows": sum(bool(row.get("success")) for row in phase_rows),
                "failed_rows": sum(not row.get("success") for row in phase_rows),
                "sharpe_gt_8_rows": sum(value > 8 for value in sharpes),
                "sharpe_gt_10_rows": sum(value > 10 for value in sharpes),
                "median_sharpe": rounded(percentile(sharpes, 0.5)),
                "p90_sharpe": rounded(percentile(sharpes, 0.9)),
                "maximum_sharpe": rounded(max(sharpes) if sharpes else None),
            }
        )

    neutral_grouped = collections.defaultdict(list)
    for row in rows:
        neutral_grouped[row.get("neutralize", "unspecified")].append(row)
    neutralizations = []
    for neutralize, neutral_rows in sorted(neutral_grouped.items()):
        sharpes = [
            float(row["metrics"]["sharpe"])
            for row in neutral_rows
            if row.get("success") and row.get("metrics", {}).get("sharpe") is not None
        ]
        neutralizations.append(
            {
                "neutralize": neutralize,
                "rows": len(neutral_rows),
                "median_sharpe": rounded(percentile(sharpes, 0.5)),
                "p90_sharpe": rounded(percentile(sharpes, 0.9)),
                "maximum_sharpe": rounded(max(sharpes) if sharpes else None),
            }
        )

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "note": (
            "Descriptive statistics for 950 measured experiments inside the adaptively "
            "inspected 2023 OOS window. These statistics are not untouched validation."
        ),
        "jsonl_sources": [str(path) for path in jsonl_paths],
        "experiment_rows": len(rows),
        "all_rows_success": all(row.get("success") for row in rows),
        "phase_count": len(phases),
        "phases": phases,
        "neutralizations": neutralizations,
        "neutralization_counts": dict(
            sorted(collections.Counter(row.get("neutralize", "unspecified") for row in rows).items())
        ),
        "method_counts": dict(
            sorted(collections.Counter(row.get("method", "unspecified") for row in rows).items())
        ),
    }
    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    header = [
        "phase",
        "rows",
        "success_rows",
        "failed_rows",
        "sharpe_gt_8_rows",
        "sharpe_gt_10_rows",
        "median_sharpe",
        "p90_sharpe",
        "maximum_sharpe",
    ]
    lines = ["\t".join(header)]
    lines.extend("\t".join(str(row[key]) for key in header) for row in phases)
    OUTPUT_TSV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(OUTPUT_JSON),
                "tsv": str(OUTPUT_TSV),
                "experiment_rows": len(rows),
                "phase_count": len(phases),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
