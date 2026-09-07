import numpy as np
import pandas as pd
from features.changepoint import detect_onset

def test_detect_onset_returns_first_changepoint():
    col1 = np.concatenate([np.random.normal(0, 0.1, 50), 
                           np.random.normal(2, 0.1, 50),
                           np.random.normal(4, 0.1, 50)])
    df = pd.DataFrame({'sensor1': col1})
    
    onset = detect_onset(df, ['sensor1'], method='pelt')
    
    assert 40 <= onset <= 60, f"Expected onset around 50, got {onset}"
