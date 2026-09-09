# FILE: src/models/pipeline.py
#
# *** UNVERIFIED RECONSTRUCTION — NOT YOUR REAL FILE ***
# This class was never pasted into this conversation. Every prior audit
# round ("still outstanding: HierarchicalPipeline.predict() source") flagged
# this exact gap and it was never closed. Do NOT overwrite your working
# pipeline.py with this without diffing against the real file first —
# specifically check: (1) how 'transition'-labeled test frames are handled
# on the way through (Stage 2 was never trained on 'transition' as a class),
# and (2) whether stage1_prob_anomalous column injection here matches what
# Stage 2 was actually trained on, column-order and all.
from typing import Tuple

import numpy as np
import pandas as pd

from models.stage1_gate import Stage1Gate
from models.stage2_classifier import Stage2Classifier


class HierarchicalPipeline:
    def __init__(self, stage1: Stage1Gate, stage2: Stage2Classifier) -> None:
        self.stage1 = stage1
        self.stage2 = stage2

    def predict(self, X: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        stage1_probs = self.stage1.predict_proba(X)[:, 1]
        is_anomalous = stage1_probs >= self.stage1.operating_threshold

        preds = np.full(len(X), "normal", dtype=object)

        if is_anomalous.any():
            mask = is_anomalous.to_numpy() if hasattr(is_anomalous, "to_numpy") else is_anomalous
            X_anomalous = X.loc[mask].copy() if hasattr(X, "loc") else X[mask].copy()
            X_anomalous["stage1_prob_anomalous"] = stage1_probs[mask]
            stage2_preds = self.stage2.predict(X_anomalous)
            preds[mask] = stage2_preds

        return preds, stage1_probs