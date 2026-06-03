#!/usr/bin/env python3
"""Freeze the next untouched-holdout protocol without running any backtest."""

import datetime as dt
import hashlib
import json
import pathlib


BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent
PAPER = ROOT / "paper"
MANIFEST = PAPER / "afternoon_final_factors.json"
OUTPUT_JSON = PAPER / "next_holdout_preregistration.json"
OUTPUT_MD = PAPER / "next_holdout_preregistration.md"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    factors = manifest["factors"]
    generated = dt.datetime.now().isoformat(timespec="seconds")
    report = {
        "generated_at": generated,
        "status": "preregistered_not_executed",
        "note": (
            "This protocol freezes a future untouched-holdout evaluation. It does not "
            "contain new backtest measurements and must not be represented as validation."
        ),
        "source_manifest": str(MANIFEST),
        "source_manifest_sha256": sha256(MANIFEST),
        "source_evidence": {
            "inspected_construction_window": "2020-2022 IS",
            "adaptively_inspected_exploratory_window": "2023 OOS",
            "recorded_exploratory_measurements": 950,
            "strict_pool_size_on_inspected_window": manifest["strict_available_count"],
            "displayed_frozen_factor_count": len(factors),
        },
        "future_holdout_rules": [
            "Use a consecutive period that is disjoint from 2020-2023.",
            "Do not alter expressions, weights, residualization, nesting, or factor order after opening holdout results.",
            "Record all factor-level and portfolio-level outputs before reviewing any pass/fail decision.",
            "Do not replace a failed factor using the untouched holdout.",
            "Keep the workflow local and do not submit any external Alpha.",
        ],
        "primary_report": [
            "Report every frozen factor Sharpe, IC, turnover, cumulative PnL, and maximum drawdown.",
            "Report the equal-weight ten-factor portfolio Sharpe and cumulative PnL.",
            "Report the full pairwise absolute daily-PnL correlation matrix.",
            "Report whether the full-period maximum pairwise absolute daily-PnL correlation is below 0.5.",
        ],
        "required_robustness": [
            "Sequential half-year, quarter, and month diagnostics without retuning.",
            "Cost scenarios at 0, 5, 10, and 20 basis points per one-way traded notional.",
            "Turnover, liquidity bucket, and capacity diagnostics.",
            "Block-bootstrap confidence intervals for factor and portfolio Sharpe.",
            "Deflated Sharpe ratio and a multiple-testing correction over the frozen exploratory universe.",
            "White reality check and Hansen superior-predictive-ability test against an atomic-only benchmark.",
            "Atomic-only, residualized, cross-style, pair/triple nesting, and L4 meta-nesting comparison tables.",
        ],
        "frozen_displayed_factors": [
            {
                "rank": row["rank"],
                "id": row["id"],
                "expression": row["expression"],
                "theme": row["theme"],
                "inspected_2023_oos_sharpe": row["sharpe"],
                "inspected_2023_max_corr_to_selected": row["max_corr_to_selected"],
            }
            for row in factors
        ],
    }
    OUTPUT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    factor_rows = "\n".join(
        f"| {row['rank']} | `{row['id']}` | {row['theme']} | "
        f"{row['sharpe']:.3f} | {row['max_corr_to_selected']:.6f} |"
        for row in factors
    )
    markdown = f"""# Next Untouched-Holdout Preregistration

Generated: `{generated}`

Status: `preregistered_not_executed`

This document freezes the next evaluation protocol. It does not contain new holdout
measurements. The 2023 OOS window was already inspected adaptively and cannot serve as
external validation.

## Frozen Portfolio

| Rank | ID | Theme | Inspected 2023 OOS Sharpe | Max corr. to selected |
|---:|---|---|---:|---:|
{factor_rows}

## Untouched-Holdout Rules

1. Use a consecutive period disjoint from 2020-2023.
2. Open results only after recording all frozen expressions without retuning.
3. Do not replace failed factors using the untouched holdout.
4. Report raw, cost-adjusted, capacity, block-bootstrap, and multiple-testing results.
5. Keep the workflow local and do not submit any external Alpha.

The machine-readable protocol is `{OUTPUT_JSON}`.
"""
    OUTPUT_MD.write_text(markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(OUTPUT_JSON),
                "markdown": str(OUTPUT_MD),
                "factor_count": len(factors),
                "source_manifest_sha256": report["source_manifest_sha256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
