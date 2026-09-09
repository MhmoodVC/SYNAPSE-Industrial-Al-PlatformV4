# FILE: src/realtime/live_features.py
"""Live feature extraction for streaming sensor data.

Maintains rolling buffers and computes features incrementally using the same
logic as extract_features.py (rolling_stats + cusum_drift), ensuring perfect
alignment with the 76 features the frozen model expects.
"""
import sys
from pathlib import Path
from collections import deque
from typing import Dict, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from features.preprocessing import clean_trajectory
from features.temporal import rolling_stats, cusum_drift


class LiveFeatureExtractor:
    """Incrementally computes rolling features from a live sensor stream."""

    def __init__(self, max_buffer_size: int = 1800) -> None:
        """
        Args:
            max_buffer_size: Maximum rows to keep in memory (must be ≥ 1800
                             to support the largest rolling window).
        """
        self.max_buffer_size = max_buffer_size
        self.sensor_cols = ['pressure', 'flow', 'temperature', 'vibration', 'motor_current']
        self.buffer = deque(maxlen=max_buffer_size)
        self.run_id = "live_stream"  # Single trajectory for live data

    def add_reading(
        self,
        pressure: Optional[float],
        flow: Optional[float],
        temperature: Optional[float],
        vibration: Optional[float],
        motor_current: Optional[float],
        operating_load: float = 0.70,
    ) -> None:
        """Add a new sensor reading to the rolling buffer."""
        self.buffer.append({
            'run_id': self.run_id,
            'pressure': pressure,
            'flow': flow,
            'temperature': temperature,
            'vibration': vibration,
            'motor_current': motor_current,
            'operating_load': operating_load,
        })

    def compute_features(self) -> Optional[pd.DataFrame]:
        """
        Compute the full 76-feature vector from the current buffer.

        Returns:
            DataFrame with 1 row and 76 columns (matching frozen model's
            feature_cols), or None if buffer is empty.
        """
        if not self.buffer:
            return None

        # Convert buffer to DataFrame
        df = pd.DataFrame(list(self.buffer))

        # Apply same preprocessing as training
        df_clean = clean_trajectory(df, self.sensor_cols)

        # Rolling stats (30, 300, 1800)
        df_features = rolling_stats(df_clean, self.sensor_cols, windows=[30, 300, 1800])

        # CUSUM drift
        df_features = cusum_drift(df_features, self.sensor_cols, baseline_window=600)

        # Return only the LAST row (current features), drop run_id
        return df_features.iloc[[-1]].drop(columns=['run_id']).reset_index(drop=True)

    def reset(self) -> None:
        """Clear the buffer (e.g., when starting a new run)."""
        self.buffer.clear()