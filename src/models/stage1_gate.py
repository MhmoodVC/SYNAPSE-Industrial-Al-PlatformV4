import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_curve

class Stage1Gate:
    def __init__(self, target_far=0.042):
        self.base_model = HistGradientBoostingClassifier(random_state=42)
        self.calibrated_model = CalibratedClassifierCV(self.base_model, method="isotonic", cv=3)
        # Final approved production threshold
        self.operating_threshold = 0.2965
        self.target_far = target_far
        
    def fit(self, X_train, y_train_binary):
        self.calibrated_model.fit(X_train, y_train_binary)
        # We bypass dynamic calibration for production and use the locked threshold
        self.operating_threshold = 0.2965
        return self
        
    def predict_proba(self, X):
        return self.calibrated_model.predict_proba(X)
        
    def predict(self, X):
        probs = self.predict_proba(X)[:, 1]
        return (probs >= self.operating_threshold).astype(int)
