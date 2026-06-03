#!/usr/bin/env python3
"""Greedy PnL-correlation dedup for minute-only alpha_history rows."""
import argparse
import json
import math
import sqlite3
from itertools import combinations

import numpy as np
from yyb_factor_policy import eligible_expr

DB = r"D:\yyb\backtest_platform\backtest.db"

def score(metrics: dict) -> float:
    ic = metrics.get('pearson_ic') or 0.0
    sharpe = metrics.get('sharpe') or 0.0
    fitness = metrics.get('fitness') or 0.0
    return abs(float(ic)) * max(abs(float(sharpe)), 1e-6) + 0.01 * abs(float(fitness))


def daily_from_cum(pnl_json: str) -> np.ndarray:
    try:
        cum = np.array(json.loads(pnl_json or '[]'), dtype=float)
    except Exception:
        return np.array([], dtype=float)
    cum = cum[np.isfinite(cum)]
    if len(cum) <= 2:
        return np.array([], dtype=float)
    return np.diff(cum)


def corr(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    if n < 30:
        return float('nan')
    x = a[-n:]
    y = b[-n:]
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 30:
        return float('nan')
    x = x[m]
    y = y[m]
    if np.nanstd(x) <= 1e-12 or np.nanstd(y) <= 1e-12:
        return float('nan')
    return float(np.corrcoef(x, y)[0, 1])


def load_rows():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT rowid, id, expression, metrics_json, pnl_json FROM alpha_history "
        "WHERE ABS(CAST(json_extract(metrics_json,'$.pearson_ic') AS REAL)) > 0.01 "
        "AND pnl_json IS NOT NULL AND length(pnl_json) > 5"
    ).fetchall()
    con.close()

    out = []
    for row in rows:
        expr = row['expression']
        if not eligible_expr(expr):
            continue
        try:
            metrics = json.loads(row['metrics_json'] or '{}')
        except Exception:
            metrics = {}
        daily = daily_from_cum(row['pnl_json'])
        if len(daily) < 30:
            continue
        out.append({
            'rowid': row['rowid'],
            'id': row['id'],
            'expression': expr,
            'metrics': metrics,
            'daily': daily,
            'score': score(metrics),
            'max_corr': 0.0,
        })
    return out


def greedy_dedup(rows, threshold: float):
    removed = set()
    pairs = []
    for i, j in combinations(range(len(rows)), 2):
        c = corr(rows[i]['daily'], rows[j]['daily'])
        if math.isnan(c):
            continue
        ac = abs(c)
        rows[i]['max_corr'] = max(rows[i]['max_corr'], ac)
        rows[j]['max_corr'] = max(rows[j]['max_corr'], ac)
        if ac > threshold:
            pairs.append((ac, i, j))

    pairs.sort(reverse=True)
    decisions = []
    for ac, i, j in pairs:
        if i in removed or j in removed:
            continue
        loser = i if rows[i]['score'] < rows[j]['score'] else j
        winner = j if loser == i else i
        removed.add(loser)
        decisions.append((ac, rows[winner], rows[loser]))
    kept = [r for idx, r in enumerate(rows) if idx not in removed]
    return kept, [rows[i] for i in sorted(removed)], decisions


def max_pair_corr(rows) -> float:
    best = 0.0
    for i, j in combinations(range(len(rows)), 2):
        c = corr(rows[i]['daily'], rows[j]['daily'])
        if not math.isnan(c):
            best = max(best, abs(c))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('threshold', nargs='?', type=float, default=0.7)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    rows = load_rows()
    kept, removed, decisions = greedy_dedup(rows, args.threshold)
    print(f"eligible_qualified={len(rows)} kept={len(kept)} remove={len(removed)} threshold={args.threshold}")
    if kept:
        print(f"max_corr_after={max_pair_corr(kept):.4f}")
    for ac, winner, loser in decisions[:20]:
        print(f"drop corr={ac:.3f} loser_score={loser['score']:.5f} keep_score={winner['score']:.5f} | {loser['expression'][:90]}")

    if removed and not args.dry_run:
        con = sqlite3.connect(DB)
        con.executemany("DELETE FROM alpha_history WHERE rowid=?", [(r['rowid'],) for r in removed])
        con.commit()
        con.close()
        print(f"deleted={len(removed)}")


if __name__ == '__main__':
    main()
