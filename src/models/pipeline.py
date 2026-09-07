import numpy as np
from models.stage1_gate import Stage1Gate
from models.stage2_classifier import Stage2Classifier

class HierarchicalPipeline:
    def __init__(self, stage1: Stage1Gate, stage2: Stage2Classifier):
        self.stage1 = stage1
        self.stage2 = stage2
        self.operating_threshold = 0.2965  # Production threshold
        
    def predict(self, X_features):
        prob_anomalous = self.stage1.predict_proba(X_features)[:, 1]
        is_normal = prob_anomalous < self.operating_threshold
        
        predictions = np.empty(len(X_features), dtype=object)
        predictions[is_normal] = "normal"
        
        if np.any(~is_normal):
            X_anomalous = X_features[~is_normal].copy()
            X_anomalous['stage1_prob_anomalous'] = prob_anomalous[~is_normal]
            predictions[~is_normal] = self.stage2.predict(X_anomalous)
            
        return predictions, prob_anomalous
