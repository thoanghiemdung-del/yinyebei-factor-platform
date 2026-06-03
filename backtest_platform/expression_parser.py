"""Simple WQ-style expression parser for factor backtesting."""
import threading
import numpy as np
import re

# ---- Module-level cache for derived fields (lazily computed, one pipeline) ----
_derived_cache = {}

# ---- Internal batch cache for minute-derived fields ----
# Stores (pipeline_id, dict_of_arrays) to avoid recomputing across different field requests.
_minute_batch_cache = None
_minute_cache_lock = threading.Lock()


def _cached_derive(key: str, compute_fn, pipeline) -> np.ndarray:
    """Return a copy of the cached derived field, computing it on first access."""
    cache_key = (id(pipeline), key)
    if cache_key not in _derived_cache:
        _derived_cache[cache_key] = compute_fn(pipeline).astype(np.float32)
    return _derived_cache[cache_key].copy()


# ---- Batch minute-derived field computation ----

def _compute_all_minute_derived(pipeline) -> dict:
    """Compute all 8 minute-derived fields in a single pass over minute .mat files.

    Returns a dict with keys:
        morning_return, afternoon_return, first30min_return, last30min_return,
        body_return, intraday_volatility, upper_shadow_pct, lower_shadow_pct.

    Each value is a (n_dates, n_stocks) float32 array with NaN for dates that
    have no corresponding minute file.

    Results are cached internally by pipeline id — subsequent calls are O(1).
    """
    global _minute_batch_cache

    pid = id(pipeline)
    if _minute_batch_cache is not None and _minute_batch_cache[0] == pid:
        return _minute_batch_cache[1]
    _minute_cache_lock.acquire()
    if _minute_batch_cache is not None and _minute_batch_cache[0] == pid:
        _minute_cache_lock.release()
        return _minute_batch_cache[1]

    n_dates, n_stocks = pipeline.n_dates, pipeline.n_stocks

    # Pre-allocate all fields as NaN (must be OUTSIDE the loop!)
    result = {
        'morning_return':       np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'afternoon_return':     np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'first30min_return':    np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'last30min_return':     np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'body_return':          np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'intraday_volatility':  np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'upper_shadow_pct':     np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'lower_shadow_pct':     np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        # 6 innovative minute-derived fields — pre-allocate here, fill inside loop
        'price_efficiency':     np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'vwap':                 np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'vwap_gap':             np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'volume_concentration': np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'am_pm_divergence':     np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
        'close_location':       np.full((n_dates, n_stocks), np.nan, dtype=np.float32),
    }

    minute_dates = pipeline.get_minute_dates()
    eps = np.float32(1e-10)

    for date_str in minute_dates:
        # Convert YYYYMMDD -> YYYY-MM-DD for pipeline.date_to_idx lookup
        date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        if date_formatted not in pipeline.date_to_idx:
            continue

        t = pipeline.date_to_idx[date_formatted]

        # Load and align minute data for this day
        try:
            md = pipeline.load_minute_day(date_str)
            aligned = pipeline.align_minute_to_daily(md, t)
        except (FileNotFoundError, ValueError, KeyError):
            continue

        O = aligned['OPEN']    # (N_bars, n_stocks) float32
        H = aligned['HIGH']
        L = aligned['LOW']
        C = aligned['CLOSE']

        N = O.shape[0]  # number of minute bars (242 for full days)

        # ---- Extract daily-level OHLC from minute bars ----
        first_open  = O[0]                     # (n_stocks,)
        last_close  = C[-1]                    # (n_stocks,)
        high_day    = np.nanmax(H, axis=0)     # (n_stocks,)
        low_day     = np.nanmin(L, axis=0)     # (n_stocks,)

        # ---- Session midpoints ----
        mid         = N // 2                # first afternoon bar index
        morning_end = mid - 1               # last morning bar index
        mid_open    = O[mid]                # OPEN of first afternoon bar
        morning_close = C[morning_end]      # CLOSE of last morning bar

        f30_idx     = min(30, N)            # bar count for approx 30th minute
        l30_idx     = max(0, N - 30)        # start index for last 30 min

        f30_close   = C[f30_idx - 1]        # bar index of 30th bar (0-indexed)
        l30_open    = O[l30_idx]            # OPEN of first bar in last 30 min

        # ---- Compute all 8 fields for this day ----
        result['morning_return'][t]      = (morning_close - first_open) / (first_open + eps)
        result['afternoon_return'][t]    = (last_close - mid_open) / (mid_open + eps)
        result['first30min_return'][t]   = (f30_close - first_open) / (first_open + eps)
        result['last30min_return'][t]    = (last_close - l30_open) / (l30_open + eps)

        result['body_return'][t]         = (last_close - first_open) / (first_open + eps)

        result['intraday_volatility'][t] = (high_day - low_day) / (first_open + eps)

        body_top    = np.maximum(first_open, last_close)
        result['upper_shadow_pct'][t]    = (high_day - body_top) / (body_top + eps)

        body_bottom = np.minimum(first_open, last_close)
        result['lower_shadow_pct'][t]    = (body_bottom - low_day) / (body_bottom + eps)

        # ---- Innovative minute-derived fields (6 new: 分钟数据创新糅合) ----
        hl_range = high_day - low_day
        # [1] price_efficiency: |close-open|/(high-low), 趋势效率越高方向性越强
        result['price_efficiency'][t]   = np.abs(last_close - first_open) / (hl_range + eps)
        # [2] vwap_gap: (close-VWAP)/VWAP, 高于VWAP=买方主导=机构流入证据
        vol_b = np.nan_to_num(aligned.get('VOLUME', np.ones_like(C)))
        vwap = np.nansum(C * vol_b, axis=0) / (np.nansum(vol_b, axis=0) + eps)
        result['vwap'][t]               = vwap
        result['vwap_gap'][t]           = (last_close - vwap) / (vwap + eps)
        # [3] volume_concentration: HHI of minute volumes, 大单集中=机构行为信号
        total_vol = np.nansum(vol_b, axis=0) + eps
        vol_share = vol_b / total_vol
        result['volume_concentration'][t] = np.nansum(vol_share * vol_share, axis=0)
        # [4] am_pm_divergence: morning*afternoon, 负=盘中反转, 正=信息连续消化
        am_ret = (morning_close - first_open) / (first_open + eps)
        pm_ret = (last_close - mid_open) / (mid_open + eps)
        result['am_pm_divergence'][t]   = am_ret * pm_ret
        # [5] close_location: (close-low)/(high-low), 高位收盘=买方控制全天
        result['close_location'][t]     = (last_close - low_day) / (hl_range + eps)

    _minute_batch_cache = (pid, result)
    _minute_cache_lock.release()
    return result


# ---- Individual derived field compute functions ----
# Each is a thin wrapper that calls the batch computation and extracts its field.
# The existing _cached_derive mechanism then caches each field individually.

def _compute_morning_return(pipeline) -> np.ndarray:
    """Morning session return: (midpoint close - open) / open, from real minute data."""
    return _compute_all_minute_derived(pipeline)['morning_return']


def _compute_afternoon_return(pipeline) -> np.ndarray:
    """Afternoon session return: (close - midpoint close) / midpoint close, from real minute data."""
    return _compute_all_minute_derived(pipeline)['afternoon_return']


def _compute_first30min_return(pipeline) -> np.ndarray:
    """First 30-minute return: (30min close - open) / open, from real minute data."""
    return _compute_all_minute_derived(pipeline)['first30min_return']


def _compute_last30min_return(pipeline) -> np.ndarray:
    """Last 30-minute return: (close - last30min open) / last30min open, from real minute data."""
    return _compute_all_minute_derived(pipeline)['last30min_return']


def _compute_body_return(pipeline) -> np.ndarray:
    """Candlestick body return: (close - open) / open, from real minute data."""
    return _compute_all_minute_derived(pipeline)['body_return']


def _compute_upper_shadow_pct(pipeline) -> np.ndarray:
    """Upper shadow %: (day high - max(open,close)) / max(open,close), from real minute data."""
    return _compute_all_minute_derived(pipeline)['upper_shadow_pct']


def _compute_lower_shadow_pct(pipeline) -> np.ndarray:
    """Lower shadow %: (min(open,close) - day low) / min(open,close), from real minute data."""
    return _compute_all_minute_derived(pipeline)['lower_shadow_pct']


def _compute_intraday_volatility(pipeline) -> np.ndarray:
    """Intraday range: (day high - day low) / open, from real minute data."""
    return _compute_all_minute_derived(pipeline)['intraday_volatility']


# ---- Innovative minute-derived field wrappers (5 new: 分钟数据创新糅合) ----

def _compute_price_efficiency(pipeline) -> np.ndarray:
    """Price efficiency: |close-open|/(high-low). Higher = stronger intraday trend direction."""
    return _compute_all_minute_derived(pipeline)['price_efficiency']


def _compute_vwap(pipeline) -> np.ndarray:
    """Raw VWAP: Volume-Weighted Average Price computed from minute bars."""
    return _compute_all_minute_derived(pipeline)['vwap']


def _compute_vwap_gap(pipeline) -> np.ndarray:
    """VWAP gap: (close-VWAP)/VWAP. Positive = buyer dominance = institutional inflow evidence."""
    return _compute_all_minute_derived(pipeline)['vwap_gap']


def _compute_volume_concentration(pipeline) -> np.ndarray:
    """Volume HHI concentration. High = block trades concentrated in few bars = institutional signal."""
    return _compute_all_minute_derived(pipeline)['volume_concentration']


def _compute_am_pm_divergence(pipeline) -> np.ndarray:
    """AM-PM divergence: morning*afternoon. Negative = intraday reversal, positive = continuous digestion."""
    return _compute_all_minute_derived(pipeline)['am_pm_divergence']


def _compute_close_location(pipeline) -> np.ndarray:
    """Close location: (close-low)/(high-low). >0.7 = buyer control, <0.3 = seller dominance."""
    return _compute_all_minute_derived(pipeline)['close_location']


# ---- Daily-only derived fields (no minute data needed) ----

def _compute_auction_return(pipeline) -> np.ndarray:
    """Auction (overnight gap) return: (open - preclose) / preclose."""
    o = pipeline.fields['I_D_OPEN_ORI']
    pc = pipeline.fields['I_D_PRECLOSE_ORI']
    return (o - pc) / (pc + np.float32(1e-10))


def _compute_volume_profile_ratio(pipeline) -> np.ndarray:
    """Volume relative to 20-day moving average: volume / ts_mean(volume, 20)."""
    vol = pipeline.fields['I_D_VOLUME']
    n_dates = vol.shape[0]
    result = np.full_like(vol, np.nan)
    window = 20
    for i in range(window - 1, n_dates):
        denom = np.nanmean(vol[i - window + 1:i + 1], axis=0)
        result[i] = vol[i] / (denom + np.float32(1e-10))
    return result


def _compute_returns(pipeline) -> np.ndarray:
    """Daily return: close / preclose - 1."""
    c = pipeline.fields['I_D_CLOSE_ORI']
    pc = pipeline.fields['I_D_PRECLOSE_ORI']
    return c / (pc + np.float32(1e-10)) - 1.0


def _compute_turnover_rate(pipeline) -> np.ndarray:
    """Turnover rate: volume / free_shares."""
    vol = pipeline.fields['I_D_VOLUME']
    free_shares = pipeline.fields.get(
        'I_D_SHARE_FREESHARES',
        np.ones_like(vol)
    )
    return vol / (free_shares + np.float32(1e-10))


def _rolling_mean(arr, window):
    result = np.full_like(arr, np.nan, dtype=np.float32)
    for i in range(window - 1, arr.shape[0]):
        result[i] = np.nanmean(arr[i - window + 1:i + 1], axis=0)
    return result.astype(np.float32, copy=False)


def _rolling_std(arr, window):
    result = np.full_like(arr, np.nan, dtype=np.float32)
    for i in range(window - 1, arr.shape[0]):
        result[i] = np.nanstd(arr[i - window + 1:i + 1], axis=0)
    return result.astype(np.float32, copy=False)


def _compute_ret_nd(pipeline, n):
    c = pipeline.fields['I_D_CLOSE_ORI']
    r = np.full_like(c, np.nan, dtype=np.float32)
    r[n:] = c[n:] / (c[:-n] + np.float32(1e-10)) - np.float32(1)
    return r


def _compute_ret_5d(pipeline): return _compute_ret_nd(pipeline, 5)
def _compute_ret_20d(pipeline): return _compute_ret_nd(pipeline, 20)
def _compute_ret_60d(pipeline): return _compute_ret_nd(pipeline, 60)


def _compute_ret_120d_skip5(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    r = np.full_like(c, np.nan, dtype=np.float32)
    r[125:] = c[120:-5] / (c[:-125] + np.float32(1e-10)) - np.float32(1)
    return r


def _compute_vol_20d(pipeline): return _rolling_std(_compute_returns(pipeline), 20)
def _compute_vol_60d(pipeline): return _rolling_std(_compute_returns(pipeline), 60)


def _compute_vol_ratio(pipeline):
    return _compute_vol_20d(pipeline) / (_compute_vol_60d(pipeline) + np.float32(1e-10))


def _compute_downside_vol_60d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan, dtype=np.float32)
    for i in range(59, ret.shape[0]):
        w = ret[i - 59:i + 1]
        r[i] = np.nanstd(np.where(w < 0, w, np.nan), axis=0)
    return r


def _compute_sharpe_60d(pipeline):
    ret = _compute_returns(pipeline)
    return _rolling_mean(ret, 60) / (_rolling_std(ret, 60) + np.float32(1e-10))


def _compute_mom_vol_adj(pipeline):
    return _compute_ret_60d(pipeline) / (np.float32(1) + _compute_vol_60d(pipeline))


def _compute_rev_1d(pipeline): return -_compute_returns(pipeline)
def _compute_rev_5d(pipeline): return -_compute_ret_5d(pipeline)
def _compute_rev_overnight(pipeline): return -_compute_auction_return(pipeline)


def _compute_abnormal_vol_rev(pipeline):
    return -_compute_returns(pipeline) * _compute_volume_profile_ratio(pipeline)


def _compute_turnover_5d(pipeline): return _rolling_mean(_compute_turnover_rate(pipeline), 5)


def _compute_amihud_20d(pipeline):
    raw = np.abs(_compute_returns(pipeline)) / (pipeline.fields['I_D_AMOUNT'] + np.float32(1e-10))
    return _rolling_mean(raw, 20)


def _compute_log_dollar_vol(pipeline):
    return np.log1p(np.nan_to_num(pipeline.fields['I_D_AMOUNT'], nan=0.0)).astype(np.float32)


def _compute_rsi_14(pipeline):
    ret = _compute_returns(pipeline)
    gain = np.where(ret > 0, ret, 0).astype(np.float32)
    loss = np.where(ret < 0, -ret, 0).astype(np.float32)
    rs = _rolling_mean(gain, 14) / (_rolling_mean(loss, 14) + np.float32(1e-10))
    return (np.float32(100) - np.float32(100) / (np.float32(1) + rs)).astype(np.float32)


def _compute_bollinger_pos(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    ma = _rolling_mean(c, 20)
    std = _rolling_std(c, 20)
    return ((c - ma) / (np.float32(2) * std + np.float32(1e-10))).astype(np.float32)


def _compute_market_cap_rank(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    shares = pipeline.fields.get('I_D_TOTAL_SHARES', np.ones_like(c))
    cap = c * shares
    result = np.full_like(cap, np.nan, dtype=np.float32)
    for t in range(cap.shape[0]):
        row = cap[t]
        valid = np.isfinite(row)
        if valid.sum() < 10:
            continue
        order = np.argsort(row[valid])
        ranks = np.empty(valid.sum(), dtype=np.float32)
        ranks[order] = (np.arange(valid.sum(), dtype=np.float32) + 1) / valid.sum()
        result[t, valid] = ranks
    return result


def _compute_beta_60d(pipeline):
    ret = _compute_returns(pipeline)
    result = np.full_like(ret, np.nan, dtype=np.float32)
    for i in range(59, ret.shape[0]):
        w = ret[i - 59:i + 1]
        mkt = np.nanmean(w, axis=1)
        mkt_mu = np.nanmean(mkt)
        mkt_dm = mkt - mkt_mu
        var = np.nanmean(mkt_dm * mkt_dm) + np.float32(1e-10)
        stock_mu = np.nanmean(w, axis=0)
        cov = np.nanmean((w - stock_mu) * mkt_dm[:, None], axis=0)
        result[i] = cov / var
    return result


def _compute_upper_shadow(pipeline):
    o = pipeline.fields['I_D_OPEN_ORI']; c = pipeline.fields['I_D_CLOSE_ORI']
    h = pipeline.fields['I_D_HIGH_ORI']; l = pipeline.fields['I_D_LOW_ORI']
    return (h - np.maximum(o, c)) / (h - l + np.float32(1e-10))


def _compute_lower_shadow(pipeline):
    o = pipeline.fields['I_D_OPEN_ORI']; c = pipeline.fields['I_D_CLOSE_ORI']
    h = pipeline.fields['I_D_HIGH_ORI']; l = pipeline.fields['I_D_LOW_ORI']
    return (np.minimum(o, c) - l) / (h - l + np.float32(1e-10))


def _compute_body_ratio(pipeline):
    o = pipeline.fields['I_D_OPEN_ORI']; c = pipeline.fields['I_D_CLOSE_ORI']
    h = pipeline.fields['I_D_HIGH_ORI']; l = pipeline.fields['I_D_LOW_ORI']
    return np.abs(c - o) / (h - l + np.float32(1e-10))


def _compute_gap_up(pipeline): return _compute_auction_return(pipeline)




# ---- New derived fields (batch-injected) ----

def _compute_ret_10d(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    r = np.full_like(c, np.nan)
    r[10:] = c[10:] / c[:-10] - 1
    return r

def _compute_ret_40d(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    r = np.full_like(c, np.nan)
    r[40:] = c[40:] / c[:-40] - 1
    return r

def _compute_vol_5d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(4, ret.shape[0]):
        r[i] = np.nanstd(ret[i-4:i+1], axis=0)
    return r

def _compute_vol_10d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(9, ret.shape[0]):
        r[i] = np.nanstd(ret[i-9:i+1], axis=0)
    return r

def _compute_vol_40d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(39, ret.shape[0]):
        r[i] = np.nanstd(ret[i-39:i+1], axis=0)
    return r

def _compute_vol_120d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(119, ret.shape[0]):
        r[i] = np.nanstd(ret[i-119:i+1], axis=0)
    return r

def _compute_upside_vol_60d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(59, ret.shape[0]):
        w = ret[i-59:i+1].copy()
        w[w < 0] = np.nan
        r[i] = np.nanstd(w, axis=0)
    return r

def _compute_down_up_vol_ratio(pipeline):
    return _compute_downside_vol_60d(pipeline) / (_compute_upside_vol_60d(pipeline) + np.float32(1e-10))

def _compute_adv5(pipeline):
    v = pipeline.fields['I_D_VOLUME']
    r = np.full_like(v, np.nan)
    for i in range(4, v.shape[0]):
        r[i] = np.nanmean(v[i-4:i+1], axis=0)
    return r

def _compute_adv20(pipeline):
    v = pipeline.fields['I_D_VOLUME']
    r = np.full_like(v, np.nan)
    for i in range(19, v.shape[0]):
        r[i] = np.nanmean(v[i-19:i+1], axis=0)
    return r

def _compute_dollar_volume(pipeline):
    return pipeline.fields['I_D_CLOSE_ORI'] * pipeline.fields['I_D_VOLUME']

def _compute_gap_down(pipeline):
    o = pipeline.fields['I_D_OPEN_ORI']
    pc = pipeline.fields['I_D_PRECLOSE_ORI']
    return np.maximum(np.float32(0), pc - o) / (pc + np.float32(1e-10))

def _compute_close_vs_low_20d(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    r = np.full_like(c, np.nan)
    for i in range(19, c.shape[0]):
        r[i] = c[i] / (np.nanmin(pipeline.fields['I_D_LOW_ORI'][i-19:i+1], axis=0) + np.float32(1e-10))
    return r

def _compute_doji_score(pipeline):
    o = pipeline.fields['I_D_OPEN_ORI']
    c = pipeline.fields['I_D_CLOSE_ORI']
    h = pipeline.fields['I_D_HIGH_ORI']
    l = pipeline.fields['I_D_LOW_ORI']
    return np.float32(1) - np.abs(c - o) / (h - l + np.float32(1e-10))

def _compute_cumret_5d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(4, ret.shape[0]):
        r[i] = np.nanprod(np.float64(1) + ret[i-4:i+1], axis=0).astype(np.float32) - np.float32(1)
    return r

def _compute_max_ret_20d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(19, ret.shape[0]):
        r[i] = np.nanmax(ret[i-19:i+1], axis=0)
    return r

def _compute_min_ret_20d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(19, ret.shape[0]):
        r[i] = np.nanmin(ret[i-19:i+1], axis=0)
    return r

def _compute_hit_rate_20d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(19, ret.shape[0]):
        r[i] = np.nanmean(ret[i-19:i+1] > np.float32(0), axis=0)
    return r

def _compute_hit_rate_60d(pipeline):
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(59, ret.shape[0]):
        r[i] = np.nanmean(ret[i-59:i+1] > np.float32(0), axis=0)
    return r

def _compute_rev_10d(pipeline):
    return -_compute_ret_10d(pipeline)

def _compute_rev_20d(pipeline):
    return -_compute_ret_20d(pipeline)

def _compute_skewness_20d(pipeline):
    cache = getattr(pipeline, '_computed_factor_cache', None)
    if cache is None:
        cache = {}
        setattr(pipeline, '_computed_factor_cache', cache)
    if 'skewness_20d' in cache:
        return cache['skewness_20d']
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(19, ret.shape[0]):
        w = ret[i-19:i+1]
        valid = ~np.isnan(w)
        cnt = valid.sum(axis=0)
        with np.errstate(invalid='ignore', divide='ignore'):
            mean = np.nanmean(w, axis=0)
            centered = np.where(valid, w - mean, np.nan)
            m2 = np.nanmean(centered ** 2, axis=0)
            m3 = np.nanmean(centered ** 3, axis=0)
            vals = m3 / (m2 ** 1.5)
        vals[(cnt < 10) | (m2 <= 0)] = np.nan
        r[i] = vals
    cache['skewness_20d'] = r
    return r

def _compute_kurtosis_60d(pipeline):
    cache = getattr(pipeline, '_computed_factor_cache', None)
    if cache is None:
        cache = {}
        setattr(pipeline, '_computed_factor_cache', cache)
    if 'kurtosis_60d' in cache:
        return cache['kurtosis_60d']
    ret = _compute_returns(pipeline)
    r = np.full_like(ret, np.nan)
    for i in range(59, ret.shape[0]):
        w = ret[i-59:i+1]
        valid = ~np.isnan(w)
        cnt = valid.sum(axis=0)
        with np.errstate(invalid='ignore', divide='ignore'):
            mean = np.nanmean(w, axis=0)
            centered = np.where(valid, w - mean, np.nan)
            m2 = np.nanmean(centered ** 2, axis=0)
            m4 = np.nanmean(centered ** 4, axis=0)
            vals = m4 / (m2 ** 2) - np.float32(3)
        vals[(cnt < 10) | (m2 <= 0)] = np.nan
        r[i] = vals
    cache['kurtosis_60d'] = r
    return r

def _compute_vol_ratio_5_20(pipeline):
    v = pipeline.fields['I_D_VOLUME']
    ma5 = np.full_like(v, np.nan)
    ma20 = np.full_like(v, np.nan)
    for i in range(4, v.shape[0]):
        ma5[i] = np.nanmean(v[i-4:i+1], axis=0)
    for i in range(19, v.shape[0]):
        ma20[i] = np.nanmean(v[i-19:i+1], axis=0)
    return ma5 / (ma20 + np.float32(1e-10))

def _compute_vol_ratio_20_60(pipeline):
    return _compute_vol_20d(pipeline) / (_compute_vol_60d(pipeline) + np.float32(1e-10))

def _compute_bollinger_width(pipeline):
    c = pipeline.fields['I_D_CLOSE_ORI']
    r = np.full_like(c, np.nan)
    for i in range(19, c.shape[0]):
        ma = np.nanmean(c[i-19:i+1], axis=0)
        std = np.nanstd(c[i-19:i+1], axis=0)
        r[i] = np.float32(4) * std / (ma + np.float32(1e-10))
    return r

def _compute_intraday_reversal(pipeline):
    return -_compute_first30min_return(pipeline) * _compute_last30min_return(pipeline)

def _compute_rev_vol_regime(pipeline):
    return _compute_rev_5d(pipeline) * _compute_vol_20d(pipeline)

def _compute_volume_price_div(pipeline):
    return _compute_returns(pipeline) * _compute_volume_trend_20d(pipeline)

def _compute_gap_momentum(pipeline):
    return _compute_auction_return(pipeline) * _compute_returns(pipeline)

def _compute_amount_volatility(pipeline):
    v = pipeline.fields['I_D_AMOUNT']
    r = np.full_like(v, np.nan)
    for i in range(19, v.shape[0]):
        r[i] = np.nanstd(v[i-19:i+1], axis=0) / (np.nanmean(v[i-19:i+1], axis=0) + 1e-10)
    return r

def _compute_volume_price_corr(pipeline):
    cache = getattr(pipeline, '_computed_factor_cache', None)
    if cache is None:
        cache = {}
        setattr(pipeline, '_computed_factor_cache', cache)
    if 'volume_price_corr' in cache:
        return cache['volume_price_corr']
    v = pipeline.fields['I_D_VOLUME']
    ret = _compute_returns(pipeline)
    r = np.full_like(v, np.nan)
    for i in range(19, v.shape[0]):
        vw = v[i-19:i+1]
        rw = ret[i-19:i+1]
        valid = ~np.isnan(vw) & ~np.isnan(rw)
        cnt = valid.sum(axis=0)
        x = np.where(valid, vw, 0.0)
        y = np.where(valid, rw, 0.0)
        mx = x.sum(axis=0) / np.maximum(cnt, 1)
        my = y.sum(axis=0) / np.maximum(cnt, 1)
        dx = np.where(valid, vw - mx, 0.0)
        dy = np.where(valid, rw - my, 0.0)
        denom = np.sqrt((dx * dx).sum(axis=0) * (dy * dy).sum(axis=0))
        vals = (dx * dy).sum(axis=0) / (denom + 1e-10)
        vals[(cnt < 10) | (denom <= 0)] = np.nan
        r[i] = vals
    cache['volume_price_corr'] = r
    return r

def _compute_volume_trend_20d(pipeline):
    cache = getattr(pipeline, '_computed_factor_cache', None)
    if cache is None:
        cache = {}
        setattr(pipeline, '_computed_factor_cache', cache)
    if 'volume_trend_20d' in cache:
        return cache['volume_trend_20d']
    v = pipeline.fields['I_D_VOLUME']
    r = np.full_like(v, np.nan)
    pos = np.arange(20).reshape(-1, 1)
    cols = np.arange(v.shape[1])
    for i in range(19, v.shape[0]):
        w = v[i-19:i+1]
        valid = ~np.isnan(w)
        cnt = valid.sum(axis=0)
        last_pos = np.where(valid, pos, -1).max(axis=0)
        has_value = last_pos >= 0
        last_val = np.full(v.shape[1], np.nan, dtype=v.dtype)
        last_val[has_value] = w[last_pos[has_value], cols[has_value]]
        less = ((w < last_val) & valid).sum(axis=0)
        equal = ((w == last_val) & valid).sum(axis=0)
        vals = (less + (equal + 1) / 2) / np.maximum(cnt, 1)
        vals[(cnt < 5) | (~has_value)] = np.nan
        r[i] = vals
    cache['volume_trend_20d'] = r
    return r

# ---- Registry: maps field name -> compute function (takes pipeline, returns array) ----
DERIVED_FIELD_REGISTRY = {
    'morning_return':       _compute_morning_return,
    'afternoon_return':     _compute_afternoon_return,
    'first30min_return':    _compute_first30min_return,
    'last30min_return':     _compute_last30min_return,
    'body_return':          _compute_body_return,
    'upper_shadow_pct':     _compute_upper_shadow_pct,
    'lower_shadow_pct':     _compute_lower_shadow_pct,
    'returns':              _compute_returns,
    'auction_return':       _compute_auction_return,
    'intraday_volatility':  _compute_intraday_volatility,
    'volume_profile_ratio': _compute_volume_profile_ratio,
    'turnover_rate':        _compute_turnover_rate,
    'ret_5d':               _compute_ret_5d,
    'ret_20d':              _compute_ret_20d,
    'ret_60d':              _compute_ret_60d,
    'ret_120d_skip5':       _compute_ret_120d_skip5,
    'sharpe_60d':           _compute_sharpe_60d,
    'mom_vol_adj':          _compute_mom_vol_adj,
    'rev_1d':               _compute_rev_1d,
    'rev_5d':               _compute_rev_5d,
    'rev_overnight':        _compute_rev_overnight,
    'abnormal_vol_rev':     _compute_abnormal_vol_rev,
    'vol_20d':              _compute_vol_20d,
    'vol_60d':              _compute_vol_60d,
    'vol_ratio':            _compute_vol_ratio,
    'downside_vol_60d':     _compute_downside_vol_60d,
    'turnover_5d':          _compute_turnover_5d,
    'amihud_20d':           _compute_amihud_20d,
    'log_dollar_vol':       _compute_log_dollar_vol,
    'rsi_14':               _compute_rsi_14,
    'bollinger_pos':        _compute_bollinger_pos,
    'beta_60d':             _compute_beta_60d,
    'market_cap_rank':      _compute_market_cap_rank,
    'upper_shadow':         _compute_upper_shadow,
    'lower_shadow':         _compute_lower_shadow,
    'body_ratio':           _compute_body_ratio,
    'gap_up':               _compute_gap_up,
    # Innovative minute-derived (5 fields)
    'price_efficiency':     _compute_price_efficiency,
    'vwap':                 _compute_vwap,
    'vwap_gap':             _compute_vwap_gap,
    'volume_concentration': _compute_volume_concentration,
    'am_pm_divergence':     _compute_am_pm_divergence,
    'close_location':       _compute_close_location,
    'ret_10d':              _compute_ret_10d,
    'ret_40d':              _compute_ret_40d,
    'vol_5d':               _compute_vol_5d,
    'vol_10d':              _compute_vol_10d,
    'vol_40d':              _compute_vol_40d,
    'vol_120d':             _compute_vol_120d,
    'upside_vol_60d':       _compute_upside_vol_60d,
    'down_up_vol_ratio':    _compute_down_up_vol_ratio,
    'adv5':                 _compute_adv5,
    'adv20':                _compute_adv20,
    'dollar_volume':        _compute_dollar_volume,
    'gap_down':             _compute_gap_down,
    'close_vs_low_20d':     _compute_close_vs_low_20d,
    'doji_score':           _compute_doji_score,
    'cumret_5d':            _compute_cumret_5d,
    'max_ret_20d':          _compute_max_ret_20d,
    'min_ret_20d':          _compute_min_ret_20d,
    'hit_rate_20d':         _compute_hit_rate_20d,
    'hit_rate_60d':         _compute_hit_rate_60d,
    'rev_10d':              _compute_rev_10d,
    'rev_20d':              _compute_rev_20d,
    'skewness_20d':         _compute_skewness_20d,
    'kurtosis_60d':         _compute_kurtosis_60d,
    'vol_ratio_5_20':       _compute_vol_ratio_5_20,
    'vol_ratio_20_60':      _compute_vol_ratio_20_60,
    'bollinger_width':      _compute_bollinger_width,
    'intraday_reversal':    _compute_intraday_reversal,
    'rev_vol_regime':       _compute_rev_vol_regime,
    'volume_price_div':     _compute_volume_price_div,
    'gap_momentum':         _compute_gap_momentum,
    'amount_volatility':    _compute_amount_volatility,
    'volume_price_corr':    _compute_volume_price_corr,
    'volume_trend_20d':     _compute_volume_trend_20d,
}


# ---- Field metadata registry (for /api/datafields) ----
FIELDS_METADATA = {
    # Return
    'returns':       {'chinese_name': '日收益率', 'category': '收益类',
                      'description': '当日涨跌幅，close/preclose-1，最基础的日频收益指标',
                      'calculation': 'close / preclose - 1'},
    # Price
    'close': {'chinese_name': '收盘价', 'category': '价格类', 'description': '日收盘价（后复权）',
                      'calculation': '取自原始数据 I_D_CLOSE_ORI'},
    'open': {'chinese_name': '开盘价', 'category': '价格类', 'description': '日开盘价（后复权）',
                      'calculation': '取自原始数据 I_D_OPEN_ORI'},
    'high': {'chinese_name': '最高价', 'category': '价格类', 'description': '日最高价（后复权）',
                      'calculation': '取自原始数据 I_D_HIGH_ORI'},
    'low': {'chinese_name': '最低价', 'category': '价格类', 'description': '日最低价（后复权）',
                      'calculation': '取自原始数据 I_D_LOW_ORI'},
    'preclose': {'chinese_name': '前收盘价', 'category': '价格类', 'description': '前日收盘价（后复权）',
                      'calculation': '取自原始数据 I_D_PRECLOSE_ORI'},
    # Return
    'morning_return': {'chinese_name': '上午收益率', 'category': '收益类',
                             'description': '上午实际涨幅（基于分钟数据），反映早盘动量方向。上午收盘价相对开盘价的涨跌幅',
                             'calculation': '(C[mid-1] - O[0]) / O[0]，mid=N//2为午后首根bar，mid-1即上午最后一根bar，使用真实分钟收盘价精确计算'},
    'afternoon_return': {'chinese_name': '下午收益率', 'category': '收益类',
                             'description': '午后实际涨幅（基于分钟数据），反映尾盘方向性。午后开盘到全天收盘的涨跌幅',
                             'calculation': '(C[-1] - O[mid]) / O[mid]，mid=N//2为午后首根bar，使用午后首笔OPEN而非上午收盘CLOSE以反映午休跳空'},
    'first30min_return': {'chinese_name': '开盘30分钟收益率', 'category': '收益类',
                             'description': '开盘约30分钟实际涨幅（基于分钟数据），反映开盘动量与隔夜信息消化速度',
                             'calculation': '(C[min(30,N)] - O[0]) / O[0]，取第30根分钟bar收盘价，精确对应开盘30分钟'},
    'last30min_return': {'chinese_name': '尾盘30分钟收益率', 'category': '收益类',
                             'description': '尾盘最后30分钟实际涨幅（基于分钟数据），反映机构收盘定价行为和次日预期',
                             'calculation': '(C[-1] - O[max(0,N-30)]) / O[max(0,N-30)]，使用最后30根bar的首笔OPEN精确计算'},
    'body_return': {'chinese_name': '实体收益率', 'category': '收益类',
                             'description': '日K线实体实际涨幅（基于分钟首尾价），反映日内方向性',
                             'calculation': '(CLOSE[-1] - OPEN[0]) / OPEN[0]，分钟数据精确计算'},
    'auction_return': {'chinese_name': '集合竞价收益率', 'category': '收益类',
                             'description': '集合竞价涨幅（隔夜跳空），反映隔夜信息冲击',
                             'calculation': '(open - preclose) / preclose'},
    # Liquidity
    'volume': {'chinese_name': '成交量', 'category': '量价类',
                             'description': '日成交量（股）',
                             'calculation': '取自原始数据 I_D_VOLUME'},
    'amount': {'chinese_name': '成交额', 'category': '量价类',
                             'description': '日成交额（元）',
                             'calculation': '取自原始数据 I_D_AMOUNT'},
    'volume_profile_ratio': {'chinese_name': '量比', 'category': '量价类',
                             'description': '量比，成交量相对20日均量的比值，反映放量/缩量程度',
                             'calculation': 'volume / ts_mean(volume, 20)'},
    'turnover_rate': {'chinese_name': '换手率', 'category': '量价类',
                             'description': '换手率，反映股票交易活跃度与流动性',
                             'calculation': 'volume / (free_shares + 1e-10)'},
    # Volatility
    'intraday_volatility': {'chinese_name': '日内波动率', 'category': '波动类',
                             'description': '日内实际振幅（基于分钟最高/最低价），反映单日价格波动范围',
                             'calculation': '(max(HIGH) - min(LOW)) / OPEN[0]，分钟数据精确计算'},
    'upper_shadow_pct': {'chinese_name': '上影线占比', 'category': '波动类',
                             'description': '上影线实际占比（基于分钟数据），反映日内冲高回落的卖压程度',
                             'calculation': '(max(HIGH) - max(OPEN[0], CLOSE[-1])) / max(OPEN[0], CLOSE[-1])，分钟数据精确计算'},
    'lower_shadow_pct': {'chinese_name': '下影线占比', 'category': '波动类',
                             'description': '下影线实际占比（基于分钟数据），反映日内探底回升的买盘支撑',
                             'calculation': '(min(OPEN[0], CLOSE[-1]) - min(LOW)) / min(OPEN[0], CLOSE[-1])，分钟数据精确计算'},
    # Innovative minute-derived (5 fields: 分钟数据创新糅合)
    'price_efficiency': {'chinese_name': '日内价格效率', 'category': '微观结构类',
                             'description': '日内价格效率 = |收盘-开盘|/(最高-最低)，效率越高趋势方向性越强。高效市场信息冲击方向明确，低效市场噪音多',
                             'calculation': '|CLOSE[-1] - OPEN[0]| / (max(HIGH) - min(LOW) + eps)'},
    'vwap': {'chinese_name': '成交量加权均价', 'category': '微观结构类',
                             'description': '成交量加权均价(VWAP)，机构交易执行的基准价格。收盘价高于VWAP说明买方主导日内资金流向',
                             'calculation': 'sum(price_i * vol_i) / sum(vol_i)，基于所有分钟bar精确计算'},
    'vwap_gap': {'chinese_name': 'VWAP偏离度', 'category': '微观结构类',
                             'description': 'VWAP偏离 = (收盘-VWAP)/VWAP，高于VWAP说明买方主导日内交易，是机构资金净流入的微观证据，被聪明钱策略广泛使用',
                             'calculation': '(CLOSE[-1] - VWAP_day) / VWAP_day，VWAP按分钟成交量加权'},
    'volume_concentration': {'chinese_name': '成交量集中度', 'category': '微观结构类',
                             'description': '成交量HHI集中度 = sum(分钟量占比^2)，高集中度说明大单集中在少数bar，可能是机构/程序化交易的微观行为痕迹',
                             'calculation': 'sum((vol_bar_i / total_day_vol)^2) over all minute bars'},
    'am_pm_divergence': {'chinese_name': '上下行背离度', 'category': '微观结构类',
                             'description': '上下行背离 = 上午收益×下午收益，负值表示盘中方向反转（新信息冲击），正值表示全天方向一致（信息被连续消化）',
                             'calculation': '(C[mid-1]-O[0])/O[0] * (C[-1]-O[mid])/O[mid]'},
    'close_location': {'chinese_name': '收盘价位置', 'category': '微观结构类',
                             'description': '收盘位置 = (收盘-最低)/(最高-最低)，>0.7说明买方控制全天（强势收盘），<0.3说明卖方主导（弱势收盘），常用于K线形态识别',
                             'calculation': '(CLOSE[-1] - min(LOW)) / (max(HIGH) - min(LOW) + eps)'},

    # 收益类扩展
    'ret_10d': {'chinese_name': '10日收益率', 'category': '收益类', 'description': '双周动量信号，介于短期反转和中期动量之间', 'calculation': 'close[t] / close[t-10] - 1'},
    'ret_40d': {'chinese_name': '40日收益率', 'category': '收益类', 'description': '双月动量，中期趋势度量', 'calculation': 'close[t] / close[t-40] - 1'},
    'cumret_5d': {'chinese_name': '5日累积收益', 'category': '收益类', 'description': '5日复利累积收益，连续涨跌信号，比简单求和更精确', 'calculation': 'product(1+returns[t-4:t+1]) - 1'},
    # 波动率扩展
    'vol_5d': {'chinese_name': '5日波动率', 'category': '波动率类', 'description': '周度已实现波动率，捕捉短期波动变化', 'calculation': 'ts_std(returns, 5)'},
    'vol_10d': {'chinese_name': '10日波动率', 'category': '波动率类', 'description': '双周已实现波动率', 'calculation': 'ts_std(returns, 10)'},
    'vol_40d': {'chinese_name': '40日波动率', 'category': '波动率类', 'description': '双月波动率，中期波动度量', 'calculation': 'ts_std(returns, 40)'},
    'vol_120d': {'chinese_name': '120日波动率', 'category': '波动率类', 'description': '半年度波动率，长期风险度量基准', 'calculation': 'ts_std(returns, 120)'},
    'upside_vol_60d': {'chinese_name': '上行波动率', 'category': '波动率类', 'description': '仅用正收益计算标准差，反映上涨动能强度', 'calculation': 'ts_std(max(returns, 0), 60)'},
    'down_up_vol_ratio': {'chinese_name': '下行上行波动比', 'category': '波动率类', 'description': '>1=下跌波动大于上涨波动，空头压力指标', 'calculation': 'downside_vol_60d / upside_vol_60d'},
    'vol_ratio_20_60': {'chinese_name': '波动率比(20/60)', 'category': '波动率类', 'description': '中短期波动状态，判断波动率趋势', 'calculation': 'vol_20d / vol_60d'},
    'bollinger_width': {'chinese_name': '布林带宽度', 'category': '技术指标类', 'description': '布林带宽度=4*std/MA，收窄=变盘前兆，扩张=趋势加速', 'calculation': '4 * std_20d(close) / ma_20d(close)'},
    # 量价扩展
    'adv5': {'chinese_name': '5日均量', 'category': '量价类', 'description': '短期平均成交量基准，周度流动性参考', 'calculation': 'ts_mean(volume, 5)'},
    'adv20': {'chinese_name': '20日均量', 'category': '量价类', 'description': '月度平均成交量，WQ平台标准字段', 'calculation': 'ts_mean(volume, 20)'},
    'dollar_volume': {'chinese_name': '成交额(元)', 'category': '量价类', 'description': '日成交额=收盘价×成交量，规模调整的流动性指标', 'calculation': 'close * volume'},
    'volume_trend_20d': {'chinese_name': '量趋势(20日)', 'category': '量价类', 'description': '20日内成交量时序排名，持续放量=资金流入趋势', 'calculation': 'ts_rank(volume, 20)'},
    'amount_volatility': {'chinese_name': '成交额波动率', 'category': '量价类', 'description': '成交额变异系数=标准差/均值，反映资金关注度的稳定性', 'calculation': 'ts_std(amount, 20) / ts_mean(amount, 20)'},
    'volume_price_corr': {'chinese_name': '量价相关系数', 'category': '量价类', 'description': '20日量价滚动相关，正=放量上涨/缩量下跌(健康)', 'calculation': 'ts_corr(volume, returns, 20)'},
    # 形态扩展
    'gap_down': {'chinese_name': '向下跳空', 'category': '形态类', 'description': '向下跳空幅度，利空冲击强度，大的向下跳空=恐慌信号', 'calculation': 'max(0, preclose - open) / preclose'},
    'close_vs_low_20d': {'chinese_name': '收盘距20日低', 'category': '形态类', 'description': '接近20日低点=可能超卖，反弹概率增大', 'calculation': 'close / ts_min(low, 20)'},
    'doji_score': {'chinese_name': '十字星评分', 'category': '形态类', 'description': '≈1=开盘≈收盘=多空均衡=趋势可能反转', 'calculation': '1 - |close - open| / (high - low + eps)'},
    # 反转扩展
    'rev_10d': {'chinese_name': '10日反转', 'category': '反转类', 'description': '双周均值回复效应', 'calculation': '-ret_10d'},
    'rev_20d': {'chinese_name': '20日反转', 'category': '反转类', 'description': '月度反转，中长期过度反应修正', 'calculation': '-ret_20d'},
    'rev_vol_regime': {'chinese_name': '波动状态反转', 'category': '反转类', 'description': '高波动环境下反转信号更强（过度反应更严重）', 'calculation': 'rev_5d * vol_20d'},
    # 高阶统计
    'skewness_20d': {'chinese_name': '20日偏度', 'category': '高阶统计类', 'description': '短期收益分布不对称性，负偏=左尾风险(Harvey & Siddique 2000)', 'calculation': 'E[(R-μ)³] / σ³ over 20d'},
    'kurtosis_60d': {'chinese_name': '60日峰度', 'category': '高阶统计类', 'description': '收益分布肥尾程度，>3=极端事件概率高于正态', 'calculation': 'E[(R-μ)⁴] / σ⁴ over 60d'},
    'max_ret_20d': {'chinese_name': '20日最大日收益', 'category': '高阶统计类', 'description': '彩票型偏好指标，最大收益高=散户追涨意愿强', 'calculation': 'ts_max(returns, 20)'},
    'min_ret_20d': {'chinese_name': '20日最小日收益', 'category': '高阶统计类', 'description': '崩盘风险指标，最差单日表现', 'calculation': 'ts_min(returns, 20)'},
    'hit_rate_20d': {'chinese_name': '20日胜率', 'category': '高阶统计类', 'description': '正收益天数占比，短期稳定性指标', 'calculation': 'ts_mean(returns > 0, 20)'},
    'hit_rate_60d': {'chinese_name': '60日胜率', 'category': '高阶统计类', 'description': '中期正收益稳定性，>0.55为佳', 'calculation': 'ts_mean(returns > 0, 60)'},
    # 跨模态
    'intraday_reversal': {'chinese_name': '日内反转', 'category': '微观结构类', 'description': '早盘vs尾盘背离度，负=盘中反转信号', 'calculation': '-first30_mom * last30_mom'},
    'volume_price_div': {'chinese_name': '量价背离', 'category': '量价类', 'description': '价涨量缩=顶部信号，价跌量增=底部信号', 'calculation': 'returns * volume_trend_20d'},
    'gap_momentum': {'chinese_name': '跳空动量', 'category': '形态类', 'description': '跳空后日内趋势延续性，正=跳空方向延续', 'calculation': 'auction_return * returns'},

    # ===== Pre-computed factors (65 factors, 8 categories) =====
    # A: Momentum 动量 (8)
    'ret_20d': {'chinese_name': '20日收益率', 'category': '动量因子',
                             'description': '20日累计收益率。中期动量效应，前期涨的股票继续涨的概率更高',
                             'calculation': 'close[t] / close[t-20] - 1。论文: Jegadeesh & Titman (1993) "Returns to Buying Winners and Selling Losers", Journal of Finance'},
    'amihud_20d': {'chinese_name': 'Amihud非流动性', 'category': '量价因子',
                             'description': 'Amihud非流动性指标：单位成交额对价格的影响。高Amihud=低流动性=高交易成本，需补偿更高收益',
                             'calculation': 'mean(|return| / dollar_volume, 20d)。论文: Amihud (2002) "Illiquidity and Stock Returns", Journal of Financial Markets'},
    'market_cap_rank': {'chinese_name': '市值排名', 'category': '技术指标',
                             'description': '市值排名：对数市值在截面中的百分位。A股最稳健的因子之一，小市值效应长期存在',
                             'calculation': 'rank(log(close * total_shares))。论文: Banz (1981) "The Relationship Between Return and Market Value of Common Stocks", JFE; Fama & French (1992) "The Cross-Section of Expected Stock Returns", Journal of Finance'},
    'vpin': {'chinese_name': 'VPIN知情交易概率', 'category': '微观结构因子',
                             'description': 'VPIN(成交量同步知情概率)：基于分钟成交量不平衡的知情交易概率，高VPIN=内幕交易风险',
                             'calculation': 'Easley et al. (2012) 成交量桶方法。论文: Easley, Lopez de Prado & O\'Hara (2012) "Flow Toxicity and Liquidity in a High Frequency World", Review of Financial Studies'},
    'rsi_14': {'chinese_name': '相对强弱指数RSI', 'category': '技术指标',
                             'description': 'RSI(14)：相对强弱指数。>70=超买(回调风险)，<30=超卖(反弹机会)。A股中RSI反转效果优于趋势跟踪',
                             'calculation': '100 - 100/(1 + mean(gain,14)/mean(loss,14))。论文: Wilder (1978) "New Concepts in Technical Trading Systems"'},
    'skewness_60d': {'chinese_name': '收益偏度', 'category': '波动率因子',
                             'description': '60日收益偏度。正偏=彩票型股票（散户偏好），负偏=崩盘风险（机构回避），A股中负偏度股票未来收益更高',
                             'calculation': 'skewness(daily_returns, 60d)。论文: Harvey & Siddique (2000) "Conditional Skewness in Asset Pricing Tests", Journal of Finance'},
    'beta_60d': {'chinese_name': '60日Beta系数', 'category': '技术指标',
                             'description': '60日Beta：个股相对市场的系统风险。高Beta=牛市弹性大但熊市跌更多，低Beta异象在A股有效',
                             'calculation': 'cov(ret_stock, ret_market) / var(ret_market)，60d rolling。论文: Frazzini & Pedersen (2014) "Betting Against Beta", JFE'},
    'ret_60d': {'chinese_name': '60日收益率', 'category': '动量因子',
                             'description': '60日累计收益率。长期动量信号，更稳定但换手率更低',
                             'calculation': 'close[t] / close[t-60] - 1'},
    'ret_120d_skip5': {'chinese_name': '120日收益率(跳5)', 'category': '动量因子',
                             'description': '120日收益（跳过最近5日）。剔除短期反转效应后的纯长期动量，避免短期噪音干扰',
                             'calculation': 'close[t-5] / close[t-120] - 1'},
    'ret_5d': {'chinese_name': '5日收益率', 'category': '动量因子',
                             'description': '5日收益率（短期动量/反转）。A股市场5日通常表现为反转效应而非动量',
                             'calculation': 'close[t] / close[t-5] - 1'},
    'sharpe_60d': {'chinese_name': '60日夏普比率', 'category': '动量因子',
                             'description': '60日夏普比率。风险调整后的动量，比原始收益更稳健，高夏普说明上涨质量好（波动小）',
                             'calculation': 'mean(ret_60d) / std(ret_60d)，逐日滚动'},
    'mom_vol_adj': {'chinese_name': '波动率调整动量', 'category': '动量因子',
                             'description': '波动率调整动量 = 20日收益/20日波动率。剔除波动率影响后的纯动量信号',
                             'calculation': 'ret_20d / std_20d(returns)'},
    'max_dd_60d': {'chinese_name': '60日最大回撤', 'category': '动量因子',
                             'description': '60日最大回撤。反映近期下行风险，回撤大的股票可能继续走弱或反弹（需结合方向判断）',
                             'calculation': 'max(peak - current) / peak over 60-day rolling window'},
    'close_vs_high_20d': {'chinese_name': '收盘距20日高点', 'category': '动量因子',
                             'description': '收盘价相对20日高点的距离。接近高点=强势趋势，远离高点=弱势或回调中',
                             'calculation': 'close[t] / max(high[t-20:t+1])'},
    # B: Reversal 反转 (6)
    'rev_1d': {'chinese_name': '1日反转', 'category': '反转因子',
                             'description': '1日反转：昨日收益取负。A股T+1制度下短期过度反应后的均值回复，是最经典的反转因子',
                             'calculation': '-(close[t-1] / close[t-2] - 1)'},
    'rev_5d': {'chinese_name': '5日反转', 'category': '反转因子',
                             'description': '5日反转：近5日收益取负。捕捉一周级别过度反应后的修正，A股中IC通常高于1日反转',
                             'calculation': '-(close[t] / close[t-5] - 1)'},
    'rev_overnight': {'chinese_name': '隔夜反转', 'category': '反转因子',
                             'description': '隔夜反转：集合竞价涨幅取负。隔夜跳空后日内回补的倾向，反映散户追涨后机构反向操作',
                             'calculation': '-(open - preclose) / preclose'},
    'abnormal_vol_rev': {'chinese_name': '异常放量反转', 'category': '反转因子',
                             'description': '异常放量反转：放量日收益取负。异常成交量伴随的价格变动更可能反转（信息冲击消化后均值回复）',
                             'calculation': '-ret * volume_profile_ratio'},
    'extreme_loser_5d': {'chinese_name': '极端输家反转', 'category': '反转因子',
                             'description': '极端输家反转：5日跌幅最大的股票短期反弹概率更高，利用投资者过度悲观',
                             'calculation': 'rank(-ret_5d)，底部排名越低的越被看好'},
    'extreme_winner_5d': {'chinese_name': '极端赢家反转', 'category': '反转因子',
                             'description': '极端赢家反转：5日涨幅最大的股票短期回调概率更高，利用投资者过度乐观',
                             'calculation': '-rank(ret_5d)'},
    # C: Volatility 波动率 (5)
    'vol_20d': {'chinese_name': '20日波动率', 'category': '波动率因子',
                             'description': '20日波动率。低波动异象（低vol股票未来收益更高）在A股同样存在，是Fama-French因子之外最稳健的异象之一',
                             'calculation': 'std_20d(daily_returns)'},
    'vol_60d': {'chinese_name': '60日波动率', 'category': '波动率因子',
                             'description': '60日波动率。更长期的波动率估计，更稳定但反应更慢',
                             'calculation': 'std_60d(daily_returns)'},
    'vol_ratio': {'chinese_name': '波动率比值', 'category': '波动率因子',
                             'description': '波动率比值 = 短期vol/长期vol。比值升高说明波动率在加速（风险预警），降低说明趋于平稳',
                             'calculation': 'vol_20d / vol_60d'},
    'downside_vol_60d': {'chinese_name': '下行波动率', 'category': '波动率因子',
                             'description': '下行波动率：仅用负收益计算标准差。区分上行波动（好）和下行波动（坏），下行波动高=尾部风险大',
                             'calculation': 'std(negative_returns_only, 60d)'},
    'skewness_60d': {'chinese_name': '收益偏度', 'category': '波动率因子',
                             'description': '60日收益偏度。正偏=彩票型股票（散户偏好），负偏=崩盘风险（机构回避），A股中负偏度股票未来收益更高',
                             'calculation': 'skewness(daily_returns, 60d)'},
    # D: Liquidity 流动性 (6)
    'vol_ratio_5_20': {'chinese_name': '量比(5/20)', 'category': '量价因子',
                             'description': '量比 = 5日均量/20日均量。>1=近期放量（资金关注），<1=缩量（无人问津），A股放量信号较为有效',
                             'calculation': 'mean(volume, 5) / mean(volume, 20)'},
    'volume_breakout': {'chinese_name': '成交量突破', 'category': '量价因子',
                             'description': '成交量突破 = 当日量/60日均量。极端放量(>3倍)可能预示趋势转折或加速',
                             'calculation': 'volume[t] / mean(volume, 60)'},
    'turnover_5d': {'chinese_name': '5日换手率', 'category': '量价因子',
                             'description': '5日换手率。高换手=高度活跃但可能过度交易，低换手=缺乏关注但可能被低估',
                             'calculation': 'mean(volume/free_shares, 5)'},
    'turnover_change': {'chinese_name': '换手率变化', 'category': '量价因子',
                             'description': '换手率变化 = 短期换手/长期换手减1。换手率加速=资金加速进出，与动量结合使用效果好',
                             'calculation': 'turnover_5d / turnover_20d - 1'},
    'amihud_20d': {'chinese_name': 'Amihud非流动性', 'category': '量价因子',
                             'description': 'Amihud非流动性指标：单位成交额对价格的影响。高Amihud=低流动性=高交易成本，需补偿更高收益',
                             'calculation': 'mean(|return| / dollar_volume, 20d)'},
    'log_dollar_vol': {'chinese_name': '对数成交额', 'category': '量价因子',
                             'description': '对数成交额。控制了规模效应后的流动性度量，大市值高成交额股票通常更受机构偏好',
                             'calculation': 'log(close * volume)'},
    # E: Price Pattern 形态 (4)
    'upper_shadow': {'chinese_name': '上影线比例', 'category': '形态因子',
                             'description': '上影线比例。长上影=盘中冲高回落=卖压大（机构出货），短上影=买方坚定',
                             'calculation': '(high - max(open, close)) / (high - low + eps)'},
    'lower_shadow': {'chinese_name': '下影线比例', 'category': '形态因子',
                             'description': '下影线比例。长下影=盘中探底回升=买盘支撑（机构吸筹），短下影=卖方坚定',
                             'calculation': '(min(open, close) - low) / (high - low + eps)'},
    'body_ratio': {'chinese_name': '实体占比', 'category': '形态因子',
                             'description': '实体占比 = |收盘-开盘|/(最高-最低)。大实体=方向明确，小实体=多空僵持/十字星',
                             'calculation': '|close - open| / (high - low + eps)'},
    'gap_up': {'chinese_name': '向上跳空幅度', 'category': '形态因子',
                             'description': '向上跳空 = max(0, open-preclose)/preclose。向上跳空后回补概率是A股日内交易的重要策略信号',
                             'calculation': 'max(0, open - preclose) / preclose'},
    # F: Microstructure 微观结构 (25)
    'first30_mom': {'chinese_name': '开盘动量', 'category': '微观结构因子',
                             'description': '开盘动量：前30分钟收益。开盘走势反映隔夜信息消化和机构开盘策略，是日内方向的重要先行指标',
                             'calculation': '(C[29] - O[0]) / O[0]，分钟线精确计算'},
    'last30_mom': {'chinese_name': '尾盘动量', 'category': '微观结构因子',
                             'description': '尾盘动量：最后30分钟收益。尾盘走势反映机构收盘定价和次日预期，是聪明钱的重要观察窗口',
                             'calculation': '(C[-1] - O[-30]) / O[-30]，分钟线精确计算'},
    'intraday_mom': {'chinese_name': '日内动量', 'category': '微观结构因子',
                             'description': '日内动量：全日实际涨跌幅。基于分钟首尾价精确计算，不含隔夜跳空的影响',
                             'calculation': '(C[-1] - O[0]) / O[0]，分钟线精确计算'},
    'realized_vol': {'chinese_name': '已实现波动率', 'category': '微观结构因子',
                             'description': '已实现波动率：日内分钟收益标准差年化。比日频vol更精细，捕捉日内波动模式',
                             'calculation': 'std(minute_returns) * sqrt(242)'},
    'vol_skew': {'chinese_name': '波动率偏度', 'category': '微观结构因子',
                             'description': '波动率偏度：上午vol/全天vol。上午波动>下午说明信息集中在早盘释放',
                             'calculation': 'morning_volatility / full_day_volatility'},
    'close_vs_vwap': {'chinese_name': '收盘vsVWAP', 'category': '微观结构因子',
                             'description': '收盘vs VWAP：收盘价相对成交量加权均价的位置。高于VWAP=买方主导日内资金流向',
                             'calculation': '(close - VWAP_day) / VWAP_day'},
    'vwap_trend': {'chinese_name': 'VWAP趋势', 'category': '微观结构因子',
                             'description': 'VWAP趋势：VWAP的短期变化方向。VWAP持续走高说明资金持续流入',
                             'calculation': 'VWAP[t] / VWAP[t-5] - 1'},
    'volume_hhi': {'chinese_name': '成交量HHI', 'category': '微观结构因子',
                             'description': '成交量HHI：分钟成交量集中度。高HHI=大单集中在少数分钟=机构行为痕迹',
                             'calculation': 'sum((vol_i / total_vol)^2)'},
    'open_vol_ratio': {'chinese_name': '开盘量占比', 'category': '微观结构因子',
                             'description': '开盘量占比：前30分钟成交量/全天。高占比说明开盘信息冲击大，机构集中调仓',
                             'calculation': 'open_vol / total_day_vol'},
    'close_vol_ratio': {'chinese_name': '收盘量占比', 'category': '微观结构因子',
                             'description': '收盘量占比：最后30分钟成交量/全天。高占比说明收盘定价效应强，被动基金调仓信号',
                             'calculation': 'close_vol / total_day_vol'},
    'smart_money_vol': {'chinese_name': '聪明钱成交量', 'category': '微观结构因子',
                             'description': '聪明钱成交量：价格上行时的成交量 - 价格下行时的成交量。正=聪明钱净买入',
                             'calculation': 'sum(vol_i * sign(ret_i))'},
    'amihud_min': {'chinese_name': '分钟Amihud', 'category': '微观结构因子',
                             'description': '分钟Amihud：分钟级别的非流动性度量。比日频Amihud更精细地捕捉日内流动性变化',
                             'calculation': 'mean(|min_ret_i| / min_vol_i)'},
    'vpin': {'chinese_name': 'VPIN知情交易概率', 'category': '微观结构因子',
                             'description': 'VPIN(成交量同步知情概率)：基于分钟成交量不平衡的知情交易概率，高VPIN=内幕交易风险',
                             'calculation': 'Easley et al. (2012) 成交量桶方法'},
    'large_trade_ratio': {'chinese_name': '大单占比', 'category': '微观结构因子',
                             'description': '大单占比：大成交量bar占比。高占比=机构/程序化交易主导，散户参与低',
                             'calculation': 'count(vol_i > threshold) / total_bars'},
    'roll_spread': {'chinese_name': 'Roll价差', 'category': '微观结构因子',
                             'description': 'Roll价差估计：基于价格变动协方差的隐含买卖价差。高Roll价差=低流动性=高交易成本',
                             'calculation': '2*sqrt(|cov(ret_t, ret_t-1)|)'},
    'opening_confirm': {'chinese_name': '开盘确认', 'category': '微观结构因子',
                             'description': '开盘确认：开盘方向与昨日收盘方向一致性。连续同向=趋势延续信号',
                             'calculation': 'sign(opening_ret) == sign(prev_close_ret) ? 1 : -1'},
    'vpin_informed': {'chinese_name': '知情交易强度', 'category': '微观结构因子',
                             'description': '知情交易强度：VPIN × 成交量。结合知情交易概率和交易规模的综合信号',
                             'calculation': 'VPIN * volume_ratio'},
    'overnight_reversal': {'chinese_name': '隔夜反转强度', 'category': '微观结构因子',
                             'description': '隔夜反转强度：隔夜跳空方向与日内走势的背离程度。高背离=散户与机构博弈激烈',
                             'calculation': '-sign(overnight_ret) * intraday_ret'},
    'amihud_hybrid': {'chinese_name': '混合Amihud', 'category': '微观结构因子',
                             'description': '混合Amihud：日频+分钟频Amihud的组合。多时间尺度流动性度量',
                             'calculation': '0.5*amihud_20d + 0.5*amihud_min'},
    'close_manipulation': {'chinese_name': '收盘操纵检测', 'category': '微观结构因子',
                             'description': '收盘操纵检测：尾盘异常拉高/打压程度。高值=疑似收盘价操纵',
                             'calculation': '|last30m_ret - body_ret| / (intraday_vol + eps)'},
    'triple_confirm': {'chinese_name': '三重确认', 'category': '微观结构因子',
                             'description': '三重确认：开盘+午盘+尾盘方向一致时=1，分歧时=-1。三个时段全同向=强信号',
                             'calculation': 'sign(first30) == sign(mid) == sign(last30) ? 1 : -1'},
    'wat': {'chinese_name': '加权平均时间', 'category': '微观结构因子',
                             'description': '加权平均时间：成交量的时间重心。重心偏早盘=信息早释放，偏尾盘=信息滞后',
                             'calculation': 'sum(time_i * vol_i) / sum(vol_i)'},
    'large_trade_signal': {'chinese_name': '大单信号', 'category': '微观结构因子',
                             'description': '大单信号：大单方向 × 大单强度。正=大单净买入，负=大单净卖出',
                             'calculation': 'direction(large_trades) * large_trade_ratio'},
    'smart_money_vwap': {'chinese_name': '聪明钱综合', 'category': '微观结构因子',
                             'description': '聪明钱综合：Smart Money Volume × VWAP偏离。双重验证聪明钱方向',
                             'calculation': 'smart_money_vol * vwap_gap'},
    'vol_conc_mom': {'chinese_name': '量集中动量', 'category': '微观结构因子',
                             'description': '量集中×动量：成交量集中度与日内动量的交互。量集中在趋势方向=强信号',
                             'calculation': 'volume_concentration * intraday_momentum'},
    # G: Cross-modal 跨模态 (7)
    'mom_vol_conf': {'chinese_name': '动量波动确认', 'category': '跨模态因子',
                             'description': '动量波动确认：动量×波动率倒数。高动量+低波动=可持续趋势，高动量+高波动=不稳定',
                             'calculation': 'ret_20d / (vol_20d + eps)'},
    'mom_liquidity_adj': {'chinese_name': '动量流动性调整', 'category': '跨模态因子',
                             'description': '动量流动性调整：动量/Amihud。剔除流动性溢价后的纯动量信号，避免把小盘流动性差的动量误判为alpha',
                             'calculation': 'ret_20d / (amihud_20d + eps)'},
    'rev_vol_conf': {'chinese_name': '反转波动确认', 'category': '跨模态因子',
                             'description': '反转波动确认：反转信号×波动率。高波动环境下的反转信号更可靠（过度反应更严重）',
                             'calculation': 'rev_5d * vol_20d'},
    'intraday_ret5d': {'chinese_name': '日内日频动量', 'category': '跨模态因子',
                             'description': '日内×日频动量：日内动量+5日动量的综合。跨时间尺度的动量一致性',
                             'calculation': 'intraday_mom * ret_5d'},
    'vwap_close_mom': {'chinese_name': 'VWAP收盘动量', 'category': '跨模态因子',
                             'description': 'VWAP×收盘动量：VWAP位置与收盘动量的交互。VWAP高+动量正=机构坚定做多',
                             'calculation': 'close_vs_vwap * ret_20d'},
    'smart_money_rev': {'chinese_name': '聪明钱反转', 'category': '跨模态因子',
                             'description': '聪明钱×反转：聪明钱流入的反转信号。聪明钱逆势买入=抄底信号',
                             'calculation': 'smart_money_vol * rev_5d'},
    'liquidity_premium': {'chinese_name': '流动性溢价', 'category': '跨模态因子',
                             'description': '流动性溢价：Amihud×市值。低流动性+小市值=最高流动性溢价补偿',
                             'calculation': 'amihud_20d / market_cap_rank'},
    # H: Technical 技术指标 (4)
    'rsi_14': {'chinese_name': '相对强弱指数RSI', 'category': '技术指标',
                             'description': 'RSI(14)：相对强弱指数。>70=超买(回调风险)，<30=超卖(反弹机会)。A股中RSI反转效果优于趋势跟踪',
                             'calculation': '100 - 100/(1 + mean(gain,14)/mean(loss,14))'},
    'bollinger_pos': {'chinese_name': '布林带位置', 'category': '技术指标',
                             'description': '布林带位置：(收盘-下轨)/(上轨-下轨)。0=下轨，1=上轨。接近下轨=可能的支撑和反弹',
                             'calculation': '(close - lower_bb) / (upper_bb - lower_bb)，bb=20日均线±2标准差'},
    'beta_60d': {'chinese_name': '60日Beta系数', 'category': '技术指标',
                             'description': '60日Beta：个股相对市场的系统风险。高Beta=牛市弹性大但熊市跌更多，低Beta异象在A股有效',
                             'calculation': 'cov(ret_stock, ret_market) / var(ret_market)，60d rolling'},
    'market_cap_rank': {'chinese_name': '市值排名', 'category': '技术指标',
                             'description': '市值排名：对数市值在截面中的百分位。A股最稳健的因子之一，小市值效应长期存在（Banz 1981）',
                             'calculation': 'rank(log(close * total_shares))'},
}


_VARS = {}

def parse_expression(expr: str, pipeline, fc=None) -> np.ndarray:
    """Parse a WQ-style expression into a numpy factor array.

    Supports multi-line code with variable assignments (WQ FastExpr style):
      returns = daily_return;
      returns + 1
    The last line without assignment is the final expression.
    Lines are separated by ; or newline. Variables persist within one parse call.

    Args:
        expr: Expression string or multi-line code block
        pipeline: DataPipeline with daily OHLCV fields
        fc: FactorComputer (optional) — provides 65 pre-computed factors
    """
    expr = expr.strip()

    # Multi-line support: split by ; or newline
    global _VARS
    lines = [l.strip() for l in expr.replace(';', '\n').split('\n') if l.strip()]
    if len(lines) > 1:
        _VARS = {}
        for line in lines[:-1]:
            if '=' in line:
                var_name, var_expr = line.split('=', 1)
                var_name = var_name.strip()
                var_expr = var_expr.strip()
                _VARS[var_name] = parse_expression(var_expr, pipeline, fc)
        # If last line is just a variable name, return cached result directly
        last_line = lines[-1].strip()
        if last_line in _VARS:
            result = _VARS[last_line].copy()
            _VARS = {}
            return result
        result = _parse_single(last_line, pipeline, fc)
        _VARS = {}
        return result

    return _parse_single(expr, pipeline, fc)


def _parse_single(expr: str, pipeline, fc=None) -> np.ndarray:
    """Parse a single-line WQ-style expression."""
    expr = expr.strip()

    # Handle unary minus
    if expr.startswith('-'):
        return -_parse_single(expr[1:].strip(), pipeline, fc)

    # Remove outer parentheses if they wrap the whole expression
    while expr.startswith('(') and expr.endswith(')'):
        depth = 0
        ok = True
        for i, c in enumerate(expr):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                ok = False
                break
        if ok:
            expr = expr[1:-1].strip()
        else:
            break

    # Try function calls: only if function spans the WHOLE expression
    func_match = re.match(r'(\w+)\(', expr)
    if func_match:
        func_name = func_match.group(1)
        paren_start = func_match.end() - 1

        # Find matching closing paren
        depth = 0
        paren_end = -1
        for i in range(paren_start, len(expr)):
            if expr[i] == '(':
                depth += 1
            elif expr[i] == ')':
                depth -= 1
                if depth == 0:
                    paren_end = i
                    break

        if paren_end == len(expr) - 1:
            # Function call is the whole expression — parse it
            args_str = expr[paren_start + 1:paren_end]
            args = _split_args(args_str)
            return _eval_function(func_name, args, pipeline, fc)

    # Arithmetic operators: scan right-to-left for lowest-precedence
    depth = 0
    for i in range(len(expr) - 1, 0, -1):
        c = expr[i]
        if c == ')':
            depth += 1
        elif c == '(':
            depth -= 1
        elif depth == 0:
            if c == '+' and expr[i - 1] not in '()[]<>=':
                left = _parse_single(expr[:i].strip(), pipeline, fc)
                right = _parse_single(expr[i + 1:].strip(), pipeline, fc)
                return left + right
            elif c == '-' and expr[i - 1] not in '()[]<>=+-*/^':
                left = _parse_single(expr[:i].strip(), pipeline, fc)
                right = _parse_single(expr[i + 1:].strip(), pipeline, fc)
                return left - right

    depth = 0
    for i in range(len(expr) - 1, 0, -1):
        c = expr[i]
        if c == ')':
            depth += 1
        elif c == '(':
            depth -= 1
        elif depth == 0:
            if c == '*':
                left = _parse_single(expr[:i].strip(), pipeline, fc)
                right = _parse_single(expr[i + 1:].strip(), pipeline, fc)
                return left * right
            elif c == '/':
                left = _parse_single(expr[:i].strip(), pipeline, fc)
                right = _parse_single(expr[i + 1:].strip(), pipeline, fc)
                return left / (right + 1e-10)

    # Variable lookup — check global _VARS before field lookup
    if expr in _VARS:
        return _VARS[expr].copy()

    # Field lookup — daily pipeline fields
    field_map = {
        'close': 'I_D_CLOSE_ORI', 'open': 'I_D_OPEN_ORI',
        'high': 'I_D_HIGH_ORI', 'low': 'I_D_LOW_ORI',
        'preclose': 'I_D_PRECLOSE_ORI', 'volume': 'I_D_VOLUME',
        'amount': 'I_D_AMOUNT',
    }
    if expr in field_map:
        return pipeline.fields[field_map[expr]].copy()

    # Derived field lookup — computed from pipeline data (Task 2)
    if expr in DERIVED_FIELD_REGISTRY:
        return _cached_derive(expr, DERIVED_FIELD_REGISTRY[expr], pipeline)

    # Pre-computed factors from FactorComputer (65 factors, 8 categories)
    if fc is not None:
        factor_field = _get_factor_field(expr, fc)
        if factor_field is not None:
            return factor_field

    # Numeric literal
    try:
        val = float(expr)
        return np.full((pipeline.n_dates, pipeline.n_stocks), val, dtype=np.float32)
    except ValueError:
        pass

    raise ValueError(f"无法解析表达式: {expr}")


def _get_factor_field(name: str, fc):
    """Look up a pre-computed factor by name. Returns (n_dates, n_stocks) array or None."""
    factor_methods = {
        # A: Momentum (8)
        'ret_20d': fc.A1_1_ret_20d,
        'ret_60d': fc.A1_2_ret_60d,
        'ret_120d_skip5': fc.A1_3_ret_120d_skip5,
        'ret_5d': fc.A1_4_ret_5d,
        'sharpe_60d': fc.A2_1_sharpe_60d,
        'mom_vol_adj': fc.A2_2_mom_vol_adj,
        'max_dd_60d': fc.A3_1_max_dd_60d,
        'close_vs_high_20d': fc.A3_3_close_vs_high_20d,
        # B: Reversal (6)
        'rev_1d': fc.B1_1_rev_1d,
        'rev_5d': fc.B1_2_rev_5d,
        'rev_overnight': fc.B1_4_rev_overnight,
        'abnormal_vol_rev': fc.B2_1_abnormal_vol_rev,
        'extreme_loser_5d': fc.B3_1_extreme_loser_5d,
        'extreme_winner_5d': fc.B3_2_extreme_winner_5d,
        # C: Volatility (5)
        'vol_20d': fc.C1_1_vol_20d,
        'vol_60d': fc.C1_2_vol_60d,
        'vol_ratio': fc.C1_3_vol_ratio,
        'downside_vol_60d': fc.C2_1_downside_vol_60d,
        'skewness_60d': fc.C4_1_skewness_60d,
        # D: Liquidity (6)
        'vol_ratio_5_20': fc.D1_1_vol_ratio_5_20,
        'volume_breakout': fc.D1_3_volume_breakout,
        'turnover_5d': fc.D2_1_turnover_5d,
        'turnover_change': fc.D2_2_turnover_change,
        'amihud_20d': fc.D3_1_amihud_20d,
        'log_dollar_vol': fc.D4_1_log_dollar_vol,
        # E: Price patterns (4)
        'upper_shadow': fc.E1_1_upper_shadow,
        'lower_shadow': fc.E1_2_lower_shadow,
        'body_ratio': fc.E1_3_body_ratio,
        'gap_up': fc.E2_1_gap_up,
        # F: Minute microstructure (25)
        'first30_mom': fc.F1_1_first30_mom,
        'last30_mom': fc.F1_2_last30_mom,
        'intraday_mom': fc.F1_3_intraday_mom,
        'realized_vol': fc.F3_1_realized_vol,
        'vol_skew': fc.F3_2_vol_skew,
        'close_vs_vwap': fc.F4_1_close_vs_vwap,
        'vwap_trend': fc.F4_2_vwap_trend,
        'volume_hhi': fc.F5_1_volume_hhi,
        'open_vol_ratio': fc.F5_2_open_vol_ratio,
        'close_vol_ratio': fc.F5_3_close_vol_ratio,
        'smart_money_vol': fc.F5_5_smart_money_vol,
        'amihud_min': fc.F6_2_amihud_min,
        'vpin': fc.F6_3_vpin,
        'large_trade_ratio': fc.F6_4_large_trade_ratio,
        'roll_spread': fc.F6_5_roll_spread,
        'opening_confirm': fc.F_COMBO_1_opening_confirmation,
        'vpin_informed': fc.F_COMBO_2_vpin_informed,
        'overnight_reversal': fc.F_COMBO_3_overnight_reversal_intensity,
        'amihud_hybrid': fc.F_COMBO_4_amihud_hybrid,
        'close_manipulation': fc.F_COMBO_5_close_manipulation,
        'triple_confirm': fc.F_COMBO_6_intraday_triple_confirmation,
        'wat': fc.F_COMBO_7_weighted_avg_time,
        'large_trade_signal': fc.F_COMBO_8_large_trade_signal,
        'smart_money_vwap': fc.F_COMBO_9_smart_money_composite,
        'vol_conc_mom': fc.F_COMBO_10_vol_concentration_mom,
        # G: Cross-modal (7)
        'mom_vol_conf': fc.G1_1_mom_with_vol_conf,
        'mom_liquidity_adj': fc.G1_2_mom_liquidity_adj,
        'rev_vol_conf': fc.G1_3_rev_with_vol_conf,
        'intraday_ret5d': fc.G2_1_intraday_trend_ret5d,
        'vwap_close_mom': fc.G2_3_vwap_close_x_mom,
        'smart_money_rev': fc.G2_5_smart_money_x_reversal,
        'liquidity_premium': fc.G3_1_liquidity_premium,
        # H: Technical (4)
        'rsi_14': fc.H1_1_RSI_14,
        'bollinger_pos': fc.H1_3_bollinger_position,
        'beta_60d': fc.H2_2_beta_60d,
        'market_cap_rank': fc.H2_5_market_cap_rank,
    }
    if name in factor_methods:
        try:
            return factor_methods[name]().astype(np.float32)
        except Exception:
            return None
    return None


def _eval_function(func_name: str, args: list, pipeline, fc=None) -> np.ndarray:
    """Evaluate a parsed function call."""
    if func_name == 'ts_delta':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        result[d:] = x[d:] - x[:-d]
        return result

    elif func_name == 'ts_mean':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d - 1, x.shape[0]):
            result[i] = np.nanmean(x[i - d + 1:i + 1], axis=0)
        return result

    elif func_name == 'ts_std':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d - 1, x.shape[0]):
            result[i] = np.nanstd(x[i - d + 1:i + 1], axis=0)
        return result

    elif func_name == 'ts_rank':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        # Vectorized: eliminate inner stock loop (5.35M python calls -> 970 numpy ops)
        for i in range(d - 1, x.shape[0]):
            window = x[i - d + 1:i + 1]  # (d, n_stocks)
            last_val = window[-1]  # (n_stocks,)
            valid_mask = ~np.isnan(window)
            valid_count = np.sum(valid_mask, axis=0)  # (n_stocks,)
            # count values strictly less than last_val (NaN comparisons give False, ok)
            less = np.sum((window < last_val) & valid_mask, axis=0)
            # count values equal to last_val (for average-rank tie handling)
            eq = np.sum((window == last_val) & valid_mask, axis=0)
            # average rank = less + (eq + 1) / 2, percentile = rank / valid_count
            rank = less + (eq + 1.0) / 2.0
            good = (~np.isnan(last_val)) & (valid_count >= 10)
            result[i, good] = rank[good] / valid_count[good]
        return result

    elif func_name == 'ts_max':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d - 1, x.shape[0]):
            result[i] = np.nanmax(x[i - d + 1:i + 1], axis=0)
        return result

    elif func_name == 'ts_min':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d - 1, x.shape[0]):
            result[i] = np.nanmin(x[i - d + 1:i + 1], axis=0)
        return result

    elif func_name == 'ts_sum':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d - 1, x.shape[0]):
            result[i] = np.nansum(x[i - d + 1:i + 1], axis=0)
        return result

    elif func_name == 'ts_corr':
        x = parse_expression(args[0], pipeline, fc)
        y = parse_expression(args[1], pipeline, fc)
        d = int(args[2])
        result = np.full_like(x, np.nan)
        for i in range(d - 1, x.shape[0]):
            for s in range(x.shape[1]):
                xw, yw = x[i - d + 1:i + 1, s], y[i - d + 1:i + 1, s]
                m = ~np.isnan(xw) & ~np.isnan(yw)
                if m.sum() >= 10:
                    result[i, s] = np.corrcoef(xw[m], yw[m])[0, 1]
        return result

    elif func_name == 'rank':
        from scipy import stats
        x = parse_expression(args[0], pipeline, fc)
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            valid = ~np.isnan(x[t])
            if valid.sum() >= 30:
                result[t, valid] = stats.rankdata(x[t, valid]) / valid.sum()
        return result

    elif func_name == 'zscore':
        x = parse_expression(args[0], pipeline, fc)
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            valid = ~np.isnan(x[t])
            if valid.sum() >= 30:
                v = x[t, valid]
                result[t, valid] = (v - np.nanmean(v)) / (np.nanstd(v) + 1e-10)
        return result

    elif func_name == 'demean':
        x = parse_expression(args[0], pipeline, fc)
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            valid = ~np.isnan(x[t])
            if valid.sum() >= 30:
                result[t, valid] = x[t, valid] - np.nanmean(x[t, valid])
        return result

    elif func_name == 'signed_power':
        x = parse_expression(args[0], pipeline, fc)
        e = float(args[1])
        return np.sign(x) * np.power(np.abs(x), e)

    elif func_name == 'group_neutralize':
        x = parse_expression(args[0], pipeline, fc)
        group_field = args[1].strip()
        if group_field == 'market_cap':
            adjf = np.clip(np.where(np.isnan(pipeline.fields.get('I_D_ADJFACTOR',
                np.ones_like(pipeline.fields['I_D_CLOSE_ORI']))), 1.0,
                pipeline.fields.get('I_D_ADJFACTOR',
                np.ones_like(pipeline.fields['I_D_CLOSE_ORI']))), 0.01, 100)
            mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields['I_D_TOTAL_SHARES']
            groups = np.floor(np.log10(np.abs(mcap) + 1)).astype(int)
        else:
            groups = np.zeros_like(x, dtype=int)
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            for g in np.unique(groups[t]):
                gmask = groups[t] == g
                valid = gmask & ~np.isnan(x[t])
                if valid.sum() >= 10:
                    result[t, valid] = x[t, valid] - np.nanmean(x[t, valid])
        return result

    elif func_name == 'ts_delay':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        result[d:] = x[:-d]
        return result

    elif func_name == 'ts_decay_linear':
        x = parse_expression(args[0], pipeline, fc)
        d = int(args[1])
        result = np.full_like(x, np.nan)
        weights = np.arange(1, d+1, dtype=np.float64)  # [1,2,...,d] newest=highest
        weights = weights / weights.sum()
        for i in range(d - 1, x.shape[0]):
            window = x[i - d + 1:i + 1]
            result[i] = np.nansum(window * weights[:, None], axis=0) / np.nansum(
                weights[:, None] * (~np.isnan(window)), axis=0).clip(1e-10)
        return result

    elif func_name == 'ts_backfill':
        x = parse_expression(args[0], pipeline, fc).copy()
        n_rows, n_cols = x.shape
        for s in range(n_cols):
            col = x[:, s]
            last_valid = np.nan
            for t in range(n_rows - 1, -1, -1):
                if not np.isnan(col[t]):
                    last_valid = col[t]
                elif not np.isnan(last_valid):
                    col[t] = last_valid
            x[:, s] = col
        return x

    elif func_name == 'group_rank':
        from scipy import stats
        x = parse_expression(args[0], pipeline, fc)
        group_name = args[1].strip()
        # Get group assignments
        if group_name == 'market_cap':
            adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                    pipeline.fields['I_D_ADJFACTOR']), 0.01, 100)
            mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields['I_D_TOTAL_SHARES']
            groups = np.floor(np.log10(np.abs(mcap) + 1)).astype(int)
        else:
            groups = np.zeros_like(x, dtype=int)
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            for g in np.unique(groups[t]):
                gmask = groups[t] == g
                valid = gmask & ~np.isnan(x[t])
                if valid.sum() >= 10:
                    result[t, valid] = stats.rankdata(x[t, valid]) / valid.sum()
        return result

    elif func_name == 'group_zscore':
        x = parse_expression(args[0], pipeline, fc)
        group_name = args[1].strip()
        if group_name == 'market_cap':
            adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                    pipeline.fields['I_D_ADJFACTOR']), 0.01, 100)
            mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields['I_D_TOTAL_SHARES']
            groups = np.floor(np.log10(np.abs(mcap) + 1)).astype(int)
        else:
            groups = np.zeros_like(x, dtype=int)
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            for g in np.unique(groups[t]):
                gmask = groups[t] == g
                valid = gmask & ~np.isnan(x[t])
                if valid.sum() >= 10:
                    v = x[t, valid]
                    result[t, valid] = (v - np.nanmean(v)) / (np.nanstd(v) + 1e-10)
        return result

    elif func_name == 'ts_regression':
        y = parse_expression(args[0], pipeline, fc)
        x = parse_expression(args[1], pipeline, fc)
        d = int(args[2])
        lag = int(args[3]) if len(args) > 3 else 0
        result = np.full_like(y, np.nan)
        for i in range(d - 1, y.shape[0]):
            xw = x[i - d + 1:i + 1]
            yw = y[i - d + 1:i + 1]
            for s in range(y.shape[1]):
                xc = xw[:, s]; yc = yw[:, s]
                valid = ~np.isnan(xc) & ~np.isnan(yc)
                if valid.sum() >= d // 2:
                    xv = xc[valid]; yv = yc[valid]
                    xv_c = xv - np.nanmean(xv)
                    yv_c = yv - np.nanmean(yv)
                    beta = np.nansum(xv_c * yv_c) / (np.nansum(xv_c * xv_c) + 1e-10)
                    alpha = np.nanmean(yv) - beta * np.nanmean(xv)
                    if lag > 0 and i + lag < y.shape[0]:
                        result[i + lag, s] = y[i + lag, s] - (alpha + beta * x[i + lag, s])
                    else:
                        result[i, s] = yc[-1] - (alpha + beta * xc[-1])
        return result

    elif func_name == 'log':
        x = parse_expression(args[0], pipeline, fc)
        return np.log(np.maximum(x, 1e-10))
    elif func_name == 'exp':
        x = parse_expression(args[0], pipeline, fc)
        return np.exp(np.clip(x, -50, 50))
    elif func_name == 'sqrt':
        x = parse_expression(args[0], pipeline, fc)
        return np.sqrt(np.maximum(x, 0))
    elif func_name == 'abs':
        x = parse_expression(args[0], pipeline, fc)
        return np.abs(x)
    elif func_name == 'sign':
        x = parse_expression(args[0], pipeline, fc)
        return np.sign(x)
    elif func_name == 'power':
        x = parse_expression(args[0], pipeline, fc)
        e = float(args[1])
        return np.power(np.abs(x), e)
    elif func_name == 'if_else':
        cond = parse_expression(args[0], pipeline, fc)
        a = parse_expression(args[1], pipeline, fc)
        b = parse_expression(args[2], pipeline, fc)
        return np.where(cond != 0, a, b)
    elif func_name == 'ts_argmax':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            window = x[i-d+1:i+1]
            all_nan = np.all(np.isnan(window), axis=0)
            valid = ~all_nan
            result[i, valid] = d - 1 - np.nanargmax(window[:, valid], axis=0)
        return result / max(d-1, 1)
    elif func_name == 'ts_argmin':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            window = x[i-d+1:i+1]
            all_nan = np.all(np.isnan(window), axis=0)
            valid = ~all_nan
            result[i, valid] = d - 1 - np.nanargmin(window[:, valid], axis=0)
        return result / max(d-1, 1)
    elif func_name == 'delay':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan); result[d:] = x[:-d]; return result
    elif func_name == 'ts_product':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            window = x[i-d+1:i+1]; prod = np.ones(x.shape[1])
            for s in range(x.shape[1]): w = window[:,s]; prod[s] = np.nanprod(w) if not np.all(np.isnan(w)) else np.nan
            result[i] = prod
        return result
    elif func_name == 'ts_median':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]): result[i] = np.nanmedian(x[i-d+1:i+1], axis=0)
        return result
    elif func_name == 'ts_percentile':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        p = float(args[2]) if len(args) > 2 else 50
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]): result[i] = np.nanpercentile(x[i-d+1:i+1], p, axis=0)
        return result
    elif func_name == 'ts_skew':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            window = x[i-d+1:i+1]  # (d, n_stocks)
            valid_mask = ~np.isnan(window)
            n = np.sum(valid_mask, axis=0)
            mean = np.sum(window * valid_mask, axis=0) / np.maximum(n, 1)
            centered = (window - mean) * valid_mask
            m2 = np.sum(centered**2, axis=0) / np.maximum(n, 1)
            m3 = np.sum(centered**3, axis=0) / np.maximum(n, 1)
            std = np.sqrt(np.maximum(m2, 1e-15))
            result[i] = m3 / np.maximum(std**3, 1e-15)
            result[i, n < 10] = np.nan
        return result
    elif func_name == 'ts_kurt':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            window = x[i-d+1:i+1]  # (d, n_stocks)
            valid_mask = ~np.isnan(window)
            n = np.sum(valid_mask, axis=0)
            mean = np.sum(window * valid_mask, axis=0) / np.maximum(n, 1)
            centered = (window - mean) * valid_mask
            m2 = np.sum(centered**2, axis=0) / np.maximum(n, 1)
            m4 = np.sum(centered**4, axis=0) / np.maximum(n, 1)
            result[i] = m4 / np.maximum(m2**2, 1e-15) - 3.0
            result[i, n < 10] = np.nan
        return result
    elif func_name == 'ts_count':
        x = parse_expression(args[0], pipeline, fc); d = int(args[1])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            result[i] = np.nansum(~np.isnan(x[i-d+1:i+1]), axis=0)
        return result
    elif func_name == 'scale':
        x = parse_expression(args[0], pipeline, fc)
        target = float(args[1]) if len(args) > 1 else 0.0
        result = np.full_like(x, np.nan)
        for t in range(x.shape[0]):
            valid = ~np.isnan(x[t])
            if valid.sum() >= 30: result[t, valid] = (x[t,valid] - np.nanmean(x[t,valid])) * (target / (np.nanstd(x[t,valid]) + 1e-10)) + target
        return result
    elif func_name == 'winsorize':
        x = parse_expression(args[0], pipeline, fc)
        n_std = float(args[1]) if len(args) > 1 else 4.0
        result = x.copy()
        for t in range(x.shape[0]):
            valid = ~np.isnan(x[t])
            if valid.sum() >= 30:
                m, s = np.nanmean(x[t,valid]), np.nanstd(x[t,valid])
                lo, hi = m - n_std*s, m + n_std*s
                result[t, valid] = np.clip(x[t,valid], lo, hi)
        return result
    elif func_name == 'covariance':
        x = parse_expression(args[0], pipeline, fc)
        y = parse_expression(args[1], pipeline, fc); d = int(args[2])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            for s in range(x.shape[1]):
                xw, yw = x[i-d+1:i+1, s], y[i-d+1:i+1, s]
                m = ~np.isnan(xw) & ~np.isnan(yw)
                if m.sum() >= 10: result[i,s] = np.cov(xw[m], yw[m])[0,1]
        return result
    elif func_name == 'regression_slope':
        x = parse_expression(args[0], pipeline, fc)
        y = parse_expression(args[1], pipeline, fc); d = int(args[2])
        result = np.full_like(x, np.nan)
        for i in range(d-1, x.shape[0]):
            for s in range(x.shape[1]):
                xw, yw = x[i-d+1:i+1, s], y[i-d+1:i+1, s]
                m = ~np.isnan(xw) & ~np.isnan(yw)
                if m.sum() >= 10:
                    xv, yv = xw[m], yw[m]
                    xvc = xv - np.nanmean(xv)
                    yvc = yv - np.nanmean(yv)
                    result[i,s] = np.nansum(xvc*yvc) / (np.nansum(xvc*xvc) + 1e-10)
        return result

    raise ValueError(f"未知函数: {func_name}")


def _split_args(s: str) -> list:
    """Split function arguments by commas, respecting nested parentheses."""
    args = []
    depth = 0
    current = ''
    for c in s:
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if c == ',' and depth == 0:
            args.append(current.strip())
            current = ''
        else:
            current += c
    if current.strip():
        args.append(current.strip())
    return args
