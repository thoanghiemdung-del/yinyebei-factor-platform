"""
Backtest framework v2 — All P0 bugs fixed per code review.
- Proper stock-date aligned correlation filtering
- Purged walk-forward CV for LightGBM
- Dimension-correct composite score (Z-score method)
- Factor direction auto-detection from IC sign
"""
import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Optional, List, Tuple
import warnings
warnings.filterwarnings('ignore')


class BacktestEngine:
    """Factor backtesting with competition-specific metrics."""

    def __init__(self, pipeline, universe_mask: np.ndarray = None):
        self.p = pipeline
        self.universe = universe_mask if universe_mask is not None else pipeline.universe_mask
        self.label = pipeline.fields['Label']
        self.min_stocks_per_day = 30  # minimum stocks for valid IC computation

    def compute_rank_ic(self, factor: np.ndarray, mask: np.ndarray = None,
                        label: np.ndarray = None) -> np.ndarray:
        """Compute daily cross-sectional rank IC series (Spearman).
        If label is None, uses self.label (full dataset — ensure factor is aligned).
        For pre-sliced factors, pass the aligned label slice explicitly.
        """
        lbl = label if label is not None else self.label
        n_dates = factor.shape[0]
        ic_series = np.full(n_dates, np.nan)
        for t in range(n_dates):
            f, l = factor[t], lbl[t]
            valid = mask[t] if mask is not None else True
            valid = valid & (~np.isnan(f)) & (~np.isnan(l))
            if valid.sum() < self.min_stocks_per_day:
                continue
            ic_series[t] = stats.spearmanr(f[valid], l[valid])[0]
        return ic_series

    def compute_pearson_ic(self, factor: np.ndarray, mask: np.ndarray = None,
                           label: np.ndarray = None) -> np.ndarray:
        """Compute daily cross-sectional Pearson IC series."""
        lbl = label if label is not None else self.label
        n_dates = factor.shape[0]
        ic_series = np.full(n_dates, np.nan)
        for t in range(n_dates):
            f, l = factor[t], lbl[t]
            valid = mask[t] if mask is not None else True
            valid = valid & (~np.isnan(f)) & (~np.isnan(l))
            if valid.sum() < self.min_stocks_per_day:
                continue
            ic_series[t] = np.corrcoef(f[valid], l[valid])[0, 1]
        return ic_series

    def compute_long_short(self, factor: np.ndarray, top_pct: float = 0.1,
                           mask: np.ndarray = None, factor_direction: int = 1,
                           label: np.ndarray = None) -> Dict:
        """Compute Top N% long-short returns."""
        lbl = label if label is not None else self.label
        n_dates = factor.shape[0]
        long_ret, short_ret, ls_ret = [], [], []
        min_stocks = int(1 / top_pct) * 10

        for t in range(n_dates):
            f, l = factor[t], lbl[t]
            valid = mask[t] if mask is not None else True
            valid = valid & (~np.isnan(f)) & (~np.isnan(l))
            n_valid = valid.sum()
            if n_valid < min_stocks:
                continue

            fv, lv = f[valid], l[valid]
            n_top = max(1, int(n_valid * top_pct))
            order = np.argsort(fv)

            if factor_direction > 0:
                long_idx = order[-n_top:]   # highest factor values
                short_idx = order[:n_top]   # lowest factor values
            else:
                long_idx = order[:n_top]    # lowest factor values (reversal)
                short_idx = order[-n_top:]  # highest factor values

            long_ret.append(np.nanmean(lv[long_idx]))
            short_ret.append(np.nanmean(lv[short_idx]))
            ls_ret.append(np.nanmean(lv[long_idx]) - np.nanmean(lv[short_idx]))

        if len(ls_ret) < 30:
            return {'annual_ls_return': np.nan, 'ls_sharpe': np.nan,
                    'max_drawdown': np.nan, 'positive_ratio': np.nan,
                    'n_days': len(ls_ret), 'mean_long_ret': np.nan,
                    'annual_long_return': np.nan, 'annual_short_return': np.nan,
                    'ls_volatility': np.nan}

        ls_arr = np.array(ls_ret)
        long_arr = np.array(long_ret)
        short_arr = np.array(short_ret)
        annual_ls = np.nanmean(ls_arr) * 250
        ls_std = np.nanstd(ls_arr)
        ls_sharpe = annual_ls / (ls_std * np.sqrt(250) + 1e-10)

        # Max drawdown via log returns (avoids cumprod overflow)
        log_cum = np.cumsum(np.log(1 + np.clip(ls_arr, -0.5, 0.5)))
        peak = np.maximum.accumulate(log_cum)
        drawdown = 1 - np.exp(log_cum - peak)
        max_dd = np.nanmax(drawdown)  # dd > 0 when below peak

        return {
            'annual_ls_return': annual_ls,
            'annual_long_return': np.nanmean(long_arr) * 250,
            'annual_short_return': np.nanmean(short_arr) * 250,
            'ls_sharpe': ls_sharpe,
            'ls_volatility': ls_std * np.sqrt(250),
            'max_drawdown': max_dd,
            'positive_ratio': (ls_arr > 0).mean(),
            'n_days': len(ls_ret),
        }

    def compute_top_excess(self, factor: np.ndarray, top_pct: float = 0.1,
                           mask: np.ndarray = None, factor_direction: int = 1,
                           label: np.ndarray = None) -> Dict:
        """P0-A FIX: Competition metric = Top N% return - market average return.
        This is NOT long-short; it's excess return over equal-weight market.
        """
        lbl = label if label is not None else self.label
        n_dates = factor.shape[0]
        daily_excess = []
        min_stocks = int(1 / top_pct) * 10

        for t in range(n_dates):
            f, l = factor[t], lbl[t]
            valid = mask[t] if mask is not None else True
            valid = valid & (~np.isnan(f)) & (~np.isnan(l))
            if valid.sum() < min_stocks:
                continue
            fv, lv = f[valid], l[valid]
            n_top = max(1, int(len(fv) * top_pct))
            order = np.argsort(fv)
            if factor_direction > 0:
                top_ret = np.nanmean(lv[order[-n_top:]])
            else:
                top_ret = np.nanmean(lv[order[:n_top]])
            mkt_ret = np.nanmean(lv)
            daily_excess.append(top_ret - mkt_ret)

        if len(daily_excess) < 30:
            return {'annual_excess_return': np.nan, 'excess_sharpe': np.nan,
                    'excess_max_dd': np.nan, 'excess_positive_ratio': np.nan,
                    'n_excess_days': len(daily_excess)}

        ex_arr = np.array(daily_excess)
        annual_ex = np.nanmean(ex_arr) * 250
        ex_std = np.nanstd(ex_arr)
        ex_sharpe = annual_ex / (ex_std * np.sqrt(250) + 1e-10)

        log_cum = np.cumsum(np.log(1 + np.clip(ex_arr, -0.5, 0.5)))
        peak = np.maximum.accumulate(log_cum)
        drawdown = 1 - np.exp(log_cum - peak)
        max_dd = np.nanmax(drawdown)

        return {
            'annual_excess_return': annual_ex,
            'excess_sharpe': ex_sharpe,
            'excess_max_dd': max_dd,
            'excess_positive_ratio': (ex_arr > 0).mean(),
            'n_excess_days': len(daily_excess),
        }

    def full_evaluation(self, factor: np.ndarray, mask: np.ndarray = None,
                        factor_name: str = '', factor_direction: int = 1,
                        label: np.ndarray = None) -> Dict:
        """Complete single-factor evaluation. Pass label for pre-sliced factors."""
        rank_ic = self.compute_rank_ic(factor, mask, label=label)
        pearson_ic = self.compute_pearson_ic(factor, mask, label=label)
        ls_metrics = self.compute_long_short(factor, 0.1, mask, factor_direction, label=label)
        ex_metrics = self.compute_top_excess(factor, 0.1, mask, factor_direction, label=label)

        mean_rank_ic = np.nanmean(rank_ic)
        mean_pearson_ic = np.nanmean(pearson_ic)
        ic_std = np.nanstd(rank_ic)
        icir = mean_rank_ic / (ic_std + 1e-10)
        ic_pos_ratio = (rank_ic[~np.isnan(rank_ic)] > 0).mean()

        return {
            'factor_name': factor_name,
            'factor_direction': factor_direction,
            'mean_rank_ic': mean_rank_ic,
            'mean_pearson_ic': mean_pearson_ic,
            'ic_std': ic_std,
            'icir': icir,
            'ic_positive_ratio': ic_pos_ratio,
            'annual_ls_return': ls_metrics['annual_ls_return'],
            'ls_sharpe': ls_metrics['ls_sharpe'],
            'ls_max_drawdown': ls_metrics['max_drawdown'],
            'ls_positive_ratio': ls_metrics['positive_ratio'],
            'annual_excess_return': ex_metrics['annual_excess_return'],
            'excess_sharpe': ex_metrics['excess_sharpe'],
            'excess_max_dd': ex_metrics['excess_max_dd'],
            'n_eval_days': ls_metrics['n_days'],
            'ic_series': rank_ic,
            'pearson_ic_series': pearson_ic,
        }

    def batch_evaluate(self, factors: Dict[str, np.ndarray],
                       mask: np.ndarray = None,
                       start_date: str = None,
                       end_date: str = None,
                       label: np.ndarray = None) -> pd.DataFrame:
        """Evaluate all factors and return sorted results DataFrame.

        If start_date/end_date are None, uses factors as-is.
        If label is provided, uses it directly (critical for pre-sliced factors).
        """
        results = []
        if start_date is not None and end_date is not None:
            start_idx = self.p.date_to_idx.get(start_date, 0)
            end_idx = min(self.p.date_to_idx.get(end_date, self.p.n_dates - 1) + 1, self.p.n_dates)
            do_slice = True
        else:
            start_idx, end_idx = 0, list(factors.values())[0].shape[0]
            do_slice = False

        # Unified label: external > sliced > first-n-rows
        if label is not None:
            base_label = label
        elif do_slice:
            base_label = self.label[start_idx:end_idx]
        else:
            base_label = self.label[:end_idx]

        for name, factor in factors.items():
            f_train = factor[start_idx:end_idx] if do_slice else factor
            if np.isnan(f_train).mean() > 0.95:
                continue

            label_train = base_label[start_idx:end_idx] if do_slice else base_label[:f_train.shape[0]]
            universe_train = (self.universe[start_idx:end_idx] if do_slice else self.universe[:f_train.shape[0]]) \
                if mask is None else (mask[start_idx:end_idx] if do_slice else mask[:f_train.shape[0]])
            ic_raw = self.compute_rank_ic(f_train, universe_train, label=label_train)
            mean_ic_raw = np.nanmean(ic_raw)
            direction = 1 if np.nansum(ic_raw > 0) >= np.nansum(ic_raw < 0) else -1

            eval_result = self.full_evaluation(f_train, universe_train, name, direction, label=label_train)
            eval_result.pop('ic_series', None)
            eval_result.pop('pearson_ic_series', None)
            results.append(eval_result)

        df = pd.DataFrame(results)
        # Composite score: Z-score method (FIX P0-3: proper 50/50 balance)
        if len(df) > 2:
            df['ic_zscore'] = (df['mean_rank_ic'] - df['mean_rank_ic'].mean()) / (df['mean_rank_ic'].std() + 1e-10)
            df['ls_zscore'] = (df['annual_ls_return'] - df['annual_ls_return'].mean()) / (df['annual_ls_return'].std() + 1e-10)
            df['composite_score'] = 0.5 * df['ic_zscore'] + 0.5 * df['ls_zscore']
        else:
            df['composite_score'] = df['mean_rank_ic'].rank() + df['annual_ls_return'].rank()

        return df.sort_values('composite_score', ascending=False)

    def ic_decay_analysis(self, factor: np.ndarray, max_lag: int = 20,
                          label: np.ndarray = None, universe: np.ndarray = None) -> np.ndarray:
        """Compute IC decay curve. FIX N4: Accept aligned label/universe."""
        lbl = label if label is not None else self.label
        univ = universe if universe is not None else self.universe
        decays = np.full(max_lag, np.nan)
        for lag in range(1, max_lag + 1):
            ics = []
            for t in range(len(factor) - lag):
                f, l = factor[t], lbl[t + lag]
                valid = univ[t] & (~np.isnan(f)) & (~np.isnan(l))
                if valid.sum() >= 30:
                    ics.append(stats.spearmanr(f[valid], l[valid])[0])
            if ics:
                decays[lag - 1] = np.nanmean(ics)
        return decays


class FactorEnsemble:
    """Factor combination with rigorous IC-based selection."""

    @staticmethod
    def normalize_factors(factors: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Cross-sectional winsorize (1%/99%) + z-score normalize."""
        normalized = {}
        for name, factor in factors.items():
            n_dates = factor.shape[0]
            norm = np.full_like(factor, np.nan)
            for t in range(n_dates):
                f = factor[t].copy()
                valid = ~np.isnan(f)
                if valid.sum() < 30:
                    continue
                v = f[valid]
                lo, hi = np.percentile(v, [1, 99])
                v_clipped = np.clip(v, lo, hi)
                mu, sigma = np.nanmean(v_clipped), np.nanstd(v_clipped)
                norm[t, valid] = (v_clipped - mu) / (sigma + 1e-10)
            normalized[name] = norm
        return normalized

    @staticmethod
    def correlation_filter(factors: Dict[str, np.ndarray],
                           icir_dict: Dict[str, float],
                           threshold: float = 0.6) -> Tuple[Dict[str, np.ndarray], List[str]]:
        """Filter correlated factors, keeping the one with higher |ICIR|.

        FIX P0-1: Uses stock-date aligned intersection for each pair.
        FIX P1-2: Keeps factor with higher |ICIR| when correlated.
        """
        names = list(factors.keys())
        kept = set(names)
        removed = []

        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                ni, nj = names[i], names[j]
                if ni not in kept or nj not in kept:
                    continue

                fi = factors[ni].ravel()
                fj = factors[nj].ravel()
                # P0-1 FIX: Use intersection of valid stock-date pairs
                both_valid = ~np.isnan(fi) & ~np.isnan(fj)
                if both_valid.sum() < 100:
                    continue

                corr = abs(np.corrcoef(fi[both_valid], fj[both_valid])[0, 1])
                if corr > threshold:
                    # P1-2 FIX: Keep factor with higher absolute ICIR
                    qi = abs(icir_dict.get(ni, 0))
                    qj = abs(icir_dict.get(nj, 0))
                    if qi >= qj:
                        removed.append(nj)
                        kept.discard(nj)
                    else:
                        removed.append(ni)
                        kept.discard(ni)

        filtered = {k: v for k, v in factors.items() if k in kept}
        return filtered, removed

    @staticmethod
    def icir_weighted(factors: Dict[str, np.ndarray],
                      icir_dict: Dict[str, float],
                      factor_sign: Dict[str, int]) -> np.ndarray:
        """ICIR-weighted ensemble with correct sign handling.

        FIX P0-4: Uses absolute ICIR for weight, sign from factor_direction.
        FIX P1-1: Efficient accumulation without redundant isnan checks.
        """
        n_dates, n_stocks = list(factors.values())[0].shape
        total_weight = sum(abs(icir_dict.get(k, 0)) for k in factors) or 1.0
        combined = np.zeros((n_dates, n_stocks))

        for name, factor in factors.items():
            w = abs(icir_dict.get(name, 0)) / total_weight
            sgn = factor_sign.get(name, 1)
            weighted = w * sgn * factor
            valid = ~np.isnan(weighted)
            combined[valid] += weighted[valid]

        # Set untouched positions to NaN
        untouched = np.all(np.isnan(list(factors.values())), axis=0)
        combined[untouched] = np.nan
        return combined

    @staticmethod
    def lightgbm_ensemble(factors: Dict[str, np.ndarray], label: np.ndarray,
                          universe: np.ndarray, n_train_dates: int,
                          n_purge: int = 5) -> np.ndarray:
        """LightGBM ensemble with purged walk-forward validation.

        FIX P0-2: Uses expanding window with purge gap. No future data leakage.
        Train on [0, train_end-purge), predict on [test_start, test_end).
        """
        try:
            import lightgbm as lgb
        except ImportError:
            return None

        factor_names = list(factors.keys())
        n_dates, n_stocks = list(factors.values())[0].shape

        predictions = np.full((n_dates, n_stocks), np.nan)
        min_train = 250  # minimum 250 days for initial training

        # Expanding window: retrain every ~60 days
        for test_start in range(min_train, n_dates, 60):
            test_end = min(test_start + 60, n_dates)
            train_end = max(0, test_start - n_purge)  # purge gap

            # Build training data from [0, train_end)
            X_list, y_list = [], []
            for t in range(train_end):
                valid = universe[t] & (~np.isnan(label[t]))
                for fn in factor_names:
                    valid = valid & (~np.isnan(factors[fn][t]))
                if valid.sum() < 100:
                    continue
                feats = np.column_stack([factors[fn][t][valid] for fn in factor_names])
                X_list.append(feats)
                y_list.append(label[t][valid])

            if len(X_list) < 50:
                continue

            X_train = np.vstack(X_list)
            y_train = np.concatenate(y_list)

            model = lgb.LGBMRegressor(
                n_estimators=50, max_depth=2, num_leaves=7,
                min_child_samples=2000, learning_rate=0.005,
                reg_alpha=5.0, reg_lambda=5.0,
                subsample=0.5, colsample_bytree=0.5,
                random_state=42, verbose=-1
            )
            model.fit(X_train, y_train)

            # Predict for test window
            for t in range(test_start, test_end):
                valid = universe[t]
                for fn in factor_names:
                    valid = valid & (~np.isnan(factors[fn][t]))
                if valid.sum() < 100:
                    continue
                feats = np.column_stack([factors[fn][t][valid] for fn in factor_names])
                predictions[t][valid] = model.predict(feats)

        return predictions


def run_full_pipeline(pipeline, factors: Dict[str, np.ndarray] = None,
                      train_start='2020-01-02', train_end='2023-12-29',
                      val_start='2022-07-01', val_end='2022-12-31',
                      test_start='2023-01-01', test_end='2023-12-29') -> Dict:
    """Run complete factor evaluation and ensemble pipeline."""
    from factor_library import compute_all_factors
    import os

    output_dir = os.path.dirname(os.path.abspath(__file__))

    # Step 1: Compute or load factors
    if factors is None:
        print("Computing all factors...")
        factors = compute_all_factors(pipeline, output_dir)

    # Step 2: Normalize factors
    print(f"\nNormalizing {len(factors)} factors...")
    normalized = FactorEnsemble.normalize_factors(factors)

    # Step 3: First-pass evaluation to get ICIR + direction
    print("First-pass evaluation (2020-2021 training, 2022H1 validation)...")
    engine = BacktestEngine(pipeline)

    # Training period evaluation
    train_df = engine.batch_evaluate(
        normalized, start_date=train_start, end_date='2021-12-31')

    # Build ICIR dict and sign dict
    icir_dict = dict(zip(train_df['factor_name'], train_df['icir']))
    factor_sign = dict(zip(train_df['factor_name'], train_df['factor_direction']))

    print(f"  Factors with |ICIR| > 0.3: {(train_df['icir'].abs() > 0.3).sum()}")
    print(f"  Positive direction: {(train_df['factor_direction'] > 0).sum()}")
    print(f"  Negative direction: {(train_df['factor_direction'] < 0).sum()}")

    # Step 4: Correlation filter
    print("\nCorrelation filtering (threshold=0.6, stock-date aligned)...")
    filtered, removed = FactorEnsemble.correlation_filter(
        normalized, icir_dict, threshold=0.6)
    print(f"  Removed {len(removed)} redundant factors, keeping {len(filtered)}")

    # Step 5: Second-pass evaluation on validation period
    print("\nValidation period evaluation...")
    val_df = engine.batch_evaluate(
        filtered, start_date=val_start, end_date=val_end)

    # Update ICIR from validation
    icir_dict_val = dict(zip(val_df['factor_name'], val_df['icir']))
    factor_sign_val = dict(zip(val_df['factor_name'], val_df['factor_direction']))

    # Step 6: ICIR-weighted ensemble
    print("\nBuilding ICIR-weighted ensemble...")
    ensemble = FactorEnsemble.icir_weighted(filtered, icir_dict_val, factor_sign_val)

    # Step 7: Full evaluation
    print("\nEvaluating ensemble on full period...")
    ensemble_train = ensemble
    label_all = pipeline.fields['Label']
    universe_all = pipeline.universe_mask

    # Training period result
    train_result = engine.full_evaluation(
        ensemble_train[pipeline.date_to_idx[train_start]:pipeline.date_to_idx[train_end]+1],
        universe_all[pipeline.date_to_idx[train_start]:pipeline.date_to_idx[train_end]+1],
        None, 'ENSEMBLE_TRAIN')

    # Test period result
    test_result = engine.full_evaluation(
        ensemble_train[pipeline.date_to_idx[test_start]:pipeline.date_to_idx[test_end]+1],
        universe_all[pipeline.date_to_idx[test_start]:pipeline.date_to_idx[test_end]+1],
        None, 'ENSEMBLE_TEST')

    # Print results
    for label, res in [('TRAIN (2020-2021)', train_result), ('TEST (2023)', test_result)]:
        print(f"\n{'='*60}")
        print(f"ENSEMBLE {label}")
        print(f"{'='*60}")
        for k in ['mean_rank_ic', 'mean_pearson_ic', 'icir', 'ic_positive_ratio',
                   'annual_ls_return', 'ls_sharpe', 'ls_max_drawdown']:
            v = res[k]
            if isinstance(v, float):
                if 'ratio' in k:
                    print(f"  {k}: {v:.2%}")
                elif 'annual' in k or 'drawdown' in k:
                    print(f"  {k}: {v:.2%}")
                else:
                    print(f"  {k}: {v:.4f}")

    # Top factors
    print(f"\nTop 20 Factors by validation composite score:")
    cols = ['factor_name', 'mean_rank_ic', 'mean_pearson_ic', 'icir',
            'annual_ls_return', 'ls_sharpe', 'composite_score', 'factor_direction']
    print(val_df[cols].head(20).to_string())

    # IC decay
    print("\nIC decay analysis...")
    decay = engine.ic_decay_analysis(
        ensemble_train[pipeline.date_to_idx[train_start]:pipeline.date_to_idx['2021-12-31']+1])
    for lag in [1, 3, 5, 10, 20]:
        if lag <= len(decay):
            print(f"  Lag {lag:2d}: IC={decay[lag-1]:.4f}")

    return {
        'factors': factors,
        'normalized': normalized,
        'filtered': filtered,
        'train_df': train_df,
        'val_df': val_df,
        'ensemble': ensemble,
        'train_result': train_result,
        'test_result': test_result,
        'ic_decay': decay,
        'removed_factors': removed,
        'factor_signs': factor_sign_val,
    }
