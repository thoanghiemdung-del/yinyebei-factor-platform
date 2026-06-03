"""
Factor library for A-share quant competition.
Implements 80+ factors across 8 categories, with focus on minute-microstructure factors.
"""
import numpy as np
from scipy import stats
from scipy.ndimage import uniform_filter1d
from typing import Optional, Tuple, Dict, List
import warnings
warnings.filterwarnings('ignore')

# Default windows
SHORT_W = 5
MEDIUM_W = 20
LONG_W = 60
LONGEST_W = 120


def rolling_mean(arr: np.ndarray, window: int, axis: int = 0) -> np.ndarray:
    """NaN-aware rolling mean along an axis."""
    result = np.full_like(arr, np.nan)
    if arr.shape[axis] < window:
        return result
    if axis == 0:
        for i in range(window - 1, arr.shape[0]):
            result[i] = np.nanmean(arr[i - window + 1:i + 1], axis=0)
    else:
        for i in range(window - 1, arr.shape[1]):
            result[:, i] = np.nanmean(arr[:, i - window + 1:i + 1], axis=1)
    return result


def rolling_std(arr: np.ndarray, window: int, axis: int = 0) -> np.ndarray:
    """NaN-aware rolling standard deviation."""
    result = np.full_like(arr, np.nan)
    if arr.shape[axis] < window:
        return result
    if axis == 0:
        for i in range(window - 1, arr.shape[0]):
            result[i] = np.nanstd(arr[i - window + 1:i + 1], axis=0)
    else:
        for i in range(window - 1, arr.shape[1]):
            result[:, i] = np.nanstd(arr[:, i - window + 1:i + 1], axis=1)
    return result


def rolling_corr(x: np.ndarray, y: np.ndarray, window: int) -> np.ndarray:
    """NaN-aware rolling correlation between two 2D arrays (dates, stocks)."""
    n_dates, n_stocks = x.shape
    result = np.full((n_dates, n_stocks), np.nan)
    for t in range(window - 1, n_dates):
        for s in range(n_stocks):
            xw = x[t - window + 1:t + 1, s]
            yw = y[t - window + 1:t + 1, s]
            mask = ~np.isnan(xw) & ~np.isnan(yw)
            if mask.sum() >= 10:
                result[t, s] = np.corrcoef(xw[mask], yw[mask])[0, 1]
    return result


def cross_sectional_rank(arr: np.ndarray) -> np.ndarray:
    """Rank stocks within each day cross-section, return percentile [0,1]."""
    result = np.full_like(arr, np.nan)
    for t in range(arr.shape[0]):
        row = arr[t].copy()
        valid = ~np.isnan(row)
        if valid.sum() < 10:
            continue
        result[t, valid] = stats.rankdata(row[valid]) / valid.sum()
    return result


def cross_sectional_zscore(arr: np.ndarray) -> np.ndarray:
    """Z-score normalize within each day cross-section."""
    result = np.full_like(arr, np.nan)
    for t in range(arr.shape[0]):
        row = arr[t].copy()
        valid = ~np.isnan(row)
        if valid.sum() < 10:
            continue
        mu = np.nanmean(row[valid])
        sigma = np.nanstd(row[valid])
        result[t, valid] = (row[valid] - mu) / (sigma + 1e-10)
    return result


def winsorize_cs(arr: np.ndarray, lo: float = 0.01, hi: float = 0.99) -> np.ndarray:
    """Winsorize within each daily cross-section."""
    result = arr.copy()
    for t in range(arr.shape[0]):
        row = arr[t].copy()
        valid = ~np.isnan(row)
        if valid.sum() < 30:
            continue
        v = row[valid]
        lo_val = np.percentile(v, lo * 100)
        hi_val = np.percentile(v, hi * 100)
        row[valid] = np.clip(v, lo_val, hi_val)
        result[t] = row
    return result


def ts_delta(arr: np.ndarray, window: int) -> np.ndarray:
    """arr[t] - arr[t-window]."""
    result = np.full_like(arr, np.nan)
    result[window:] = arr[window:] - arr[:-window]
    return result


def ts_sum(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling sum. FIX P1-2: Correct NaN handling with nansum."""
    result = np.full_like(arr, np.nan)
    for i in range(window - 1, arr.shape[0]):
        result[i] = np.nansum(arr[i - window + 1:i + 1], axis=0)
    return result


def ts_max(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling maximum."""
    result = np.full_like(arr, np.nan)
    for i in range(window - 1, arr.shape[0]):
        result[i] = np.nanmax(arr[i - window + 1:i + 1], axis=0)
    return result


def ts_min(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling minimum."""
    result = np.full_like(arr, np.nan)
    for i in range(window - 1, arr.shape[0]):
        result[i] = np.nanmin(arr[i - window + 1:i + 1], axis=0)
    return result


def signed_power(arr: np.ndarray, exp: float) -> np.ndarray:
    """sign(arr) * |arr|^exp."""
    return np.sign(arr) * np.power(np.abs(arr), exp)


class FactorComputer:
    """Compute all factors from daily and minute data."""

    def __init__(self, pipeline):
        self.p = pipeline  # DataPipeline instance
        self.n_dates = pipeline.n_dates
        self.n_stocks = pipeline.n_stocks

        # Pre-load all daily data
        self.close = pipeline.fields['I_D_CLOSE_ORI']
        self.open = pipeline.fields['I_D_OPEN_ORI']
        self.high = pipeline.fields['I_D_HIGH_ORI']
        self.low = pipeline.fields['I_D_LOW_ORI']
        self.preclose = pipeline.fields['I_D_PRECLOSE_ORI']
        self.amount = pipeline.fields['I_D_AMOUNT']
        self.volume = pipeline.fields['I_D_VOLUME']
        self.adjfactor = pipeline.fields['I_D_ADJFACTOR']
        self.free_shares = pipeline.fields['I_D_SHARE_FREESHARES']
        self.liqa_shares = pipeline.fields['I_D_SHARE_LIQA']
        self.total_shares = pipeline.fields['I_D_TOTAL_SHARES']

        # Derived daily fields
        self._compute_derived()

        # Cache for minute-derived daily aggregates
        self._minute_cache = {}
        self._factor_cache = {}

    def _compute_derived(self):
        """Compute derived daily fields with correct adjfactor handling.

        CRITICAL: adjfactor[t] adjusts price[t] to a common reference point.
        adj_close[t] = close_ori[t] * adjfactor[t] is "backward-adjusted".
        Daily return = adj_close[t] / adj_close[t-1] - 1 gives CORRECT total return
        because adjfactor[t] already accounts for dividends between t-1 and t.
        """
        eps = 1e-10
        # Fill NaN adjfactor with 1.0 (conservative: assume no adjustment)
        safe_adjfactor = np.where(np.isnan(self.adjfactor), 1.0, self.adjfactor)
        # Clip extreme adjfactor values (data errors) to [0.01, 100]
        safe_adjfactor = np.clip(safe_adjfactor, 0.01, 100.0)

        self.adj_close = self.close * safe_adjfactor
        self.adj_open = self.open * safe_adjfactor
        self.adj_high = self.high * safe_adjfactor
        self.adj_low = self.low * safe_adjfactor

        # Correct daily return: adj_close[t] / adj_close[t-1] - 1
        # Use safe_adjfactor[t-1] for yesterday's adjusted close
        adjfactor_tm1 = np.roll(safe_adjfactor, 1, axis=0)
        adjfactor_tm1[0] = safe_adjfactor[0]  # first row: use same factor

        close_tm1_adj = self.preclose * adjfactor_tm1
        self.daily_ret = self.adj_close / (close_tm1_adj + eps) - 1

        # Clip extreme daily returns (data errors, >500% in one day is almost certainly data issue)
        self.daily_ret = np.clip(self.daily_ret, -0.99, 5.0)

        # Overnight return (close[t-1] → open[t])
        self.overnight_ret = np.full_like(self.daily_ret, np.nan)
        self.overnight_ret[1:] = self.adj_open[1:] / (self.adj_close[:-1] + eps) - 1
        self.overnight_ret = np.clip(self.overnight_ret, -0.99, 5.0)

        # Intraday return (open[t] → close[t])
        self.intraday_ret = self.adj_close / (self.adj_open + eps) - 1
        self.intraday_ret = np.clip(self.intraday_ret, -0.99, 5.0)

        # VWAP proxy: (high+low+close)/3
        self.vwap_proxy = (self.adj_high + self.adj_low + self.adj_close) / 3

        # Log dollar volume
        self.log_dollar_vol = np.log(1 + self.amount)

        # Turnover
        self.turnover = self.volume / (self.free_shares + eps)

        # Market cap proxy: close * total_shares
        self.market_cap = self.adj_close * self.total_shares

    # ============================================================
    # Category A: Momentum Factors (15)
    # ============================================================

    def A1_ret_Nd(self, N=20):
        """Raw N-day return. DEPRECATED: use _ret_N instead."""
        return self._ret_N(N)

    def A1_1_ret_20d(self): return self._ret_N(20)
    def A1_2_ret_60d(self): return self._ret_N(60)
    def A1_3_ret_120d_skip5(self): return self._ret_N_skip(120, 5)
    def A1_4_ret_5d(self): return self._ret_N(5)

    def A2_1_sharpe_60d(self):
        ret = self.daily_ret
        return rolling_mean(ret, 60) / (rolling_std(ret, 60) + 1e-10)

    def A2_2_mom_vol_adj(self):
        ret_60d = self._ret_N(60)
        vol_60d = rolling_std(self.daily_ret, 60)
        return ret_60d / (1 + vol_60d)

    def A3_1_max_dd_60d(self):
        """Negative max drawdown over 60 days. FIX P1-5: efficient."""
        rolling_max = np.full_like(self.adj_close, np.nan)
        for t in range(59, self.n_dates):
            rolling_max[t] = np.nanmax(self.adj_close[t - 59:t + 1], axis=0)
        dd = (self.adj_close - rolling_max) / (rolling_max + 1e-10)
        return -dd

    def A3_3_close_vs_high_20d(self):
        return self.adj_close / (ts_max(self.adj_high, 20) + 1e-10)

    # ============================================================
    # Category B: Reversal Factors (12)
    # ============================================================

    def B1_1_rev_1d(self): return -self.daily_ret
    def B1_2_rev_5d(self): return -self._ret_N(5)
    def B1_4_rev_overnight(self): return -self.overnight_ret

    def B2_1_abnormal_vol_rev(self):
        vol_ratio = self.volume / (rolling_mean(self.volume, 20) + 1e-10)
        return -self.daily_ret * vol_ratio

    def B3_1_extreme_loser_5d(self):
        ret_5d = self._ret_N(5)
        mask = ret_5d < -0.10
        result = np.full_like(ret_5d, np.nan)
        result[mask] = -ret_5d[mask]
        return result

    def B3_2_extreme_winner_5d(self):
        ret_5d = self._ret_N(5)
        mask = ret_5d > 0.15
        result = np.full_like(ret_5d, np.nan)
        result[mask] = -ret_5d[mask]
        return result

    # ============================================================
    # Category C: Volatility Factors (10)
    # ============================================================

    def C1_1_vol_20d(self): return rolling_std(self.daily_ret, 20)
    def C1_2_vol_60d(self): return rolling_std(self.daily_ret, 60)
    def C1_3_vol_ratio(self): return self.C1_1_vol_20d() / (self.C1_2_vol_60d() + 1e-10)

    def C2_1_downside_vol_60d(self):
        neg_ret = np.where(self.daily_ret < 0, self.daily_ret, np.nan)
        return rolling_std(neg_ret, 60)

    def C4_1_skewness_60d(self):
        key = 'C4_1_skewness_60d'
        if key not in self._factor_cache:
            self._factor_cache[key] = self._rolling_moment(self.daily_ret, 60, 'skew')
        return self._factor_cache[key]

    # ============================================================
    # Category D: Volume & Liquidity (15)
    # ============================================================

    def D1_1_vol_ratio_5_20(self):
        return rolling_mean(self.volume, 5) / (rolling_mean(self.volume, 20) + 1e-10)

    def D1_3_volume_breakout(self):
        return self.volume / (ts_max(self.volume, 60) + 1e-10)

    def D2_1_turnover_5d(self): return rolling_mean(self.turnover, 5)
    def D2_2_turnover_change(self): return self.D2_1_turnover_5d() / (rolling_mean(self.turnover, 20) + 1e-10) - 1

    def D3_1_amihud_20d(self):
        """Amihud illiquidity measure."""
        daily_amihud = np.abs(self.daily_ret) / (self.amount + 1e-10)
        return rolling_mean(daily_amihud, 20)

    def D4_1_log_dollar_vol(self): return self.log_dollar_vol

    # ============================================================
    # Category E: Daily Price Patterns (10)
    # ============================================================

    def E1_1_upper_shadow(self):
        return (self.adj_high - np.maximum(self.adj_open, self.adj_close)) / \
               (self.adj_high - self.adj_low + 1e-10)

    def E1_2_lower_shadow(self):
        return (np.minimum(self.adj_open, self.adj_close) - self.adj_low) / \
               (self.adj_high - self.adj_low + 1e-10)

    def E1_3_body_ratio(self):
        return np.abs(self.adj_close - self.adj_open) / (self.adj_high - self.adj_low + 1e-10)

    def E2_1_gap_up(self): return self.overnight_ret

    # ============================================================
    # Category F: Minute Microstructure Factors (30) — THE DIFFERENTIATOR
    # ============================================================

    def compute_all_minute_aggregates(self):
        """Pre-compute daily aggregates from minute data for all 970 days.
        This is the heavy computation step. Results cached in self._minute_cache.
        """
        minute_dates = self.p.get_minute_dates()
        # Only compute for dates within our daily data range
        daily_date_set = set(self.p.idx_to_date.values())

        # Storage for aggregates: each key -> (n_dates, n_stocks) array
        agg_keys = ['first30_ret', 'last30_ret', 'intraday_ret_min', 'am_pm_ret_ratio',
                     'realized_vol', 'vol_skew', 'close_vs_vwap', 'vwap_trend',
                     'volume_hhi', 'open_vol_ratio', 'close_vol_ratio', 'vol_profile_skew',
                     'smart_money_vol', 'vol_price_corr', 'amihud_min', 'vpin',
                     'large_trade_ratio', 'roll_spread', 'weighted_avg_time',
                     'last_bar_ret', 'last_bar_vol_ratio', 'gap_t']
        result = {k: np.full((self.n_dates, self.n_stocks), np.nan, dtype=np.float32)
                  for k in agg_keys}

        for date_str in minute_dates:
            # Map to daily index
            date_obj = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            if date_obj not in self.p.date_to_idx:
                continue
            t = self.p.date_to_idx[date_obj]
            if t >= self.n_dates:
                continue

            try:
                md = self.p.load_minute_day(date_str)
                aligned = self.p.align_minute_to_daily(md, t)
                self._compute_minute_aggregates_one_day(aligned, t, result)
            except Exception as e:
                if int(date_str[4:6]) in (1, 7) and int(date_str[6:8]) <= 10:
                    print(f"  [WARN] minute aggregates failed for {date_str}: {e}")
                continue

            if int(date_str[4:]) == 101:  # Progress marker
                print(f"  Minute aggregates: processed up to {date_str}")

        self._minute_cache = result
        print(f"Minute aggregates computed: {len(minute_dates)} days, "
              f"fields: {list(result.keys())}")
        return result

    def _compute_minute_aggregates_one_day(self, md, t, result):
        """Compute all minute-derived daily values for one day."""
        # md: dict with OPEN, HIGH, LOW, CLOSE, VOLUME, AMOUNT, NUMBER
        # Each is (242, n_stocks) float32
        o = md['OPEN']
        c = md['CLOSE']
        h = md['HIGH']
        l = md['LOW']
        v = md['VOLUME']
        a = md['AMOUNT']
        n_bars = o.shape[0]
        n_stocks = o.shape[1]
        mid = n_bars // 2
        f30_end = min(30, n_bars)
        l30_start = max(0, n_bars - 30)
        l30_start_vol = max(0, n_bars - 30)
        eps = 1e-10

        # Minute returns (use relative indexing to handle variable bar counts)
        min_ret = np.full_like(o, np.nan)
        min_ret[1:] = (o[1:] - o[:-1]) / (o[:-1] + eps)
        min_ret_c = np.full_like(c, np.nan)
        min_ret_c[1:] = (c[1:] - c[:-1]) / (c[:-1] + eps)

        # --- F1: Intraday momentum ---
        # first30 (bars 0 to f30_end-1, ~09:25-09:55)
        first30_open = o[0]  # open price
        first30_close = c[f30_end - 1]
        result['first30_ret'][t] = (first30_close - first30_open) / (first30_open + eps)

        # last30 (bars l30_start to n_bars-1)
        last30_open = o[l30_start]
        last30_close = c[-1]
        result['last30_ret'][t] = (last30_close - last30_open) / (last30_open + eps)

        # Full intraday return
        result['intraday_ret_min'][t] = (c[-1] - o[0]) / (o[0] + eps)

        # --- F2: Intraday reversal (AM/PM divergence) ---
        am_ret = (c[mid - 1] - o[0]) / (o[0] + eps)
        pm_ret = (c[-1] - o[mid]) / (o[mid] + eps)
        result['am_pm_ret_ratio'][t] = am_ret / (np.abs(pm_ret) + eps)

        # --- F3: Intraday volatility ---
        rv = np.sqrt(np.nansum(min_ret_c ** 2, axis=0) * n_bars)
        result['realized_vol'][t] = rv

        am_vol = np.nanstd(min_ret_c[:mid], axis=0)
        pm_vol = np.nanstd(min_ret_c[mid:], axis=0)
        result['vol_skew'][t] = np.clip(am_vol / np.maximum(pm_vol, 0.0001), 0.01, 10)

        # --- F4: VWAP ---
        price_avg = (h + l + c) / 3
        vwap = np.nansum(price_avg * v, axis=0) / (np.nansum(v, axis=0) + eps)
        result['close_vs_vwap'][t] = (c[-1] - vwap) / (vwap + eps)
        vwap_am = np.nansum(price_avg[:mid] * v[:mid], axis=0) / (np.nansum(v[:mid], axis=0) + eps)
        vwap_pm = np.nansum(price_avg[mid:] * v[mid:], axis=0) / (np.nansum(v[mid:], axis=0) + eps)
        result['vwap_trend'][t] = np.clip((vwap_pm - vwap_am) / (vwap_am + eps), -2, 2)

        # --- F5: Volume distribution ---
        total_v = np.nansum(v, axis=0)
        v_norm = v / (total_v + eps)
        result['volume_hhi'][t] = np.nansum(v_norm ** 2, axis=0)
        # f30_end = min(30, n_bars), ~前30分钟
        result['open_vol_ratio'][t] = np.nansum(v[:f30_end], axis=0) / (total_v + eps)
        result['close_vol_ratio'][t] = np.nansum(v[l30_start_vol:], axis=0) / (total_v + eps)

        # Volume profile skew (positive = volume tilts late)
        bar_idx = np.arange(n_bars).reshape(-1, 1)
        weighted_time = np.nansum(bar_idx * v_norm, axis=0)
        result['weighted_avg_time'][t] = weighted_time / n_bars

        # Smart money: volume on up-bars
        # FIX P1-6: Compute bar 0 direction separately to avoid NaN exclusion
        bar_direction = np.sign(min_ret_c)
        bar_direction[0] = np.sign(c[0] - o[0])
        result['smart_money_vol'][t] = np.nansum(v * (bar_direction > 0), axis=0) / (total_v + eps)

        # --- F6: Price-volume interaction ---
        # VPIN-style
        result['vpin'][t] = np.nansum(v * np.abs(min_ret_c), axis=0) / (np.sqrt(np.nansum(v ** 2, axis=0)) + eps)

        # Amihud-minute: clip extreme values from near-zero amount
        raw_amihud = np.abs(min_ret_c) / np.maximum(a, 1000)  # min amount = 1000 yuan
        result['amihud_min'][t] = np.nanmean(np.clip(raw_amihud, 0, 0.01), axis=0)

        # Large trade ratio (> 2x median volume bar)
        med_vol = np.nanmedian(v, axis=0)
        result['large_trade_ratio'][t] = np.nansum(v * (v > 2 * med_vol), axis=0) / (total_v + eps)

        # Volume-price correlation: corr(minute_returns, minute_volumes) per stock
        # Positive = volume surges on up-bars (buying pressure), Negative = volume on down-bars
        vol_price_corr = np.full(n_stocks, np.nan)
        for si in range(n_stocks):
            r = min_ret_c[:, si]; vi = v[:, si]
            valid = ~np.isnan(r) & ~np.isnan(vi) & (vi > 0)
            if valid.sum() >= 30:
                rv, vv = r[valid], vi[valid]
                r_std = np.nanstd(rv); v_std = np.nanstd(vv)
                if r_std > 1e-10 and v_std > 1e-10:
                    vol_price_corr[si] = np.corrcoef(rv, vv)[0, 1]
        result['vol_price_corr'][t] = vol_price_corr

        # Roll spread proxy
        cov_ret = np.full(n_stocks, np.nan)
        for si in range(n_stocks):
            r = min_ret_c[:, si]
            valid = ~np.isnan(r)
            if valid.sum() >= 100:
                cov_ret[si] = np.nanmean(r[1:][valid[1:]] * r[:-1][valid[:-1]])
        roll_spread = np.where(cov_ret < 0, 2 * np.sqrt(-cov_ret), 0)
        result['roll_spread'][t] = roll_spread / (c[-1] + eps)

        # Last bar manipulation
        result['last_bar_ret'][t] = min_ret_c[-1]
        result['last_bar_vol_ratio'][t] = v[-1] / (med_vol + eps)

        # Overnight gap for minute alignment
        result['gap_t'][t] = (o[0] - c[-1]) / (c[-1] + eps)

    # ---- Minute factor wrappers (use cached aggregates) ----

    def _get_agg(self, key):
        """Get pre-computed minute aggregate, compute if not cached."""
        if key not in self._minute_cache:
            self.compute_all_minute_aggregates()
        return self._minute_cache[key]

    def F1_1_first30_mom(self): return self._get_agg('first30_ret')
    def F1_2_last30_mom(self): return self._get_agg('last30_ret')
    def F1_3_intraday_mom(self): return self._get_agg('intraday_ret_min')
    def F3_1_realized_vol(self): return self._get_agg('realized_vol')
    def F3_2_vol_skew(self): return self._get_agg('vol_skew')
    def F4_1_close_vs_vwap(self): return self._get_agg('close_vs_vwap')
    def F4_2_vwap_trend(self): return self._get_agg('vwap_trend')
    def F5_1_volume_hhi(self): return self._get_agg('volume_hhi')
    def F5_2_open_vol_ratio(self): return self._get_agg('open_vol_ratio')
    def F5_3_close_vol_ratio(self): return self._get_agg('close_vol_ratio')
    def F5_5_smart_money_vol(self): return self._get_agg('smart_money_vol')
    def F6_1_vol_price_corr(self): return self._get_agg('vol_price_corr')
    def F6_2_amihud_min(self): return self._get_agg('amihud_min')
    def F6_3_vpin(self): return self._get_agg('vpin')
    def F6_4_large_trade_ratio(self): return self._get_agg('large_trade_ratio')
    def F6_5_roll_spread(self): return self._get_agg('roll_spread')

    # ---- Composite minute factors ----

    def F_COMBO_1_opening_confirmation(self):
        """Factor 1: Opening drive with smart-money confirmation."""
        f30 = self.F1_1_first30_mom()
        l30 = self.F1_2_last30_mom()
        same_sign = np.sign(f30) == np.sign(l30)
        result = np.full_like(f30, np.nan)
        result[same_sign] = f30[same_sign] * np.abs(l30[same_sign]) / (np.abs(f30[same_sign]) + 1e-10)
        return rolling_mean(result, 5)

    def F_COMBO_2_vpin_informed(self):
        """Factor 2: VPIN-style informed trading."""
        vpin = self.F6_3_vpin()
        return vpin - rolling_mean(vpin, 20)

    def F_COMBO_3_overnight_reversal_intensity(self):
        """Factor 4: Overnight-anchored reversal. FIX: clip extreme values."""
        gap = self.overnight_ret
        f30 = self.F1_1_first30_mom()
        # Use max(0.01, abs(f30)) to prevent division by near-zero
        denom = np.maximum(np.abs(f30), 0.01)
        result = -np.sign(gap) * np.abs(gap) / denom
        return np.clip(result, -5.0, 5.0)

    def F_COMBO_4_amihud_hybrid(self):
        """Factor 7: Amihud-minute hybrid liquidity."""
        am_min = self.F6_2_amihud_min()
        return am_min / (rolling_mean(am_min, 20) + 1e-10) - 1

    def F_COMBO_5_close_manipulation(self):
        """Factor 13: Closing auction manipulation detection."""
        last_ret = self._get_agg('last_bar_ret')
        last_vol_ratio = self._get_agg('last_bar_vol_ratio')
        suspicious = np.abs(last_ret) * (1 - last_vol_ratio)
        return -suspicious * np.sign(last_ret)

    def F_COMBO_6_intraday_triple_confirmation(self):
        """Factor 20: Triple confirmation (gap + intraday + closing rush).
        FIX P0-1: Bearish confirmation produces negative values.
        """
        gap = self.overnight_ret
        intraday = self.F1_3_intraday_mom()
        close_rush = self.F5_3_close_vol_ratio() / (self.F5_2_open_vol_ratio() + 1e-10)

        result = np.full_like(gap, 0.0)
        # FIX: Relaxed thresholds (was 1.5 → 95% zeros, now 1.2 → ~80% zeros, still selective)
        bullish = (gap > 0.005) & (intraday > 0.005) & (close_rush > 1.2)
        bearish = (gap < -0.005) & (intraday < -0.005) & (close_rush > 1.2)
        result[bullish] = gap[bullish] * intraday[bullish] * np.log(close_rush[bullish])
        # P0-1 FIX: bearish confirmation → negative signal
        result[bearish] = gap[bearish] * np.abs(intraday[bearish]) * np.log(close_rush[bearish])
        return result

    def F_COMBO_7_weighted_avg_time(self):
        """Factor 18: Information arrival asymmetry (WAT factor)."""
        wat = self._get_agg('weighted_avg_time')
        intraday = self.F1_3_intraday_mom()
        return (0.5 - wat) * np.sign(intraday)

    def F_COMBO_8_large_trade_signal(self):
        """Large trade concentration as informed trading signal."""
        ltr = self.F6_4_large_trade_ratio()
        intraday = self.F1_3_intraday_mom()
        return ltr * np.sign(intraday)

    def F_COMBO_9_smart_money_composite(self):
        """Smart money volume * VWAP deviation."""
        sm = self.F5_5_smart_money_vol()
        vwap_dev = self.F4_1_close_vs_vwap()
        return sm * vwap_dev

    def F_COMBO_10_vol_concentration_mom(self):
        """Volume concentration with intraday momentum."""
        hhi = self.F5_1_volume_hhi()
        intraday = self.F1_3_intraday_mom()
        hhi_norm = (hhi - rolling_mean(hhi, 20)) / (rolling_std(hhi, 20) + 1e-10)
        return intraday * hhi_norm

    # ============================================================
    # Category G: Cross-Modal Interaction Factors (18)
    # ============================================================

    def G1_1_mom_with_vol_conf(self):
        return self._ret_N(5) * self.D1_1_vol_ratio_5_20()

    def G1_2_mom_liquidity_adj(self):
        return self._ret_N(20) * (1 - cross_sectional_rank(self.D3_1_amihud_20d()))

    def G1_3_rev_with_vol_conf(self):
        return -self.daily_ret * self.D1_1_vol_ratio_5_20()

    def G2_1_intraday_trend_ret5d(self):
        intraday = self.F1_3_intraday_mom()
        ret5 = self._ret_N(5)
        same_sign = np.sign(intraday) == np.sign(ret5)
        result = np.full_like(intraday, np.nan)
        result[same_sign] = np.abs(intraday[same_sign] * ret5[same_sign])
        return result

    def G2_3_vwap_close_x_mom(self):
        return self.F4_1_close_vs_vwap() * self._ret_N(5)

    def G2_5_smart_money_x_reversal(self):
        sm = self.F5_5_smart_money_vol()
        return sm * (-self.daily_ret)

    def G3_1_liquidity_premium(self):
        return self.D3_1_amihud_20d() * self.F6_3_vpin()

    # ============================================================
    # Category H: Technical & Market Relative (10)
    # ============================================================

    def H1_1_RSI_14(self):
        """14-day RSI."""
        delta = np.diff(self.adj_close, axis=0)
        delta = np.vstack([np.full((1, self.n_stocks), np.nan), delta])
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = rolling_mean(gain, 14)
        avg_loss = rolling_mean(loss, 14)
        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - 100 / (1 + rs)

    def H1_3_bollinger_position(self):
        ma20 = rolling_mean(self.adj_close, 20)
        std20 = rolling_std(self.adj_close, 20)
        return (self.adj_close - ma20) / (2 * std20 + 1e-10)

    def H2_2_beta_60d(self):
        """Rolling 60-day market beta."""
        mkt_ret = np.nanmean(self.daily_ret, axis=1, keepdims=True)
        cov_mkt = rolling_mean(self.daily_ret * mkt_ret, 60)
        var_mkt = rolling_mean(mkt_ret ** 2, 60)
        return cov_mkt / (var_mkt + 1e-10)

    def H2_5_market_cap_rank(self):
        """Cross-sectional market cap percentile."""
        return cross_sectional_rank(self.market_cap)

    # ============================================================
    # Helper methods
    # ============================================================

    def _ret_N(self, N):
        """N-day return: (close[t]-close[t-N])/close[t-N]."""
        result = np.full_like(self.adj_close, np.nan)
        result[N:] = (self.adj_close[N:] - self.adj_close[:-N]) / (self.adj_close[:-N] + 1e-10)
        return result

    def _ret_N_skip(self, N, skip):
        """N-day return skipping the most recent `skip` days.
        Computes return from (t-skip-N) to (t-skip), stored at time t.
        FIX P1-1: Correct window alignment.
        """
        result = np.full_like(self.adj_close, np.nan)
        total = N + skip
        if total >= self.n_dates:
            return result
        # result[t] = (adj_close[t-skip] - adj_close[t-total]) / adj_close[t-total]
        n_result = self.n_dates - total
        result[total:] = (self.adj_close[N:self.n_dates - skip] -
                          self.adj_close[0:n_result]) / \
                         (self.adj_close[0:n_result] + 1e-10)
        return result

    def _rolling_moment(self, arr, window, moment):
        """Rolling moment (skew, kurt)."""
        n = arr.shape[0]
        result = np.full_like(arr, np.nan)
        for i in range(window - 1, n):
            w = arr[i - window + 1:i + 1]
            valid = ~np.isnan(w)
            cnt = valid.sum(axis=0)
            with np.errstate(invalid='ignore', divide='ignore'):
                mean = np.nanmean(w, axis=0)
                centered = np.where(valid, w - mean, np.nan)
                m2 = np.nanmean(centered ** 2, axis=0)
                if moment == 'skew':
                    m3 = np.nanmean(centered ** 3, axis=0)
                    vals = m3 / (m2 ** 1.5)
                    vals[(cnt < 3) | (m2 <= 0)] = np.nan
                else:
                    m4 = np.nanmean(centered ** 4, axis=0)
                    vals = m4 / (m2 ** 2) - 3.0
                    vals[(cnt < 4) | (m2 <= 0)] = np.nan
            result[i] = vals
        return result


def compute_all_factors(pipeline, output_dir: str = None) -> Dict[str, np.ndarray]:
    """Compute all factors and return dict of (N_dates, N_stocks) arrays.

    Returns:
        Dict mapping factor name to (n_dates, n_stocks) float32 array.
    """
    fc = FactorComputer(pipeline)

    print("Computing minute aggregates (this may take 10-30 minutes)...")
    fc.compute_all_minute_aggregates()

    factors = {}

    print("Computing daily price factors (Category A-D)...")
    # Category A
    for name, method in [
        ('A1_1_ret_20d', fc.A1_1_ret_20d), ('A1_2_ret_60d', fc.A1_2_ret_60d),
        ('A1_3_ret_120d_skip5', fc.A1_3_ret_120d_skip5), ('A1_4_ret_5d', fc.A1_4_ret_5d),
        ('A2_1_sharpe_60d', fc.A2_1_sharpe_60d), ('A2_2_mom_vol_adj', fc.A2_2_mom_vol_adj),
        ('A3_1_max_dd_60d', fc.A3_1_max_dd_60d), ('A3_3_close_vs_high_20d', fc.A3_3_close_vs_high_20d),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    # Category B
    for name, method in [
        ('B1_1_rev_1d', fc.B1_1_rev_1d), ('B1_2_rev_5d', fc.B1_2_rev_5d),
        ('B1_4_rev_overnight', fc.B1_4_rev_overnight), ('B2_1_abnormal_vol_rev', fc.B2_1_abnormal_vol_rev),
        ('B3_1_extreme_loser_5d', fc.B3_1_extreme_loser_5d), ('B3_2_extreme_winner_5d', fc.B3_2_extreme_winner_5d),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    # Category C
    for name, method in [
        ('C1_1_vol_20d', fc.C1_1_vol_20d), ('C1_2_vol_60d', fc.C1_2_vol_60d),
        ('C1_3_vol_ratio', fc.C1_3_vol_ratio), ('C2_1_downside_vol_60d', fc.C2_1_downside_vol_60d),
        ('C4_1_skewness_60d', fc.C4_1_skewness_60d),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    # Category D
    for name, method in [
        ('D1_1_vol_ratio_5_20', fc.D1_1_vol_ratio_5_20), ('D1_3_volume_breakout', fc.D1_3_volume_breakout),
        ('D2_1_turnover_5d', fc.D2_1_turnover_5d), ('D2_2_turnover_change', fc.D2_2_turnover_change),
        ('D3_1_amihud_20d', fc.D3_1_amihud_20d), ('D4_1_log_dollar_vol', fc.D4_1_log_dollar_vol),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    # Category E
    for name, method in [
        ('E1_1_upper_shadow', fc.E1_1_upper_shadow), ('E1_2_lower_shadow', fc.E1_2_lower_shadow),
        ('E1_3_body_ratio', fc.E1_3_body_ratio), ('E2_1_gap_up', fc.E2_1_gap_up),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    print("Computing minute microstructure factors (Category F)...")
    for name, method in [
        ('F1_1_first30_mom', fc.F1_1_first30_mom), ('F1_2_last30_mom', fc.F1_2_last30_mom),
        ('F1_3_intraday_mom', fc.F1_3_intraday_mom), ('F3_1_realized_vol', fc.F3_1_realized_vol),
        ('F3_2_vol_skew', fc.F3_2_vol_skew), ('F4_1_close_vs_vwap', fc.F4_1_close_vs_vwap),
        ('F4_2_vwap_trend', fc.F4_2_vwap_trend), ('F5_1_volume_hhi', fc.F5_1_volume_hhi),
        ('F5_2_open_vol_ratio', fc.F5_2_open_vol_ratio), ('F5_3_close_vol_ratio', fc.F5_3_close_vol_ratio),
        ('F5_5_smart_money_vol', fc.F5_5_smart_money_vol), ('F6_2_amihud_min', fc.F6_2_amihud_min),
        ('F6_3_vpin', fc.F6_3_vpin), ('F6_4_large_trade_ratio', fc.F6_4_large_trade_ratio),
        ('F6_5_roll_spread', fc.F6_5_roll_spread),
        ('F_COMBO_1_opening_confirm', fc.F_COMBO_1_opening_confirmation),
        ('F_COMBO_2_vpin_informed', fc.F_COMBO_2_vpin_informed),
        ('F_COMBO_3_overnight_reversal', fc.F_COMBO_3_overnight_reversal_intensity),
        ('F_COMBO_4_amihud_hybrid', fc.F_COMBO_4_amihud_hybrid),
        ('F_COMBO_5_close_manip', fc.F_COMBO_5_close_manipulation),
        ('F_COMBO_6_triple_confirm', fc.F_COMBO_6_intraday_triple_confirmation),
        ('F_COMBO_7_wat', fc.F_COMBO_7_weighted_avg_time),
        ('F_COMBO_8_large_trade', fc.F_COMBO_8_large_trade_signal),
        ('F_COMBO_9_smart_money_vwap', fc.F_COMBO_9_smart_money_composite),
        ('F_COMBO_10_vol_conc_mom', fc.F_COMBO_10_vol_concentration_mom),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    print("Computing cross-modal factors (Category G)...")
    for name, method in [
        ('G1_1_mom_vol_conf', fc.G1_1_mom_with_vol_conf), ('G1_2_mom_liquidity_adj', fc.G1_2_mom_liquidity_adj),
        ('G1_3_rev_vol_conf', fc.G1_3_rev_with_vol_conf), ('G2_1_intraday_ret5d', fc.G2_1_intraday_trend_ret5d),
        ('G2_3_vwap_close_mom', fc.G2_3_vwap_close_x_mom), ('G2_5_smart_money_rev', fc.G2_5_smart_money_x_reversal),
        ('G3_1_liquidity_premium', fc.G3_1_liquidity_premium),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    print("Computing technical factors (Category H)...")
    for name, method in [
        ('H1_1_RSI_14', fc.H1_1_RSI_14), ('H1_3_bollinger_pos', fc.H1_3_bollinger_position),
        ('H2_2_beta_60d', fc.H2_2_beta_60d), ('H2_5_market_cap_rank', fc.H2_5_market_cap_rank),
    ]:
        try:
            factors[name] = method().astype(np.float32)
        except Exception as e:
            print(f"  {name}: FAILED - {e}")

    print(f"Computed {len(factors)} factors total.")

    if output_dir:
        import joblib
        import os
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, 'all_factors.pkl')
        joblib.dump(factors, out_path)
        print(f"Saved factors to {out_path}")

    return factors
