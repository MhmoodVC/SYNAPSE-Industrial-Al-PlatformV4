import pandas as pd
from typing import List

def clean_trajectory(df: pd.DataFrame, sensor_cols: List[str]) -> pd.DataFrame:
    """
    Imputes NaNs using causal ffill() per trajectory, with a safe leading edge fallback (bfill()).
    """
    df_clean = df.copy()
    df_clean[sensor_cols] = df_clean[sensor_cols].ffill().bfill()
    return df_clean
