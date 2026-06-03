"""Add 30+ new derived fields to expression_parser.py."""
import re

path = "D:/yyb/backtest_platform/expression_parser.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

new_funcs = r"""
# ---- New derived fields (batch added 2026-05-19) ----

def _compute_ret_10d(p): c=p.fields['I_D_CLOSE_ORI']; r=np.full_like(c,np.nan); r[10:]=c[10:]/c[:-10]-1; return r
def _compute_ret_40d(p): c=p.fields['I_D_CLOSE_ORI']; r=np.full_like(c,np.nan); r[40:]=c[40:]/c[:-40]-1; return r
def _compute_vol_5d(p): ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(4,ret.shape[0]): r[i]=np.nanstd(ret[i-4:i+1],axis=0)
return r
def _compute_vol_10d(p): ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(9,ret.shape[0]): r[i]=np.nanstd(ret[i-9:i+1],axis=0)
return r
def _compute_vol_40d(p): ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(39,ret.shape[0]): r[i]=np.nanstd(ret[i-39:i+1],axis=0)
return r
def _compute_vol_120d(p): ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(119,ret.shape[0]): r[i]=np.nanstd(ret[i-119:i+1],axis=0)
return r
def _compute_upside_vol_60d(p): ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(59,ret.shape[0]): w=ret[i-59:i+1]; pos=w.copy(); pos[pos<0]=np.nan; r[i]=np.nanstd(pos,axis=0)
return r
def _compute_down_up_vol_ratio(p): d=_compute_downside_vol_60d(p); u=_compute_upside_vol_60d(p); return d/(u+np.float32(1e-10))
def _compute_adv5(p): import numpy as np; v=p.fields['I_D_VOLUME']; r=np.full_like(v,np.nan)
for i in range(4,v.shape[0]): r[i]=np.nanmean(v[i-4:i+1],axis=0)
return r
def _compute_adv20(p): import numpy as np; v=p.fields['I_D_VOLUME']; r=np.full_like(v,np.nan)
for i in range(19,v.shape[0]): r[i]=np.nanmean(v[i-19:i+1],axis=0)
return r
def _compute_dollar_volume(p): return p.fields['I_D_CLOSE_ORI'].astype(np.float64)*p.fields['I_D_VOLUME'].astype(np.float64)
def _compute_gap_down(p): o=p.fields['I_D_OPEN_ORI']; pc=p.fields['I_D_PRECLOSE_ORI']; return np.maximum(np.float32(0),pc-o)/(pc+np.float32(1e-10))
def _compute_close_vs_low_20d(p): import numpy as np; c=p.fields['I_D_CLOSE_ORI']; r=np.full_like(c,np.nan)
for i in range(19,c.shape[0]): r[i]=c[i]/(np.nanmin(p.fields['I_D_LOW_ORI'][i-19:i+1],axis=0)+np.float32(1e-10))
return r
def _compute_doji_score(p): o=p.fields['I_D_OPEN_ORI']; c=p.fields['I_D_CLOSE_ORI']; h=p.fields['I_D_HIGH_ORI']; l=p.fields['I_D_LOW_ORI']; return np.float32(1)-np.abs(c-o)/(h-l+np.float32(1e-10))
def _compute_cumret_5d(p): import numpy as np; ret=_compute_returns(p); r=np.full_like(ret,np.nan)
for i in range(4,ret.shape[0]): r[i]=np.nanprod(np.float64(1)+ret[i-4:i+1],axis=0).astype(np.float32)-np.float32(1)
return r
def _compute_max_ret_20d(p): import numpy as np; ret=_compute_returns(p); r=np.full_like(ret,np.nan)
for i in range(19,ret.shape[0]): r[i]=np.nanmax(ret[i-19:i+1],axis=0)
return r
def _compute_min_ret_20d(p): import numpy as np; ret=_compute_returns(p); r=np.full_like(ret,np.nan)
for i in range(19,ret.shape[0]): r[i]=np.nanmin(ret[i-19:i+1],axis=0)
return r
def _compute_hit_rate_20d(p): import numpy as np; ret=_compute_returns(p); r=np.full_like(ret,np.nan)
for i in range(19,ret.shape[0]): r[i]=np.nanmean(ret[i-19:i+1]>np.float32(0),axis=0)
return r
def _compute_hit_rate_60d(p): import numpy as np; ret=_compute_returns(p); r=np.full_like(ret,np.nan)
for i in range(59,ret.shape[0]): r[i]=np.nanmean(ret[i-59:i+1]>np.float32(0),axis=0)
return r
def _compute_rev_10d(p): return -_compute_ret_10d(p)
def _compute_rev_20d(p): return -_compute_ret_20d(p)
def _compute_skewness_20d(p): from scipy import stats; ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(19,ret.shape[0]):
    for s in range(ret.shape[1]): w=ret[i-19:i+1,s]; v=w[~np.isnan(w)]; r[i,s]=stats.skew(v) if len(v)>=10 else np.nan
return r
def _compute_kurtosis_60d(p): from scipy import stats; ret=_compute_returns(p); import numpy as np; r=np.full_like(ret,np.nan)
for i in range(59,ret.shape[0]):
    for s in range(ret.shape[1]): w=ret[i-59:i+1,s]; v=w[~np.isnan(w)]; r[i,s]=stats.kurtosis(v) if len(v)>=10 else np.nan
return r
def _compute_vol_ratio_5_20(p): return _compute_vol_5d(p)/(_compute_vol_20d(p)+np.float32(1e-10))
def _compute_vol_ratio_20_60(p): return _compute_vol_20d(p)/(_compute_vol_60d(p)+np.float32(1e-10))
def _compute_bollinger_width(p): import numpy as np; c=p.fields['I_D_CLOSE_ORI']; r=np.full_like(c,np.nan)
for i in range(19,c.shape[0]): ma=np.nanmean(c[i-19:i+1],axis=0); std=np.nanstd(c[i-19:i+1],axis=0); r[i]=np.float32(4)*std/(ma+np.float32(1e-10))
return r
def _compute_volume_trend_20d(p): from scipy import stats; import numpy as np; v=p.fields['I_D_VOLUME']; r=np.full_like(v,np.nan)
for i in range(19,v.shape[0]):
    for s in range(v.shape[1]): w=v[i-19:i+1,s]; vv=w[~np.isnan(w)]; r[i,s]=stats.rankdata(vv)[-1]/len(vv) if len(vv)>=5 else np.nan
return r
def _compute_intraday_reversal(p): return -_compute_first30min_return(p)*_compute_last30min_return(p)
def _compute_rev_vol_regime(p): return _compute_rev_5d(p)*_compute_vol_20d(p)
def _compute_volume_price_div(p): return _compute_returns(p)*_compute_volume_trend_20d(p)
def _compute_gap_momentum(p): return _compute_auction_return(p)*_compute_returns(p)
def _compute_amount_volatility(p): v=p.fields['I_D_AMOUNT']; import numpy as np; r=np.full_like(v,np.nan)
for i in range(19,v.shape[0]): r[i]=np.nanstd(v[i-19:i+1],axis=0)/(np.nanmean(v[i-19:i+1],axis=0)+1e-10)
return r
def _compute_volume_price_corr(p): import numpy as np; v=p.fields['I_D_VOLUME']; ret=_compute_returns(p); r=np.full_like(v,np.nan)
for i in range(19,v.shape[0]):
    for s in range(v.shape[1]): vw,ww=v[i-19:i+1,s],ret[i-19:i+1,s]; m=~np.isnan(vw)&~np.isnan(ww)
    if m.sum()>=10: r[i,s]=np.corrcoef(vw[m],ww[m])[0,1]
return r
"""

# Find insertion point
marker = "# ---- Registry: maps field name -> compute function"
idx = src.find(marker)
if idx > 0:
    src = src[:idx] + new_funcs + "\n" + src[idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print("30+ compute functions injected")
else:
    print("ERROR: marker not found at", idx)

# Verify
import sys; sys.path.insert(0, "D:/yyb/backtest_platform")
from expression_parser import DERIVED_FIELD_REGISTRY
print(f"Current registry size: {len(DERIVED_FIELD_REGISTRY)}")
