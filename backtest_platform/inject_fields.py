"""Inject new derived field functions into expression_parser.py with proper indentation."""
import os

PATH = os.path.join(os.path.dirname(__file__), 'expression_parser.py')

FUNCTIONS = [
    # (name, code_lines)
    ("_compute_ret_10d", [
        "def _compute_ret_10d(pipeline):",
        "    c = pipeline.fields['I_D_CLOSE_ORI']",
        "    r = np.full_like(c, np.nan)",
        "    r[10:] = c[10:] / c[:-10] - 1",
        "    return r",
    ]),
    ("_compute_ret_40d", [
        "def _compute_ret_40d(pipeline):",
        "    c = pipeline.fields['I_D_CLOSE_ORI']",
        "    r = np.full_like(c, np.nan)",
        "    r[40:] = c[40:] / c[:-40] - 1",
        "    return r",
    ]),
    ("_compute_vol_5d", [
        "def _compute_vol_5d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(4, ret.shape[0]):",
        "        r[i] = np.nanstd(ret[i-4:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_vol_10d", [
        "def _compute_vol_10d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(9, ret.shape[0]):",
        "        r[i] = np.nanstd(ret[i-9:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_vol_40d", [
        "def _compute_vol_40d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(39, ret.shape[0]):",
        "        r[i] = np.nanstd(ret[i-39:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_vol_120d", [
        "def _compute_vol_120d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(119, ret.shape[0]):",
        "        r[i] = np.nanstd(ret[i-119:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_upside_vol_60d", [
        "def _compute_upside_vol_60d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(59, ret.shape[0]):",
        "        w = ret[i-59:i+1].copy()",
        "        w[w < 0] = np.nan",
        "        r[i] = np.nanstd(w, axis=0)",
        "    return r",
    ]),
    ("_compute_down_up_vol_ratio", [
        "def _compute_down_up_vol_ratio(pipeline):",
        "    return _compute_downside_vol_60d(pipeline) / (_compute_upside_vol_60d(pipeline) + np.float32(1e-10))",
    ]),
    ("_compute_adv5", [
        "def _compute_adv5(pipeline):",
        "    v = pipeline.fields['I_D_VOLUME']",
        "    r = np.full_like(v, np.nan)",
        "    for i in range(4, v.shape[0]):",
        "        r[i] = np.nanmean(v[i-4:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_adv20", [
        "def _compute_adv20(pipeline):",
        "    v = pipeline.fields['I_D_VOLUME']",
        "    r = np.full_like(v, np.nan)",
        "    for i in range(19, v.shape[0]):",
        "        r[i] = np.nanmean(v[i-19:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_dollar_volume", [
        "def _compute_dollar_volume(pipeline):",
        "    return pipeline.fields['I_D_CLOSE_ORI'] * pipeline.fields['I_D_VOLUME']",
    ]),
    ("_compute_gap_down", [
        "def _compute_gap_down(pipeline):",
        "    o = pipeline.fields['I_D_OPEN_ORI']",
        "    pc = pipeline.fields['I_D_PRECLOSE_ORI']",
        "    return np.maximum(np.float32(0), pc - o) / (pc + np.float32(1e-10))",
    ]),
    ("_compute_close_vs_low_20d", [
        "def _compute_close_vs_low_20d(pipeline):",
        "    c = pipeline.fields['I_D_CLOSE_ORI']",
        "    r = np.full_like(c, np.nan)",
        "    for i in range(19, c.shape[0]):",
        "        r[i] = c[i] / (np.nanmin(pipeline.fields['I_D_LOW_ORI'][i-19:i+1], axis=0) + np.float32(1e-10))",
        "    return r",
    ]),
    ("_compute_doji_score", [
        "def _compute_doji_score(pipeline):",
        "    o = pipeline.fields['I_D_OPEN_ORI']",
        "    c = pipeline.fields['I_D_CLOSE_ORI']",
        "    h = pipeline.fields['I_D_HIGH_ORI']",
        "    l = pipeline.fields['I_D_LOW_ORI']",
        "    return np.float32(1) - np.abs(c - o) / (h - l + np.float32(1e-10))",
    ]),
    ("_compute_cumret_5d", [
        "def _compute_cumret_5d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(4, ret.shape[0]):",
        "        r[i] = np.nanprod(np.float64(1) + ret[i-4:i+1], axis=0).astype(np.float32) - np.float32(1)",
        "    return r",
    ]),
    ("_compute_max_ret_20d", [
        "def _compute_max_ret_20d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(19, ret.shape[0]):",
        "        r[i] = np.nanmax(ret[i-19:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_min_ret_20d", [
        "def _compute_min_ret_20d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(19, ret.shape[0]):",
        "        r[i] = np.nanmin(ret[i-19:i+1], axis=0)",
        "    return r",
    ]),
    ("_compute_hit_rate_20d", [
        "def _compute_hit_rate_20d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(19, ret.shape[0]):",
        "        r[i] = np.nanmean(ret[i-19:i+1] > np.float32(0), axis=0)",
        "    return r",
    ]),
    ("_compute_hit_rate_60d", [
        "def _compute_hit_rate_60d(pipeline):",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(59, ret.shape[0]):",
        "        r[i] = np.nanmean(ret[i-59:i+1] > np.float32(0), axis=0)",
        "    return r",
    ]),
    ("_compute_rev_10d", [
        "def _compute_rev_10d(pipeline):",
        "    return -_compute_ret_10d(pipeline)",
    ]),
    ("_compute_rev_20d", [
        "def _compute_rev_20d(pipeline):",
        "    return -_compute_ret_20d(pipeline)",
    ]),
    ("_compute_skewness_20d", [
        "def _compute_skewness_20d(pipeline):",
        "    from scipy import stats",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(19, ret.shape[0]):",
        "        for s in range(ret.shape[1]):",
        "            w = ret[i-19:i+1, s]",
        "            v = w[~np.isnan(w)]",
        "            if len(v) >= 10:",
        "                r[i, s] = stats.skew(v)",
        "    return r",
    ]),
    ("_compute_kurtosis_60d", [
        "def _compute_kurtosis_60d(pipeline):",
        "    from scipy import stats",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(ret, np.nan)",
        "    for i in range(59, ret.shape[0]):",
        "        for s in range(ret.shape[1]):",
        "            w = ret[i-59:i+1, s]",
        "            v = w[~np.isnan(w)]",
        "            if len(v) >= 10:",
        "                r[i, s] = stats.kurtosis(v)",
        "    return r",
    ]),
    ("_compute_vol_ratio_5_20", [
        "def _compute_vol_ratio_5_20(pipeline):",
        "    return _compute_vol_5d(pipeline) / (_compute_vol_20d(pipeline) + np.float32(1e-10))",
    ]),
    ("_compute_vol_ratio_20_60", [
        "def _compute_vol_ratio_20_60(pipeline):",
        "    return _compute_vol_20d(pipeline) / (_compute_vol_60d(pipeline) + np.float32(1e-10))",
    ]),
    ("_compute_bollinger_width", [
        "def _compute_bollinger_width(pipeline):",
        "    c = pipeline.fields['I_D_CLOSE_ORI']",
        "    r = np.full_like(c, np.nan)",
        "    for i in range(19, c.shape[0]):",
        "        ma = np.nanmean(c[i-19:i+1], axis=0)",
        "        std = np.nanstd(c[i-19:i+1], axis=0)",
        "        r[i] = np.float32(4) * std / (ma + np.float32(1e-10))",
        "    return r",
    ]),
    ("_compute_intraday_reversal", [
        "def _compute_intraday_reversal(pipeline):",
        "    return -_compute_first30min_return(pipeline) * _compute_last30min_return(pipeline)",
    ]),
    ("_compute_rev_vol_regime", [
        "def _compute_rev_vol_regime(pipeline):",
        "    return _compute_rev_5d(pipeline) * _compute_vol_20d(pipeline)",
    ]),
    ("_compute_volume_price_div", [
        "def _compute_volume_price_div(pipeline):",
        "    return _compute_returns(pipeline) * _compute_volume_trend_20d(pipeline)",
    ]),
    ("_compute_gap_momentum", [
        "def _compute_gap_momentum(pipeline):",
        "    return _compute_auction_return(pipeline) * _compute_returns(pipeline)",
    ]),
    ("_compute_amount_volatility", [
        "def _compute_amount_volatility(pipeline):",
        "    v = pipeline.fields['I_D_AMOUNT']",
        "    r = np.full_like(v, np.nan)",
        "    for i in range(19, v.shape[0]):",
        "        r[i] = np.nanstd(v[i-19:i+1], axis=0) / (np.nanmean(v[i-19:i+1], axis=0) + 1e-10)",
        "    return r",
    ]),
    ("_compute_volume_price_corr", [
        "def _compute_volume_price_corr(pipeline):",
        "    v = pipeline.fields['I_D_VOLUME']",
        "    ret = _compute_returns(pipeline)",
        "    r = np.full_like(v, np.nan)",
        "    for i in range(19, v.shape[0]):",
        "        for s in range(v.shape[1]):",
        "            vw = v[i-19:i+1, s]",
        "            rw = ret[i-19:i+1, s]",
        "            m = ~np.isnan(vw) & ~np.isnan(rw)",
        "            if m.sum() >= 10:",
        "                r[i, s] = np.corrcoef(vw[m], rw[m])[0, 1]",
        "    return r",
    ]),
    ("_compute_volume_trend_20d", [
        "def _compute_volume_trend_20d(pipeline):",
        "    from scipy import stats",
        "    v = pipeline.fields['I_D_VOLUME']",
        "    r = np.full_like(v, np.nan)",
        "    for i in range(19, v.shape[0]):",
        "        for s in range(v.shape[1]):",
        "            w = v[i-19:i+1, s]",
        "            vv = w[~np.isnan(w)]",
        "            if len(vv) >= 5:",
        "                r[i, s] = stats.rankdata(vv)[-1] / len(vv)",
        "    return r",
    ]),
]

# Generate function code
func_code = "\n\n# ---- New derived fields (batch-injected) ----\n\n"
for name, lines in FUNCTIONS:
    func_code += "\n".join(lines) + "\n\n"

# Read source
with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# Insert before DERIVED_FIELD_REGISTRY
marker = "# ---- Registry: maps field name -> compute function"
idx = src.find(marker)
assert idx > 0, "Registry marker not found"
src = src[:idx] + func_code + src[idx:]

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

# Verify syntax
import py_compile
try:
    py_compile.compile(PATH, doraise=True)
    print(f"OK: {len(FUNCTIONS)} functions injected, syntax clean")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")

# Verify imports
import sys; sys.path.insert(0, os.path.dirname(__file__))
from expression_parser import DERIVED_FIELD_REGISTRY
print(f"Registry size before: {len(DERIVED_FIELD_REGISTRY)}")
