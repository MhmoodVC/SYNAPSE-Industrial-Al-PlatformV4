import numpy as np
import pandas as pd
import ruptures as rpt
from typing import List, Tuple
from features.preprocessing import clean_trajectory

def detect_onset(trajectory_df: pd.DataFrame, sensor_cols: List[str], method: str = "pelt") -> Tuple[int, int]:
    df_clean = clean_trajectory(trajectory_df, sensor_cols)
    data = df_clean[sensor_cols].values
    n, d = data.shape
    
    baseline_len = min(100, n)
    baseline_data = data[:baseline_len]
    
    medians = np.median(baseline_data, axis=0)
    mads = np.median(np.abs(baseline_data - medians), axis=0)
    mads[mads == 0] = 1.0 
    norm_data = (data - medians) / (1.4826 * mads)
    
    if method == "pelt":
        algo = rpt.Pelt(model="rbf").fit(norm_data)
        pen = np.log(n) * d * 2.0 
        result = algo.predict(pen=pen)
        
        valid_cps = [cp for cp in result if cp >= baseline_len and cp < n]
        num_cps = len(result) - 1
        
        if valid_cps:
            return valid_cps[0], num_cps
        else:
            return n - 1, num_cps
    else:
        raise ValueError(f"Method {method} not implemented")

def relabel_trajectory(trajectory_df: pd.DataFrame, gt_onset_idx: int, pelt_onset_idx: int) -> pd.DataFrame:
    df = trajectory_df.copy()
    terminal_fault = df['fault_type'].iloc[-1]
    
    LAG_BUFFERS = {'sensor_drift': 131, 'flow_restriction': 106, 'cavitation': 104, 
                   'motor_overload': 59, 'overheating': 59, 'pressure_loss': 44, 'default': 5}
    buffer_len = LAG_BUFFERS.get(terminal_fault, LAG_BUFFERS['default'])
    
    new_labels = np.full(len(df), 'normal', dtype=object)
    
    start_transition = max(0, gt_onset_idx - 10)
    end_transition = min(len(df), gt_onset_idx + buffer_len)
    
    if terminal_fault != 'normal':
        new_labels[end_transition:] = terminal_fault
        new_labels[start_transition:end_transition] = 'transition'
        
    df['relabeled_fault'] = new_labels
    df['pelt_onset_idx'] = pelt_onset_idx
    return df
