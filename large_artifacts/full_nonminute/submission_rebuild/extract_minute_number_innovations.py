#!/usr/bin/env python3
"""Extract bounded-memory minute factors that use transaction-count data."""

from __future__ import annotations

import gc
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np


ROOT = Path(r"D:\yyb")
OUT = ROOT / "submission_rebuild" / "innovations"
OUT.mkdir(parents=True, exist_ok=True)
MODEL = next(ROOT.rglob("all_factors.pkl")).parent
sys.path.insert(0, str(MODEL))

from data_pipeline import DataPipeline  # noqa: E402


DEFINITIONS = {
    "N1_count_weighted_time": "sum(minute_index * MINUTE_NUMBER) / sum(MINUTE_NUMBER) / 241",
    "N2_open_count_ratio": "sum(first_30min MINUTE_NUMBER) / sum(all_day MINUTE_NUMBER)",
    "N3_close_count_ratio": "sum(last_30min MINUTE_NUMBER) / sum(all_day MINUTE_NUMBER)",
    "N4_count_hhi": "sum((MINUTE_NUMBER / sum(all_day MINUTE_NUMBER)) ** 2)",
    "N5_log_avg_ticket": "log1p(sum(MINUTE_AMOUNT) / sum(MINUTE_NUMBER))",
    "N6_large_ticket_amount_ratio": "sum(MINUTE_AMOUNT where avg_ticket_per_bar > 2 * median_bar_ticket) / sum(MINUTE_AMOUNT)",
    "N7_count_price_corr": "corr(minute_close_return, MINUTE_NUMBER) across the trading day",
    "N8_tail_ticket_reversal": "-last_30min_return * (last_30min_avg_ticket / all_day_avg_ticket)",
}


def open_outputs(n_dates: int, n_stocks: int):
    outputs = {}
    for name in DEFINITIONS:
        path = OUT / f"{name}.npy"
        mm = np.lib.format.open_memmap(path, mode="w+", dtype=np.float32, shape=(n_dates, n_stocks))
        mm[:] = np.nan
        outputs[name] = mm
    return outputs


def safe_ratio(num, den):
    return num / np.maximum(den, 1e-10)


def vectorized_corr(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    valid = np.isfinite(x) & np.isfinite(y) & (y > 0)
    count = valid.sum(axis=0)
    xx = np.where(valid, x, 0.0)
    yy = np.where(valid, y, 0.0)
    mx = safe_ratio(xx.sum(axis=0), count)
    my = safe_ratio(yy.sum(axis=0), count)
    dx = np.where(valid, x - mx, 0.0)
    dy = np.where(valid, y - my, 0.0)
    cov = safe_ratio((dx * dy).sum(axis=0), count)
    vx = safe_ratio((dx * dx).sum(axis=0), count)
    vy = safe_ratio((dy * dy).sum(axis=0), count)
    corr = safe_ratio(cov, np.sqrt(vx * vy))
    corr[(count < 30) | ~np.isfinite(corr)] = np.nan
    return corr


def extract_day(aligned: dict[str, np.ndarray], outputs, t: int):
    o = aligned["OPEN"]
    c = aligned["CLOSE"]
    amount = np.nan_to_num(aligned["AMOUNT"], nan=0.0)
    number = np.nan_to_num(aligned["NUMBER"], nan=0.0)
    n_bars = c.shape[0]
    first = min(30, n_bars)
    last = max(0, n_bars - 30)
    eps = 1e-10

    total_number = number.sum(axis=0)
    total_amount = amount.sum(axis=0)
    day_avg_ticket = safe_ratio(total_amount, total_number)

    bar_ticket = safe_ratio(amount, number)
    valid_ticket = number > 0
    bar_ticket_for_median = np.where(valid_ticket, bar_ticket, np.nan)
    median_ticket = np.nanmedian(bar_ticket_for_median, axis=0)

    idx = np.arange(n_bars, dtype=np.float32).reshape(-1, 1)
    number_share = safe_ratio(number, total_number)
    min_ret = np.full_like(c, np.nan)
    min_ret[1:] = safe_ratio(c[1:] - c[:-1], c[:-1])

    last_ret = safe_ratio(c[-1] - o[last], o[last])
    last_avg_ticket = safe_ratio(amount[last:].sum(axis=0), number[last:].sum(axis=0))

    outputs["N1_count_weighted_time"][t] = safe_ratio((idx * number).sum(axis=0), total_number) / max(n_bars - 1, 1)
    outputs["N2_open_count_ratio"][t] = safe_ratio(number[:first].sum(axis=0), total_number)
    outputs["N3_close_count_ratio"][t] = safe_ratio(number[last:].sum(axis=0), total_number)
    outputs["N4_count_hhi"][t] = (number_share * number_share).sum(axis=0)
    outputs["N5_log_avg_ticket"][t] = np.log1p(np.maximum(day_avg_ticket, 0.0))
    outputs["N6_large_ticket_amount_ratio"][t] = safe_ratio(
        np.where(bar_ticket > 2 * median_ticket, amount, 0.0).sum(axis=0),
        total_amount,
    )
    outputs["N7_count_price_corr"][t] = vectorized_corr(min_ret, number)
    outputs["N8_tail_ticket_reversal"][t] = -last_ret * safe_ratio(last_avg_ticket, day_avg_ticket + eps)

    invalid = total_number <= 0
    for values in outputs.values():
        values[t, invalid] = np.nan


def main():
    print("Loading daily alignment metadata...")
    pipeline = DataPipeline(ROOT)
    outputs = open_outputs(pipeline.n_dates, pipeline.n_stocks)
    minute_dates = pipeline.get_minute_dates()
    processed = 0
    failures = []

    for date_str in minute_dates:
        iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        if iso not in pipeline.date_to_idx:
            continue
        t = pipeline.date_to_idx[iso]
        try:
            aligned = pipeline.align_minute_to_daily(pipeline.load_minute_day(date_str), t)
            extract_day(aligned, outputs, t)
            processed += 1
        except Exception as exc:
            failures.append({"date": date_str, "error": str(exc)})
        if processed and processed % 100 == 0:
            print(f"Processed {processed}/{len(minute_dates)} minute days")
            for values in outputs.values():
                values.flush()
            gc.collect()

    for values in outputs.values():
        values.flush()

    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "processed_days": processed,
        "failed_days": failures,
        "shape": [pipeline.n_dates, pipeline.n_stocks],
        "definitions": DEFINITIONS,
        "source_fields": ["MINUTE_OPEN", "MINUTE_CLOSE", "MINUTE_AMOUNT", "MINUTE_NUMBER"],
        "future_data_used": False,
    }
    (OUT / "number_innovations_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
