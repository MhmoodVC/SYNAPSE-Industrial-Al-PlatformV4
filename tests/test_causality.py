import numpy as np
import pandas as pd
from features.temporal import rolling_stats, cusum_drift

def test_causality():
    # Create dummy dataset
    np.random.seed(42)
    n = 100
    df = pd.DataFrame({
        'run_id': ['run1'] * n + ['run2'] * n,
        'sensor1': np.random.randn(2 * n),
        'sensor2': np.random.randn(2 * n)
    })
    
    cols = ['sensor1', 'sensor2']
    
    # Compute on full
    df_full_rolling = rolling_stats(df, cols, windows=[10])
    df_full_cusum = cusum_drift(df_full_rolling, cols, baseline_window=20)
    
    # Target frame to test causality
    t = 45 # index within run1
    
    # Slice up to t
    df_sub = df.iloc[:t + 1].copy()
    
    # Compute on sliced
    df_sub_rolling = rolling_stats(df_sub, cols, windows=[10])
    df_sub_cusum = cusum_drift(df_sub_rolling, cols, baseline_window=20)
    
    # Compare row at index t
    row_full = df_full_cusum.iloc[t]
    row_sub = df_sub_cusum.iloc[t]
    
    # Check all feature columns
    feat_cols = [c for c in df_full_cusum.columns if c not in ['run_id', 'sensor1', 'sensor2']]
    for c in feat_cols:
        val_full = row_full[c]
        val_sub = row_sub[c]
        assert np.isclose(val_full, val_sub, equal_nan=True), f"Causality leak in {c}! Full: {val_full}, Sub: {val_sub}"
