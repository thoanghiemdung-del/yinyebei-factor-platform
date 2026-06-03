"""
Data pipeline for A-share factor competition.
Loads daily & minute data, handles alignment, provides non-future-leaking slices.
"""
import numpy as np
import pandas as pd
import joblib
import scipy.io as sio
import os
import glob
from pathlib import Path
from typing import Tuple, Optional, Dict, List
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class DataPipeline:
    """Unified data loader with strict non-future-leaking guarantees."""

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else DATA_DIR
        self._load_daily()
        self._build_maps()
        self._build_universe_mask()

    def _load_daily(self):
        """Load daily .bin file and extract all arrays."""
        bin_path = self.data_dir / 'DailyData20240102open.bin'
        with open(bin_path, 'rb') as f:
            self.daily = joblib.load(f)

        self.calendar = self.daily['CALENDAR_DF']
        self.cal_dates = pd.to_datetime(self.calendar['Day'].values)

        self.stocklist = self.daily['STOCKLIST']
        self.stock_codes = self.stocklist['code'].values
        self.stock_names = self.stocklist['name'].values
        self.ipo_dates = pd.to_datetime([str(x) for x in self.stocklist['IPO_DATE'].values], errors='coerce')
        raw_delist = self.stocklist['DELIST_DATE'].values
        self.delist_dates = pd.to_datetime([str(x) for x in raw_delist], errors='coerce')
        self.delist_dates = self.delist_dates.fillna(pd.Timestamp('2099-12-31'))

        # Core data arrays (dates × stocks, float32)
        self.fields = {}
        for key in self.daily:
            if isinstance(self.daily[key], np.ndarray) and self.daily[key].dtype == np.float32:
                self.fields[key] = self.daily[key]

        self.n_dates, self.n_stocks = self.fields['Label'].shape

    def _build_maps(self):
        """Build date ↔ index and stock code ↔ index mappings.

        FIX F3: Only map dates that correspond to actual data rows (n_dates).
        Calendar has n_dates+1 entries, data arrays have n_dates rows.
        """
        # Only map the first n_dates calendar entries (those with data)
        n_data = self.n_dates
        self.date_to_idx = {str(self.cal_dates[i].date()): i for i in range(n_data)}
        self.idx_to_date = {i: str(self.cal_dates[i].date()) for i in range(n_data)}
        self.stock_to_idx = {str(c): i for i, c in enumerate(self.stock_codes)}
        self.idx_to_stock = {i: str(c) for i, c in enumerate(self.stock_codes)}

        # Training period indices (within data array range)
        self.train_start = pd.Timestamp('2020-01-02')
        self.train_end = pd.Timestamp('2023-12-29')
        self.train_mask = (self.cal_dates[:n_data] >= self.train_start) & (self.cal_dates[:n_data] <= self.train_end)
        self.train_indices = np.where(self.train_mask)[0]
        self.train_data_indices = self.train_indices.copy()

    def _build_universe_mask(self):
        """Precompute stock universe masks — vectorized (FIX S1)."""
        n_dates, n_stocks = self.n_dates, self.n_stocks

        # Vectorized: broadcast date x stock comparisons
        dates_arr = self.cal_dates[:n_dates].values.reshape(-1, 1)  # (n_dates, 1)
        ipo_arr = self.ipo_dates.values.reshape(1, -1)              # (1, n_stocks)
        delist_arr = self.delist_dates.values.reshape(1, -1)

        listed = ipo_arr <= dates_arr
        not_delisted = delist_arr > dates_arr
        seasoned = (dates_arr - ipo_arr).astype('timedelta64[D]').astype(float) >= 120

        self.universe_mask = (listed & not_delisted & seasoned)

        # Exclude ST stocks
        st_mask = np.array(['ST' in str(n) or '*ST' in str(n) for n in self.stock_names])
        self.universe_mask[:, st_mask] = False

    def get_field(self, field: str, start_date: str = None, end_date: str = None) -> np.ndarray:
        """Get daily data field for a date range. Returns (dates, stocks) array."""
        if field not in self.fields:
            raise KeyError(f"Field '{field}' not found. Available: {list(self.fields.keys())}")

        data = self.fields[field]
        start_idx = self.date_to_idx.get(start_date, 0) if start_date else 0
        end_idx = self.date_to_idx.get(end_date, self.n_dates - 1) + 1 if end_date else self.n_dates

        start_idx = max(0, min(start_idx, self.n_dates))
        end_idx = max(0, min(end_idx, self.n_dates))

        return data[start_idx:end_idx].copy()

    def get_label(self, start_date: str = None, end_date: str = None) -> np.ndarray:
        """Get Label (forward 5-day return) for date range."""
        return self.get_field('Label', start_date, end_date)

    def get_universe(self, start_date: str = None, end_date: str = None) -> np.ndarray:
        """Get valid stock universe mask for date range."""
        start_idx = self.date_to_idx.get(start_date, 0) if start_date else 0
        end_idx = self.date_to_idx.get(end_date, self.n_dates - 1) + 1 if end_date else self.n_dates
        start_idx = max(0, min(start_idx, self.n_dates))
        end_idx = max(0, min(end_idx, self.n_dates))
        return self.universe_mask[start_idx:end_idx].copy()

    def get_dates(self, start_date: str = None, end_date: str = None) -> np.ndarray:
        """Get date array for a range."""
        start_idx = self.date_to_idx.get(start_date, 0) if start_date else 0
        end_idx = self.date_to_idx.get(end_date, self.n_dates - 1) + 1 if end_date else self.n_dates
        start_idx = max(0, min(start_idx, self.n_dates))
        end_idx = max(0, min(end_idx, self.n_dates))
        return self.cal_dates[start_idx:end_idx]

    # ---- Minute data ----

    def _get_minute_files(self) -> List[str]:
        """Get sorted list of minute .mat file paths."""
        pattern = str(self.data_dir / 'Minute*.mat')
        files = sorted(glob.glob(pattern))
        return files

    def get_minute_dates(self) -> List[str]:
        """Get list of available minute data dates (YYYYMMDD)."""
        files = self._get_minute_files()
        return [os.path.basename(f).replace('Minute', '').replace('.mat', '') for f in files]

    def load_minute_day(self, date_str: str) -> Dict[str, np.ndarray]:
        """Load all minute data for a single day.

        Args:
            date_str: Date in 'YYYYMMDD' format

        Returns:
            dict with keys: OPEN, HIGH, LOW, CLOSE, VOLUME, AMOUNT, NUMBER, STOCKLIST, TIMES
            Each price/volume field is (242 minutes, N stocks) float64
        """
        filepath = self.data_dir / f'Minute{date_str}.mat'
        if not filepath.exists():
            raise FileNotFoundError(f"Minute file not found: {filepath}")

        mat = sio.loadmat(str(filepath))

        # Extract stock codes
        sl = mat['STOCKLIST']
        n_stocks_minute = sl.shape[1]
        minute_codes = [str(sl[0, i][0]) for i in range(n_stocks_minute)]

        # Extract time labels
        times = mat['MinuteShow'][0] if 'MinuteShow' in mat else None

        result = {
            'OPEN': mat['MINUTE_OPEN'].reshape(242, n_stocks_minute).astype(np.float32),
            'HIGH': mat['MINUTE_HIGH'].reshape(242, n_stocks_minute).astype(np.float32),
            'LOW': mat['MINUTE_LOW'].reshape(242, n_stocks_minute).astype(np.float32),
            'CLOSE': mat['MINUTE_CLOSE'].reshape(242, n_stocks_minute).astype(np.float32),
            'VOLUME': mat['MINUTE_VOLUME'].reshape(242, n_stocks_minute).astype(np.float32),
            'AMOUNT': mat['MINUTE_AMOUNT'].reshape(242, n_stocks_minute).astype(np.float32),
            'NUMBER': mat['MINUTE_NUMBER'].reshape(242, n_stocks_minute).astype(np.float32),
            'STOCKLIST': minute_codes,
            'TIMES': times,
        }
        return result

    def align_minute_to_daily(self, minute_data: Dict, daily_date_idx: int) -> Dict[str, np.ndarray]:
        """Align minute stock dimension to daily stock dimension.

        Minute data has ~4065 stocks, daily has 5515 stocks.
        Returns minute fields with shape (242, n_daily_stocks), with NaN for missing stocks.
        """
        minute_codes = minute_data['STOCKLIST']
        n_minutes, n_minute_stocks = 242, len(minute_codes)

        # Build mapping: minute stock index → daily stock index
        # FIX S3: Validate stock code format match
        n_matched = 0
        mapping = np.full(len(self.stock_codes), -1, dtype=int)
        for mi, code in enumerate(minute_codes):
            if code in self.stock_to_idx:
                mapping[self.stock_to_idx[code]] = mi
                n_matched += 1

        if n_matched == 0:
            raise ValueError(
                f"Zero stock code match! Minute sample: {minute_codes[:5]}, "
                f"Daily sample: {list(self.stock_to_idx.keys())[:5]}")

        valid_daily = mapping >= 0  # (n_daily_stocks,) boolean

        result = {}
        for field in ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME', 'AMOUNT', 'NUMBER']:
            if field in minute_data:
                aligned = np.full((n_minutes, self.n_stocks), np.nan, dtype=np.float32)
                # FIX S2: Fancy indexing — no Python loop over stocks
                if valid_daily.any():
                    aligned[:, valid_daily] = minute_data[field][:, mapping[valid_daily]]
                result[field] = aligned

        result['TIMES'] = minute_data.get('TIMES', None)
        return result


class FactorEvaluator:
    """Evaluate factor quality using competition metrics."""

    @staticmethod
    def rank_ic(factor: np.ndarray, label: np.ndarray) -> float:
        """Compute cross-sectional rank IC (Spearman)."""
        valid = ~np.isnan(factor) & ~np.isnan(label)
        if valid.sum() < 10:
            return np.nan
        from scipy.stats import spearmanr
        ic, _ = spearmanr(factor[valid], label[valid])
        return ic

    @staticmethod
    def pearson_ic(factor: np.ndarray, label: np.ndarray) -> float:
        """Compute cross-sectional Pearson IC."""
        valid = ~np.isnan(factor) & ~np.isnan(label)
        if valid.sum() < 10:
            return np.nan
        return np.corrcoef(factor[valid], label[valid])[0, 1]

    @staticmethod
    def compute_daily_ic_series(factor_values: np.ndarray, label: np.ndarray,
                                 universe: np.ndarray = None) -> np.ndarray:
        """Compute daily rank IC series. factor_values: (dates, stocks)."""
        n_dates = factor_values.shape[0]
        ic_series = np.full(n_dates, np.nan)

        for t in range(n_dates):
            f = factor_values[t]
            l = label[t]
            if universe is not None:
                mask = universe[t] & ~np.isnan(f) & ~np.isnan(l)
            else:
                mask = ~np.isnan(f) & ~np.isnan(l)

            if mask.sum() >= 30:
                ic_series[t] = FactorEvaluator.rank_ic(f[mask], l[mask])

        return ic_series

    @staticmethod
    def compute_long_short(factor_values: np.ndarray, label: np.ndarray,
                           top_pct: float = 0.1, universe: np.ndarray = None) -> dict:
        """Compute Top N% long-short return metrics."""
        n_dates = factor_values.shape[0]
        long_returns = []
        short_returns = []

        for t in range(n_dates):
            f = factor_values[t]
            l = label[t]
            if universe is not None:
                mask = universe[t] & ~np.isnan(f) & ~np.isnan(l)
            else:
                mask = ~np.isnan(f) & ~np.isnan(l)

            if mask.sum() < 100:
                continue

            f_valid = f[mask]
            l_valid = l[mask]
            n_valid = len(f_valid)
            n_top = max(1, int(n_valid * top_pct))

            order = np.argsort(f_valid)
            long_idx = order[-n_top:]
            short_idx = order[:n_top]

            long_returns.append(np.nanmean(l_valid[long_idx]))
            short_returns.append(np.nanmean(l_valid[short_idx]))

        if not long_returns:
            return {'long_ret_daily': np.nan, 'short_ret_daily': np.nan,
                    'ls_ret_daily': np.nan, 'annual_ls_return': np.nan,
                    'ls_ir': np.nan, 'n_days': 0}

        long_arr = np.array(long_returns)
        short_arr = np.array(short_returns)
        ls_arr = long_arr - short_arr

        # Annualize: daily returns × 250 trading days
        annual_ls = np.nanmean(ls_arr) * 250

        return {
            'long_ret_daily': np.nanmean(long_arr),
            'short_ret_daily': np.nanmean(short_arr),
            'ls_ret_daily': np.nanmean(ls_arr),
            'annual_ls_return': annual_ls,
            'ls_ir': np.nanmean(ls_arr) / (np.nanstd(ls_arr) + 1e-10) * np.sqrt(250),
            'n_days': len(long_arr)
        }

    @staticmethod
    def full_eval(factor_values: np.ndarray, label: np.ndarray,
                  universe: np.ndarray = None) -> dict:
        """Complete factor evaluation matching competition scoring.

        Score = 0.5 × (IC component) + 0.5 × (Long-Short component)
        """
        ic_series = FactorEvaluator.compute_daily_ic_series(factor_values, label, universe)
        ls_metrics = FactorEvaluator.compute_long_short(factor_values, label, 0.1, universe)

        mean_ic = np.nanmean(ic_series)
        ic_ir = mean_ic / (np.nanstd(ic_series) + 1e-10)

        # Competition score: 50% IC + 50% long-short
        # Normalize IC component to comparable scale
        ic_score = mean_ic * 100  # Scale to percentage

        return {
            'mean_rank_ic': mean_ic,
            'ic_ir': ic_ir,
            'ic_std': np.nanstd(ic_series),
            'ic_positive_ratio': np.nansum(ic_series > 0) / np.sum(~np.isnan(ic_series)),
            'annual_ls_return': ls_metrics['annual_ls_return'],
            'ls_ir': ls_metrics['ls_ir'],
            'n_eval_days': ls_metrics['n_days'],
            'composite_score': 0.5 * ic_score + 0.5 * ls_metrics['annual_ls_return'],
        }


if __name__ == '__main__':
    pipeline = DataPipeline()
    print(f"Daily data: {pipeline.n_dates} dates × {pipeline.n_stocks} stocks")
    print(f"Training period: {len(pipeline.train_data_indices)} days")
    print(f"Fields: {list(pipeline.fields.keys())}")
    print(f"Label shape: {pipeline.fields['Label'].shape}")
    print(f"Universe valid stocks per day: {pipeline.universe_mask.sum(axis=1).mean():.0f}")

    # Test minute data loading
    minute_dates = pipeline.get_minute_dates()
    print(f"\nMinute data: {len(minute_dates)} days available")
    print(f"Date range: {minute_dates[0]} ~ {minute_dates[-1]}")

    # Load one minute day
    md = pipeline.load_minute_day(minute_dates[0])
    print(f"Minute stocks: {len(md['STOCKLIST'])}")
    print(f"Minute CLOSE shape: {md['CLOSE'].shape}")

    # Align test
    aligned = pipeline.align_minute_to_daily(md, 0)
    print(f"Aligned CLOSE shape: {aligned['CLOSE'].shape}")
    print(f"Aligned non-NaN stocks: {(~np.isnan(aligned['CLOSE'][0])).sum()}")

    print("\nPipeline test PASSED.")
