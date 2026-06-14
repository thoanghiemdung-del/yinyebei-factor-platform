#!/usr/bin/env python3
"""Run a dependency-light interface smoke test for factor_submission.py."""

from __future__ import annotations

import json

import numpy as np

from factor_submission import compute_final_factors


def synthetic_days(n_dates=25, n_bars=242, n_stocks=80):
    rng = np.random.default_rng(20260602)
    price = np.linspace(8.0, 35.0, n_stocks)
    days = []
    daily_close = []
    for _ in range(n_dates):
        open_price = np.maximum(price[None, :] * (1 + rng.normal(0, 0.0008, (n_bars, n_stocks)).cumsum(axis=0)), 0.1)
        close_price = open_price * (1 + rng.normal(0, 0.0005, (n_bars, n_stocks)))
        high_price = np.maximum(open_price, close_price) * (1 + np.abs(rng.normal(0, 0.0003, (n_bars, n_stocks))))
        low_price = np.minimum(open_price, close_price) * (1 - np.abs(rng.normal(0, 0.0003, (n_bars, n_stocks))))
        volume = rng.lognormal(8, 0.9, (n_bars, n_stocks)).astype(np.float32)
        amount = (volume * close_price).astype(np.float32)
        number = np.maximum(1, (volume / rng.uniform(30, 300, (n_bars, n_stocks))).astype(np.float32))
        days.append({
            "OPEN": open_price.astype(np.float32),
            "HIGH": high_price.astype(np.float32),
            "LOW": low_price.astype(np.float32),
            "CLOSE": close_price.astype(np.float32),
            "VOLUME": volume,
            "AMOUNT": amount,
            "NUMBER": number,
        })
        price = close_price[-1]
        daily_close.append(price)
    return days, np.asarray(daily_close, dtype=np.float32)


def main():
    days, daily_close = synthetic_days()
    universe = np.ones(daily_close.shape, dtype=bool)
    factors = compute_final_factors(iter(days), daily_close, universe)
    assert list(factors) == [f"factor_{index:02d}" for index in range(1, 11)]
    for key, matrix in factors.items():
        assert matrix.shape == daily_close.shape, (key, matrix.shape)
        assert matrix.dtype == np.float32, (key, matrix.dtype)
        finite_rows = np.isfinite(matrix).sum(axis=1) >= 30
        assert finite_rows.any(), key
        means = np.nanmean(matrix[finite_rows], axis=1)
        stds = np.nanstd(matrix[finite_rows], axis=1)
        assert np.max(np.abs(means)) < 1e-5, (key, float(np.max(np.abs(means))))
        assert np.max(np.abs(stds - 1)) < 1e-5, (key, float(np.max(np.abs(stds - 1))))
    print(json.dumps({
        "status": "PASS",
        "factor_count": len(factors),
        "shape_per_factor": list(daily_close.shape),
        "interface": "compute_final_factors(iter(minute_days), daily_close, universe_mask)",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

