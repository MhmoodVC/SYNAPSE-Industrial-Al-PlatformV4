import numpy as np
import pandas as pd
from features.preprocessing import clean_trajectory

def rolling_stats(df: pd.DataFrame, cols: list, windows=[30, 300, 1800]) -> pd.DataFrame:
    out_df = df.copy()
    for w in windows:
        grouped = out_df.groupby('run_id')[cols]
        
        # Mean
        mean_cols = {c: f"{c}_mean_{w}" for c in cols}
        means = grouped.transform(lambda x: x.rolling(w, min_periods=1, center=False).mean())
        out_df = out_df.join(means.rename(columns=mean_cols))
        
        # Std
        std_cols = {c: f"{c}_std_{w}" for c in cols}
        stds = grouped.transform(lambda x: x.rolling(w, min_periods=1, center=False).std().fillna(0))
        out_df = out_df.join(stds.rename(columns=std_cols))
        
        # Skew
        skew_cols = {c: f"{c}_skew_{w}" for c in cols}
        skews = grouped.transform(lambda x: x.rolling(w, min_periods=1, center=False).skew().fillna(0))
        out_df = out_df.join(skews.rename(columns=skew_cols))
        
        # Kurtosis
        kurt_cols = {c: f"{c}_kurt_{w}" for c in cols}
        kurts = grouped.transform(lambda x: x.rolling(w, min_periods=1, center=False).kurt().fillna(0))
        out_df = out_df.join(kurts.rename(columns=kurt_cols))
        
    return out_df

def cusum_drift(df: pd.DataFrame, cols: list, baseline_window=600) -> pd.DataFrame:
    out_df = df.copy()
    
    for c in cols:
        sh_col = f"{c}_cusum_pos"
        sl_col = f"{c}_cusum_neg"
        
        # Preallocate
        out_df[sh_col] = 0.0
        out_df[sl_col] = 0.0
        
        for run_id, group in out_df.groupby('run_id'):
            vals = group[c].values
            mu = pd.Series(vals).rolling(baseline_window, min_periods=1).mean().values
            sigma = pd.Series(vals).rolling(baseline_window, min_periods=1).std().fillna(1.0).values
            sigma[sigma == 0] = 1.0
            k = 0.5 * sigma
            
            SH = np.zeros(len(vals))
            SL = np.zeros(len(vals))
            for i in range(1, len(vals)):
                SH[i] = max(0, SH[i-1] + vals[i] - mu[i] - k[i])
                SL[i] = min(0, SL[i-1] + vals[i] - mu[i] + k[i])
                
            out_df.loc[group.index, sh_col] = SH
            out_df.loc[group.index, sl_col] = SL
            
    return out_df
