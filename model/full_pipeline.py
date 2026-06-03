"""
Full pipeline v4 — single entry point, uses FactorComputer only (no duplicate factor code).
Outputs: factor_ranking_full.csv, ensemble_full.npy, final_results.pkl, ensemble_results.csv
"""
import sys, os, numpy as np, pandas as pd, joblib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_pipeline import DataPipeline
from factor_library import FactorComputer, compute_all_factors
from backtest_framework import BacktestEngine, FactorEnsemble

print("=" * 70)
print("FULL PIPELINE v4 — Single entry point, FactorComputer only")
print("=" * 70)

# [1] Load data
print("\n[1/5] Loading data...")
p = DataPipeline()
t0, t1 = p.date_to_idx['2020-01-02'], min(p.date_to_idx['2023-12-29'] + 1, p.n_dates)
print(f"  Training: {t1-t0} days, {p.n_stocks} stocks")

# [2] Compute factors via FactorComputer (single source of truth)
print("\n[2/5] Computing factors via FactorComputer...")
factors = compute_all_factors(p, os.path.dirname(os.path.abspath(__file__)))

# Minute factor quality report (N2)
print("\n  Minute factor data quality:")
for name in sorted(factors.keys()):
    if name.startswith('F'):
        f = factors[name]
        f_train = f[t0:t1]
        nan_pct = np.isnan(f_train).mean()
        zero_pct = (f_train == 0).mean()
        extreme = np.sum(np.abs(f_train[~np.isnan(f_train)]) > 10)
        print(f"    {name}: NaN={nan_pct:.1%}, Zero={zero_pct:.1%}, extreme>10={extreme}")

print(f"\n  Total factors: {len(factors)}")

# [3] Factor selection: IS-ONLY (2020-2021) — NO FUTURE DATA LEAK (P0-B fix)
print("\n[3/5] Factor selection on 2020-2021 only (IS-only, no future leak)...")
engine = BacktestEngine(p)
t_is_end = p.date_to_idx['2021-12-31'] + 1
factors_is = {k: v[t0:t_is_end] for k, v in factors.items()}
label_is = p.fields['Label'][t0:t_is_end]
univ_is = p.universe_mask[t0:t_is_end]

results_is = engine.batch_evaluate(factors_is, mask=univ_is, label=label_is)
results_is.to_csv('factor_ranking_is_only.csv', index=False)

# Full-period factors for LGB training
factors_train = {k: v[t0:t1] for k, v in factors.items()}
label_train = p.fields['Label'][t0:t1]
univ_train = p.universe_mask[t0:t1]

# Also save full-period ranking (for reference only, NOT used for selection)
results_full = engine.batch_evaluate(factors_train, mask=univ_train, label=label_train)
results_full.to_csv('factor_ranking_full.csv', index=False)

print(f"\n  Top 10 IS-only factors (used for selection):")
cols = ['factor_name', 'mean_rank_ic', 'icir', 'annual_ls_return', 'ls_sharpe', 'ls_max_drawdown', 'annual_excess_return', 'composite_score', 'factor_direction']
print(results_is[cols].head(10).to_string())

# [4] Ensemble with IS-only selected factors
print("\n[4/5] Building ensemble (factors selected on IS-only)...")
norm = FactorEnsemble.normalize_factors(factors_is)
icirs = dict(zip(results_is['factor_name'], results_is['icir']))
signs = dict(zip(results_is['factor_name'], results_is['factor_direction']))

filtered, removed = FactorEnsemble.correlation_filter(norm, icirs, 0.6)
print(f"  After |corr|>0.6 filter: {len(filtered)} kept, removed: {removed}")

# Guard: some factors in filtered may not have valid IC (NaN) in results
valid_filtered = {k: v for k, v in filtered.items() if k in icirs and not np.isnan(icirs[k])}
print(f"  Valid factors with non-NaN IC: {len(valid_filtered)}")
icirs_f = {k: icirs[k] for k in valid_filtered}
signs_f = {k: signs[k] for k in valid_filtered}
filtered = valid_filtered
ensemble = FactorEnsemble.icir_weighted(filtered, icirs_f, signs_f)

res = engine.full_evaluation(ensemble, univ_train, label=label_train)
decay = engine.ic_decay_analysis(ensemble, label=label_train, universe=univ_train)

print(f"\n{'='*70}")
print(f"FINAL ENSEMBLE RESULTS")
print(f"{'='*70}")
for k, v in res.items():
    if isinstance(v, float) and 'series' not in k:
        print(f"  {k}: {v:.4f}")
print(f"  IC decay lag1: {decay[0]:.4f}  lag5: {decay[4]:.4f}  lag10: {decay[9]:.4f}")

# [5] LightGBM ensemble (P0-3: now actually called)
print("\n[5/5] LightGBM ensemble (purged walk-forward)...")
lgb_pred = FactorEnsemble.lightgbm_ensemble(
    filtered, label_train, univ_train, n_train_dates=(t1-t0)//2, n_purge=5)
if lgb_pred is not None:
    lgb_res = engine.full_evaluation(lgb_pred, univ_train, label=label_train, factor_name='LGB_ENSEMBLE')
    print(f"  LGB Pearson IC: {lgb_res['mean_pearson_ic']:.4f}")
    print(f"  LGB Rank IC:    {lgb_res['mean_rank_ic']:.4f}")
    print(f"  LGB L/S:        {lgb_res['annual_ls_return']:.2%}")
    print(f"  LGB MaxDD:      {lgb_res['ls_max_drawdown']:.2%}")

# Save
np.save('ensemble_full.npy', ensemble.astype(np.float32))
if lgb_pred is not None:
    np.save('ensemble_lgb.npy', lgb_pred.astype(np.float32))

# N7: Output ensemble results to human-readable CSV
ensemble_csv = pd.DataFrame([{
    'method': 'ICIR_Weighted',
    'pearson_ic': res['mean_pearson_ic'], 'rank_ic': res['mean_rank_ic'],
    'icir': res['icir'], 'ic_pos_ratio': res['ic_positive_ratio'],
    'annual_ls': res['annual_ls_return'], 'ls_sharpe': res['ls_sharpe'],
    'max_drawdown': res['ls_max_drawdown'], 'n_eval_days': res['n_eval_days'],
    'ic_decay_1': decay[0], 'ic_decay_5': decay[4], 'ic_decay_10': decay[9],
    'n_factors_used': len(filtered), 'n_factors_total': len(factors),
    'n_removed_by_corr': len(removed),
}])
if lgb_pred is not None:
    lgb_row = pd.DataFrame([{
        'method': 'LightGBM',
        'pearson_ic': lgb_res['mean_pearson_ic'], 'rank_ic': lgb_res['mean_rank_ic'],
        'icir': lgb_res['icir'], 'ic_pos_ratio': lgb_res['ic_positive_ratio'],
        'annual_ls': lgb_res['annual_ls_return'], 'ls_sharpe': lgb_res['ls_sharpe'],
        'max_drawdown': lgb_res['ls_max_drawdown'], 'n_eval_days': lgb_res['n_eval_days'],
        'ic_decay_1': np.nan, 'ic_decay_5': np.nan, 'ic_decay_10': np.nan,
        'n_factors_used': len(filtered), 'n_factors_total': len(factors),
        'n_removed_by_corr': len(removed),
    }])
    ensemble_csv = pd.concat([ensemble_csv, lgb_row])
ensemble_csv.to_csv('ensemble_results.csv', index=False)
print("\n  ensemble_results.csv saved")

joblib.dump({
    'ensemble': ensemble, 'lgb_ensemble': lgb_pred if lgb_pred is not None else None,
    'results': results, 'filtered': list(filtered.keys()), 'removed': removed,
    'icir_weights': icirs_f, 'factor_signs': signs_f,
    'eval_result': res, 'lgb_result': lgb_res if lgb_pred is not None else None,
    'ic_decay': decay,
}, 'final_results.pkl')

print("\nPIPELINE COMPLETE.")
print(f"  Files: ensemble_full.npy, ensemble_results.csv, factor_ranking_full.csv, final_results.pkl")
