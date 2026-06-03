#!/usr/bin/env python3
"""Generate descriptive 2023 OOS regime splits for the final displayed portfolio."""

import csv
import json
import math
import pathlib
import sqlite3

import numpy as np


BASE = pathlib.Path(__file__).resolve().parent
PAPER = BASE.parent / "paper"
DB = BASE / "backtest.db"
MANIFEST = PAPER / "afternoon_final_factors.json"
OUTPUT = PAPER / "afternoon_regime_audit.json"
TSV = PAPER / "afternoon_regime_audit.tsv"


def safe_sharpe(values):
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 5 or np.std(arr) <= 1e-12:
        return 0.0
    return float(np.mean(arr) / np.std(arr) * math.sqrt(252))


def max_abs_corr(matrix):
    values = []
    for left in range(len(matrix)):
        for right in range(left):
            a = matrix[left]
            b = matrix[right]
            valid = np.isfinite(a) & np.isfinite(b)
            if valid.sum() < 5 or np.std(a[valid]) <= 1e-12 or np.std(b[valid]) <= 1e-12:
                continue
            values.append(abs(float(np.corrcoef(a[valid], b[valid])[0, 1])))
    return max(values) if values else 0.0


def segment(name, matrix, start, stop):
    sliced = np.asarray([values[start:stop] for values in matrix], dtype=float)
    portfolio = np.nanmean(sliced, axis=0)
    return {
        "segment": name,
        "start_daily_index": int(start),
        "stop_daily_index_exclusive": int(stop),
        "n_days": int(stop - start),
        "equal_weight_portfolio_sharpe": round(safe_sharpe(portfolio), 6),
        "equal_weight_cumulative_pnl": round(float(np.nansum(portfolio)), 6),
        "equal_weight_positive_day_ratio": round(float(np.nanmean(portfolio > 0)), 6),
        "maximum_pairwise_abs_daily_pnl_corr": round(max_abs_corr(sliced), 6),
    }


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    ids = [row["id"] for row in manifest["factors"]]
    connection = sqlite3.connect(DB)
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(
        f"SELECT id, pnl_json FROM alpha_history WHERE id IN ({placeholders})",
        ids,
    ).fetchall()
    connection.close()
    pnl_by_id = {aid: json.loads(raw) for aid, raw in rows}
    missing = [aid for aid in ids if aid not in pnl_by_id]
    if missing:
        raise RuntimeError(f"missing pnl_json for {missing}")
    daily = [np.diff(np.asarray(pnl_by_id[aid], dtype=float)) for aid in ids]
    n_days = min(len(values) for values in daily)
    daily = [values[-n_days:] for values in daily]
    q1 = n_days // 4
    q2 = n_days // 2
    q3 = (3 * n_days) // 4
    segments = [
        segment("Full 2023 OOS", daily, 0, n_days),
        segment("H1 sequential", daily, 0, q2),
        segment("H2 sequential", daily, q2, n_days),
        segment("Q1 sequential", daily, 0, q1),
        segment("Q2 sequential", daily, q1, q2),
        segment("Q3 sequential", daily, q2, q3),
        segment("Q4 sequential", daily, q3, n_days),
    ]
    factor_splits = []
    for aid, values in zip(ids, daily):
        factor_splits.append(
            {
                "id": aid,
                "full_sharpe": round(safe_sharpe(values), 6),
                "h1_sharpe": round(safe_sharpe(values[:q2]), 6),
                "h2_sharpe": round(safe_sharpe(values[q2:]), 6),
                "positive_halves": int(safe_sharpe(values[:q2]) > 0) + int(safe_sharpe(values[q2:]) > 0),
            }
        )
    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "note": (
            "Descriptive sequential splits within the adaptively inspected 2023 OOS window. "
            "These are not an untouched holdout and must not support an external performance claim."
        ),
        "displayed_factor_ids": ids,
        "segments": segments,
        "factor_half_splits": factor_splits,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(segments[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(segments)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
