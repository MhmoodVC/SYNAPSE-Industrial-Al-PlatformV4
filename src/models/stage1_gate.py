# FILE: src/models/stage1_gate.py
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, ClassifierMixin as _CM, clone
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold


class GroupedCalibratedClassifier(BaseEstimator, ClassifierMixin):
    """Hand-rolled grouped-calibration ensemble, replacing CalibratedClassifierCV.

    Two separate CalibratedClassifierCV failures in this sklearn version
    forced this:
      1. `fit(X, y, groups=...)` raised ValueError — groups is not routed to
         the internal splitter at all in this version.
      2. Precomputing GroupKFold splits and passing them as `cv=<list>`
         worked for a direct fit, but broke under clone()+refit-on-a-subset
         (what cross_val_predict does for its own OOF folds) — the frozen
         integer indices no longer matched the smaller subset's row count,
         raising IndexError.

    This class avoids both: it stores only `base_model` and `n_splits` as
    constructor params (so sklearn's clone() correctly resets it to unfitted
    state), and computes the GroupKFold split freshly, inside fit(), against
    whatever X/y/groups is actually passed that call. Correct whether fit on
    the full training set or on a cross_val_predict subset.
    """

    def __init__(self, base_model: ClassifierMixin, n_splits: int = 3) -> None:
        self.base_model = base_model
        self.n_splits = n_splits

    def fit(self, X: pd.DataFrame, y: np.ndarray, groups: Optional[pd.Series] = None) -> "GroupedCalibratedClassifier":
        if groups is None:
            raise ValueError("`groups` (run_id) is required for grouped calibration.")

        X_ = X.reset_index(drop=True) if hasattr(X, "reset_index") else X
        y_ = np.asarray(y)
        groups_ = np.asarray(groups)

        cv = GroupKFold(n_splits=self.n_splits)
        self.fold_pairs_: List[Tuple[ClassifierMixin, IsotonicRegression]] = []

        for train_idx, calib_idx in cv.split(X_, y_, groups=groups_):
            X_train_fold = X_.iloc[train_idx] if hasattr(X_, "iloc") else X_[train_idx]
            X_calib_fold = X_.iloc[calib_idx] if hasattr(X_, "iloc") else X_[calib_idx]
            y_train_fold, y_calib_fold = y_[train_idx], y_[calib_idx]

            fold_model = clone(self.base_model)
            fold_model.fit(X_train_fold, y_train_fold)

            raw_probs = fold_model.predict_proba(X_calib_fold)[:, 1]
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(raw_probs, y_calib_fold)

            self.fold_pairs_.append((fold_model, calibrator))

        self.classes_ = np.unique(y_)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if not getattr(self, "fold_pairs_", None):
            raise RuntimeError("fit() must be called before predict_proba().")
        fold_probs = []
        for fold_model, calibrator in self.fold_pairs_:
            raw = fold_model.predict_proba(X)[:, 1]
            fold_probs.append(calibrator.predict(raw))
        mean_pos_prob = np.mean(fold_probs, axis=0)
        return np.column_stack([1.0 - mean_pos_prob, mean_pos_prob])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


class Stage1Gate:
    """Calibrated binary anomaly gate.

    Operating threshold is FROZEN from Audit Run 4's ROC/FAR contour sweep
    (see PROJECT_SYSTEM_ARCHITECTURE_REPORT.md, Point E). Not recomputed here.
    """

    FROZEN_OPERATING_THRESHOLD_AUDIT_RUN_4: float = 0.5810  

    def __init__(self, base_model: ClassifierMixin) -> None:
        self.base_model = base_model
        self.operating_threshold: float = self.FROZEN_OPERATING_THRESHOLD_AUDIT_RUN_4
        self.calibrated_model = GroupedCalibratedClassifier(base_model, n_splits=3)

    def fit(self, X: pd.DataFrame, y: np.ndarray, groups: pd.Series) -> "Stage1Gate":
        self.calibrated_model.fit(X, y, groups=groups)
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.calibrated_model.predict_proba(X)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        probs = self.predict_proba(X)[:, 1]
        return (probs >= self.operating_threshold).astype(int)