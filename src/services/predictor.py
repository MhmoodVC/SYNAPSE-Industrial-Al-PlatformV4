import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from features.preprocessing import clean_trajectory
from features.temporal import rolling_stats, cusum_drift

class PredictorService:
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.sensor_cols = ['pressure', 'flow', 'temperature', 'vibration', 'motor_current']
        
    def predict(self, sensor_window_df: pd.DataFrame):
        """
        Unified inference packaging feature extraction + Stage 1 + Stage 2 into a single call.
        NOTE: detect_onset (PELT) is strictly an offline labeling tool and is NEVER executed 
        in the real-time inference path.
        """
        df_clean = clean_trajectory(sensor_window_df, self.sensor_cols)
        df_feat = rolling_stats(df_clean, self.sensor_cols, windows=[30, 300, 1800])
        df_feat = cusum_drift(df_feat, self.sensor_cols, baseline_window=600)
        
        ignore_cols = ['timestamp', 'run_id', 'pump_id', 'operating_regime', 'pump_state', 
                       'fault_type', 'event_start', 'event_end', 'failure_flag', 
                       'relabeled_fault', 'pelt_onset_idx', 'degradation_stage', 'severity']
        
        feature_cols = [c for c in df_feat.columns if c not in ignore_cols]
        X_infer = df_feat[feature_cols].fillna(0)
        
        preds, probs = self.pipeline.predict(X_infer)
        return preds, probs
