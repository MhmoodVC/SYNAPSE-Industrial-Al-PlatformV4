import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from features.preprocessing import clean_trajectory
from features.temporal import rolling_stats, cusum_drift

DATA_PATH = PROJECT_ROOT / "data" / "processed" / "relabeled_v2.parquet"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "features_v2.parquet"

def main():
    print("Loading relabeled data...")
    df = pd.read_parquet(DATA_PATH)
    sensor_cols = ['pressure', 'flow', 'temperature', 'vibration', 'motor_current']
    
    print("Cleaning trajectories...")
    df_clean = clean_trajectory(df, sensor_cols)
    
    print("Extracting rolling statistics...")
    df_features = rolling_stats(df_clean, sensor_cols, windows=[30, 300, 1800])
    
    print("Extracting CUSUM drift features...")
    df_features = cusum_drift(df_features, sensor_cols, baseline_window=600)
    
    out_dir = OUT_PATH.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    df_features.to_parquet(OUT_PATH)
    print(f"Saved feature dataset to {OUT_PATH}")

if __name__ == '__main__':
    main()
