"""Shared eligibility policy for yyb factor mining and dedup."""
import re

MINUTE_FIELDS = {
    'intraday_volatility', 'price_efficiency', 'vwap_gap',
    'volume_concentration', 'close_location', 'upper_shadow_pct',
    'lower_shadow_pct', 'morning_return', 'afternoon_return',
    'first30min_return', 'last30min_return', 'body_return',
    'am_pm_divergence',
}

MICRO_FIELDS = {
    'first30_mom', 'last30_mom', 'intraday_mom', 'realized_vol',
    'vol_skew', 'close_vs_vwap', 'vwap_trend', 'volume_hhi',
    'open_vol_ratio', 'close_vol_ratio', 'smart_money_vol',
    'amihud_min', 'vpin', 'large_trade_ratio', 'roll_spread',
    'opening_confirm', 'vpin_informed', 'overnight_reversal',
    'amihud_hybrid', 'close_manipulation', 'triple_confirm', 'wat',
    'large_trade_signal', 'smart_money_vwap', 'vol_conc_mom',
}

ECON_DAILY_FIELDS = {
    'auction_return', 'volume_profile_ratio', 'turnover_rate',
    'ret_5d', 'ret_60d', 'ret_120d_skip5', 'sharpe_60d',
    'mom_vol_adj', 'max_dd_60d', 'close_vs_high_20d',
    'rev_1d', 'rev_overnight', 'abnormal_vol_rev',
    'extreme_loser_5d', 'extreme_winner_5d',
    'ret_10d', 'ret_20d', 'ret_40d', 'cumret_5d',
    'vol_5d', 'vol_10d', 'vol_20d', 'vol_40d', 'vol_60d',
    'vol_120d', 'upside_vol_60d', 'downside_vol_60d',
    'down_up_vol_ratio', 'vol_ratio', 'vol_ratio_20_60',
    'vol_ratio_5_20', 'bollinger_width', 'adv5', 'adv20',
    'dollar_volume', 'volume_breakout', 'turnover_5d',
    'turnover_change', 'log_dollar_vol', 'volume_trend_20d', 'amount_volatility',
    'volume_price_corr', 'gap_down', 'gap_up', 'close_vs_low_20d',
    'upper_shadow', 'lower_shadow', 'body_ratio',
    'doji_score', 'rev_5d', 'rev_10d', 'rev_20d', 'rev_vol_regime',
    'skewness_20d', 'skewness_60d', 'kurtosis_60d',
    'max_ret_20d', 'min_ret_20d', 'hit_rate_20d', 'hit_rate_60d',
    'intraday_reversal', 'volume_price_div', 'gap_momentum',
    'amihud_20d', 'market_cap_rank', 'rsi_14', 'bollinger_pos',
    'beta_60d', 'mom_vol_conf', 'mom_liquidity_adj', 'rev_vol_conf',
    'intraday_ret5d', 'vwap_close_mom', 'smart_money_rev',
    'liquidity_premium',
}

ELIGIBLE_FIELDS = MINUTE_FIELDS | MICRO_FIELDS | ECON_DAILY_FIELDS

ALLOWED_FUNCTIONS = {
    'rank', 'zscore', 'demean', 'ts_delta', 'ts_rank', 'ts_mean',
    'ts_std', 'ts_corr', 'ts_min', 'ts_max', 'ts_sum', 'ts_delay',
    'ts_decay_linear', 'signed_power', 'abs', 'winsorize',
    'group_neutralize', 'group_rank', 'group_zscore',
}


def identifiers(expr: str) -> set:
    return set(re.findall(r'\b[A-Za-z_]\w*\b', expr or ''))


def eligible_expr(expr: str) -> bool:
    names = identifiers(expr)
    return bool(names & ELIGIBLE_FIELDS) and names <= (ELIGIBLE_FIELDS | ALLOWED_FUNCTIONS)
