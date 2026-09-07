import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, VotingClassifier

class Stage2Classifier:
    def __init__(self):
        clf1 = ExtraTreesClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        clf2 = HistGradientBoostingClassifier(random_state=42)
        self.ensemble = VotingClassifier(estimators=[('et', clf1), ('hgb', clf2)], voting='soft')
        
    def fit(self, X_train, y_train):
        self.ensemble.fit(X_train, y_train)
        return self
        
    def predict(self, X):
        return self.ensemble.predict(X)
