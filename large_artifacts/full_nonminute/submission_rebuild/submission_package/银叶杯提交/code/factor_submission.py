#!/usr/bin/env python3
"""Direct-submission implementation for the Silver Leaf Cup factors.

Inputs
------
minute_days:
    Iterable of daily dictionaries. Every dictionary contains aligned matrices
    OPEN, HIGH, LOW, CLOSE, VOLUME, AMOUNT and NUMBER with shape
    (minute_bars, stocks). The stock order is fixed across dates.
daily_close:
    Adjusted daily close matrix with shape (dates, stocks). It is only used by
    factor_08 for the allowed five-day basic-market return.
universe_mask:
    Boolean matrix with shape (dates, stocks). It must already exclude ST,
    *ST and stocks listed for fewer than 120 days.

Output
------
Ordered mapping factor_01 ... factor_10. Each value is a (dates, stocks)
float32 matrix standardized by daily 1%/99% winsorization and z-score.

The implementation uses no future data and no news or fundamental fields.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


EPS = 1e-10


FACTOR_DESCRIPTIONS = OrderedDict([
    ("factor_01", "Large-ticket execution pressure"),
    ("factor_02", "Intraday reversal and trade-count timing"),
    ("factor_03", "VWAP execution-price pressure"),
    ("factor_04", "Trade-count concentration"),
    ("factor_05", "Closing pressure and volume-profile reversal"),
    ("factor_06", "Relative minute-Amihud liquidity shock"),
    ("factor_07", "Relative VPIN order-flow toxicity"),
    ("factor_08", "Intraday and five-day trend confirmation"),
    ("factor_09", "Minute-Amihud price impact"),
    ("factor_10", "Volume-count concentration gap"),
])


# Every final factor is a one-level weighted sum of standardized leaves.
# There is no recursive composite or hidden UUID lookup.
FINAL_SPECS = OrderedDict([
    ("factor_01", {
        "F6_4_large_trade_ratio": -0.25,
        "F_COMBO_8_large_trade": -0.25,
        "N5_log_avg_ticket": -0.25,
        "N6_large_ticket_amount_ratio": 0.25,
    }),
    ("factor_02", {
        "F1_1_first30_mom": -1 / 6,
        "F1_2_last30_mom": -1 / 6,
        "F1_3_intraday_mom": -1 / 6,
        "N1_count_weighted_time": 0.10,
        "N2_open_count_ratio": -0.10,
        "N3_close_count_ratio": -0.10,
        "N4_count_hhi": -0.10,
        "N7_count_price_corr": -0.10,
    }),
    ("factor_03", {
        "F4_1_close_vs_vwap": -1 / 3,
        "F4_2_vwap_trend": -1 / 3,
        "F_COMBO_9_smart_money_vwap": -1 / 3,
    }),
    ("factor_04", {"N4_count_hhi": -1.0}),
    ("factor_05", {
        "F1_2_last30_mom": -0.10,
        "F5_1_volume_hhi": -0.125,
        "F5_2_open_vol_ratio": -0.125,
        "F5_3_close_vol_ratio": -0.225,
        "F_COMBO_7_wat": -0.125,
        "N3_close_count_ratio": -0.10,
        "N8_tail_ticket_reversal": 0.10,
    }),
    ("factor_06", {"F_COMBO_4_amihud_hybrid": 1.0}),
    ("factor_07", {"F_COMBO_2_vpin_informed": -1.0}),
    ("factor_08", {"G2_1_intraday_ret5d": -1.0}),
    ("factor_09", {"F6_2_amihud_min": 1.0}),
    ("factor_10", {
        "F5_1_volume_hhi": 0.50,
        "N4_count_hhi": -0.50,
    }),
])


def safe_ratio(numerator: np.ndarray, denominator: np.ndarray | float) -> np.ndarray:
    return numerator / np.maximum(denominator, EPS)


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """NaN-aware trailing mean, including the current day."""
    result = np.full_like(values, np.nan, dtype=np.float32)
    for t in range(window - 1, len(values)):
        result[t] = np.nanmean(values[t - window + 1:t + 1], axis=0)
    return result


def cs_winsor_zscore(values: np.ndarray, universe: np.ndarray | None = None) -> np.ndarray:
    """Daily cross-sectional 1%/99% winsorization followed by z-score."""
    values = np.asarray(values, dtype=np.float64)
    one_row = values.ndim == 1
    matrix = values.reshape(1, -1) if one_row else values
    if universe is None:
        masks = np.ones(matrix.shape, dtype=bool)
    else:
        masks = np.asarray(universe, dtype=bool).reshape(matrix.shape)
    result = np.full(matrix.shape, np.nan, dtype=np.float32)
    for t in range(len(matrix)):
        valid = masks[t] & np.isfinite(matrix[t])
        if valid.sum() < 30:
            continue
        row = matrix[t, valid]
        lo, hi = np.nanpercentile(row, [1, 99])
        row = np.clip(row, lo, hi)
        std = np.nanstd(row)
        if std <= EPS:
            continue
        result[t, valid] = ((row - np.nanmean(row)) / std).astype(np.float32)
    return result[0] if one_row else result


def vectorized_corr(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    valid = np.isfinite(x) & np.isfinite(y) & (y > 0)
    count = valid.sum(axis=0)
    xx = np.where(valid, x, 0.0)
    yy = np.where(valid, y, 0.0)
    mx = safe_ratio(xx.sum(axis=0), count)
    my = safe_ratio(yy.sum(axis=0), count)
    dx = np.where(valid, x - mx, 0.0)
    dy = np.where(valid, y - my, 0.0)
    corr = safe_ratio((dx * dy).sum(axis=0), np.sqrt((dx * dx).sum(axis=0) * (dy * dy).sum(axis=0)))
    corr[(count < 30) | ~np.isfinite(corr)] = np.nan
    return corr


def compute_daily_leaves(day: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Compute all minute leaves needed by the final ten factors for one date."""
    # Keep the source precision: the official minute matrices are float32.
    # This also reproduces the frozen research matrices for tiny liquidity
    # ratios whose trailing normalization can amplify rounding differences.
    o = np.asarray(day["OPEN"], dtype=np.float32)
    h = np.asarray(day["HIGH"], dtype=np.float32)
    l = np.asarray(day["LOW"], dtype=np.float32)
    c = np.asarray(day["CLOSE"], dtype=np.float32)
    v = np.asarray(day["VOLUME"], dtype=np.float32)
    amount = np.asarray(day["AMOUNT"], dtype=np.float32)
    number = np.asarray(day["NUMBER"], dtype=np.float32)
    n_bars = len(c)
    mid = n_bars // 2
    first = min(30, n_bars)
    last = max(0, n_bars - 30)

    min_ret = np.full_like(c, np.nan)
    min_ret[1:] = safe_ratio(c[1:] - c[:-1], c[:-1])
    total_v = np.nansum(v, axis=0)
    total_amount = np.nansum(amount, axis=0)
    total_number = np.nansum(number, axis=0)
    volume_share = safe_ratio(v, total_v)
    number_share = safe_ratio(number, total_number)
    typical_price = (h + l + c) / 3
    vwap = safe_ratio(np.nansum(typical_price * v, axis=0), total_v)
    vwap_am = safe_ratio(np.nansum(typical_price[:mid] * v[:mid], axis=0), np.nansum(v[:mid], axis=0))
    vwap_pm = safe_ratio(np.nansum(typical_price[mid:] * v[mid:], axis=0), np.nansum(v[mid:], axis=0))
    med_vol = np.nanmedian(v, axis=0)
    bar_direction = np.sign(min_ret)
    bar_direction[0] = np.sign(c[0] - o[0])
    day_avg_ticket = safe_ratio(total_amount, total_number)
    bar_ticket = safe_ratio(amount, number)
    med_ticket = np.nanmedian(np.where(number > 0, bar_ticket, np.nan), axis=0)
    last30_ret = safe_ratio(c[-1] - o[last], o[last])
    last30_avg_ticket = safe_ratio(np.nansum(amount[last:], axis=0), np.nansum(number[last:], axis=0))
    idx = np.arange(n_bars, dtype=np.float64).reshape(-1, 1)

    result = {
        "F1_1_first30_mom": safe_ratio(c[first - 1] - o[0], o[0]),
        "F1_2_last30_mom": last30_ret,
        "F1_3_intraday_mom": safe_ratio(c[-1] - o[0], o[0]),
        "F4_1_close_vs_vwap": safe_ratio(c[-1] - vwap, vwap),
        "F4_2_vwap_trend": safe_ratio(vwap_pm - vwap_am, vwap_am),
        "F5_1_volume_hhi": np.nansum(volume_share ** 2, axis=0),
        "F5_2_open_vol_ratio": safe_ratio(np.nansum(v[:6], axis=0), total_v),
        "F5_3_close_vol_ratio": safe_ratio(np.nansum(v[last:], axis=0), total_v),
        "F6_2_amihud_min": np.nanmean(np.clip(safe_ratio(np.abs(min_ret), np.maximum(amount, 1000)), 0, 0.01), axis=0),
        "F6_3_vpin": safe_ratio(np.nansum(v * np.abs(min_ret), axis=0), np.sqrt(np.nansum(v ** 2, axis=0))),
        "F6_4_large_trade_ratio": safe_ratio(np.nansum(v * (v > 2 * med_vol), axis=0), total_v),
        "N1_count_weighted_time": safe_ratio(np.nansum(idx * number, axis=0), total_number) / max(n_bars - 1, 1),
        "N2_open_count_ratio": safe_ratio(np.nansum(number[:first], axis=0), total_number),
        "N3_close_count_ratio": safe_ratio(np.nansum(number[last:], axis=0), total_number),
        "N4_count_hhi": np.nansum(number_share ** 2, axis=0),
        "N5_log_avg_ticket": np.log1p(np.maximum(day_avg_ticket, 0)),
        "N6_large_ticket_amount_ratio": safe_ratio(np.nansum(np.where(bar_ticket > 2 * med_ticket, amount, 0), axis=0), total_amount),
        "N7_count_price_corr": vectorized_corr(min_ret, number),
        "N8_tail_ticket_reversal": -last30_ret * safe_ratio(last30_avg_ticket, day_avg_ticket + EPS),
    }
    weighted_avg_time = np.nansum(idx * volume_share, axis=0) / n_bars
    smart_money_vol = safe_ratio(np.nansum(v * (bar_direction > 0), axis=0), total_v)
    result["F_COMBO_7_wat"] = (0.5 - weighted_avg_time) * np.sign(result["F1_3_intraday_mom"])
    result["F_COMBO_8_large_trade"] = result["F6_4_large_trade_ratio"] * np.sign(result["F1_3_intraday_mom"])
    result["F_COMBO_9_smart_money_vwap"] = smart_money_vol * result["F4_1_close_vs_vwap"]
    number_invalid = total_number <= 0
    for name in (
        "N1_count_weighted_time",
        "N2_open_count_ratio",
        "N3_close_count_ratio",
        "N4_count_hhi",
        "N7_count_price_corr",
    ):
        result[name][number_invalid] = np.nan
    ticket_invalid = number_invalid | (total_amount <= 0)
    for name in ("N5_log_avg_ticket", "N6_large_ticket_amount_ratio", "N8_tail_ticket_reversal"):
        result[name][ticket_invalid] = np.nan
    return result


def compute_leaf_matrices(
    minute_days: Iterable[Mapping[str, np.ndarray]],
    daily_close: np.ndarray,
) -> dict[str, np.ndarray]:
    """Compute daily leaf matrices and trailing minute composites."""
    daily_close = np.asarray(daily_close, dtype=np.float64)
    rows: dict[str, list[np.ndarray]] = {}
    day_count = 0
    for day in minute_days:
        for name, values in compute_daily_leaves(day).items():
            rows.setdefault(name, []).append(np.asarray(values, dtype=np.float32))
        day_count += 1
    if day_count != len(daily_close):
        raise ValueError("minute_days and daily_close must have the same number of dates")
    leaves = {name: np.asarray(values, dtype=np.float32) for name, values in rows.items()}
    leaves["F_COMBO_2_vpin_informed"] = leaves["F6_3_vpin"] - rolling_mean(leaves["F6_3_vpin"], 20)
    leaves["F_COMBO_4_amihud_hybrid"] = leaves["F6_2_amihud_min"] / (rolling_mean(leaves["F6_2_amihud_min"], 20) + EPS) - 1
    ret5 = np.full_like(daily_close, np.nan)
    ret5[5:] = safe_ratio(daily_close[5:] - daily_close[:-5], daily_close[:-5])
    same_sign = np.sign(leaves["F1_3_intraday_mom"]) == np.sign(ret5)
    leaves["G2_1_intraday_ret5d"] = np.where(same_sign, np.abs(leaves["F1_3_intraday_mom"] * ret5), np.nan)
    return leaves


def compute_final_factors(
    minute_days: Iterable[Mapping[str, np.ndarray]],
    daily_close: np.ndarray,
    universe_mask: np.ndarray,
) -> OrderedDict[str, np.ndarray]:
    """Return the ten standardized final factor matrices."""
    universe_mask = np.asarray(universe_mask, dtype=bool)
    leaves = compute_leaf_matrices(minute_days, daily_close)
    z_leaves = {name: cs_winsor_zscore(values, universe_mask) for name, values in leaves.items()}
    result = OrderedDict()
    for factor_key, terms in FINAL_SPECS.items():
        matrix = np.zeros(universe_mask.shape, dtype=np.float64)
        valid_any = np.zeros(universe_mask.shape, dtype=bool)
        for leaf, weight in terms.items():
            values = z_leaves[leaf]
            valid = np.isfinite(values)
            matrix[valid] += weight * values[valid]
            valid_any |= valid
        matrix[~valid_any] = np.nan
        result[factor_key] = cs_winsor_zscore(matrix, universe_mask)
    return result


def save_factor_values(
    output: str | Path,
    dates: np.ndarray,
    stock_codes: np.ndarray,
    factors: Mapping[str, np.ndarray],
) -> None:
    """Write standardized factors in the submission matrix format."""
    np.savez_compressed(
        Path(output),
        dates=np.asarray(dates),
        stock_codes=np.asarray(stock_codes),
        **{key: np.asarray(values, dtype=np.float32) for key, values in factors.items()},
    )
