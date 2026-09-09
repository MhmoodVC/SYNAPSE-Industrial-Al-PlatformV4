# FILE: src/models/stage2_classifier.py
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, VotingClassifier


class Stage2Classifier:
    """Multi-class fault diagnostic ensemble. Trained only on active-fault
    frames (excludes 'normal' and 'transition' — see audit_report.py's
    fault_mask construction)."""

    def __init__(self) -> None:
        clf1 = ExtraTreesClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        clf2 = HistGradientBoostingClassifier(random_state=42)
        self.ensemble = VotingClassifier(
            estimators=[("et", clf1), ("hgb", clf2)],
            voting="soft",
        )

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "Stage2Classifier":
        self.ensemble.fit(X_train, y_train)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.ensemble.predict(X)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.ensemble.predict_proba(X)