import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from features.changepoint import detect_onset, relabel_trajectory

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "synthetic_pump_dataset.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "relabeled_v2.parquet"

def main():
    df = pd.read_csv(DATA_PATH)
    sensor_cols = ['pressure', 'flow', 'temperature', 'vibration', 'motor_current']
    
    relabeled_dfs = []
    for run_id, group in df.groupby('run_id'):
        group = group.sort_values(by='timestamp').reset_index(drop=True)
        gt_onsets = group.index[group['degradation_stage'] > 0.0].tolist()
        if group['fault_type'].iloc[0] == 'normal':
            gt_onset = len(group) - 1
        else:
            gt_onset = gt_onsets[0] if gt_onsets else len(group) - 1
            
        pelt_onset, num_cps = detect_onset(group, sensor_cols, method="pelt")
        
        relabeled = relabel_trajectory(group, gt_onset, pelt_onset)
        relabeled_dfs.append(relabeled)
        
    final_df = pd.concat(relabeled_dfs, ignore_index=True)
    out_dir = OUT_PATH.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    final_df.to_parquet(OUT_PATH)
    print(f"Successfully generated and saved {len(final_df)} frames to {OUT_PATH}")

if __name__ == '__main__':
    main()
