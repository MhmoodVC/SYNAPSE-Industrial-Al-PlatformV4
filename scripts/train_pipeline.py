import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.model_selection import cross_val_predict, StratifiedKFold, GroupKFold
from sklearn.metrics import accuracy_score, confusion_matrix

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from models.stage1_gate import Stage1Gate
from models.stage2_classifier import Stage2Classifier
from models.pipeline import HierarchicalPipeline

DATA_PATH = PROJECT_ROOT / "data" / "processed" / "features_v2.parquet"

def main():
    print("[TRAINING PIPELINE - OOF CASCADED - IDENTICAL PROTOCOL]")
    print("Loading features...")
    df = pd.read_parquet(DATA_PATH)
    
    run_scenarios = df.groupby('run_id')['fault_type'].last().to_dict()
    scenario_to_runs = {}
    for r_id, sc in run_scenarios.items():
        scenario_to_runs.setdefault(sc, []).append(r_id)
        
    test_run_set = set()
    for sc, runs in scenario_to_runs.items():
        ordered = sorted(runs)
        count = int(round(len(ordered) * 0.2))
        if count == 0 and len(ordered) > 1: count = 1
        test_run_set.update(ordered[-count:])
        
    train_run_set = set(run_scenarios.keys()) - test_run_set
    
    train_df = df[df['run_id'].isin(train_run_set)].copy()
    test_df = df[df['run_id'].isin(test_run_set)].copy()
    
    ignore_cols = ['timestamp', 'run_id', 'pump_id', 'operating_regime', 'pump_state', 
                   'fault_type', 'event_start', 'event_end', 'failure_flag', 
                   'relabeled_fault', 'pelt_onset_idx', 'degradation_stage', 'severity']
    
    feature_cols = [c for c in df.columns if c not in ignore_cols]
    
    X_train = train_df[feature_cols].fillna(0)
    y_train_raw = train_df['relabeled_fault']
    X_test = test_df[feature_cols].fillna(0)
    y_test_raw = test_df['relabeled_fault']
    
    print(f"Train runs: {len(train_run_set)} | Test runs: {len(test_run_set)}")
    
    y_train_binary = (y_train_raw != 'normal').astype(int)
    
    print("Training Stage 1 Gate...")
    stage1 = Stage1Gate(target_far=0.042)
    stage1.fit(X_train, y_train_binary)
    print(f"Stage 1 operating threshold fixed to: {stage1.operating_threshold:.4f}")
    
    print("Generating OOF probabilities for Stage 2 (No Leakage)...")
    assert len(train_df['run_id']) == len(X_train), "Group length mismatch with X_train"
    assert train_df.index.equals(X_train.index), "Index misalignment between train_df and X_train"
    probs_train = cross_val_predict(stage1.calibrated_model, X_train, y_train_binary, cv=GroupKFold(n_splits=3), groups=train_df['run_id'], method='predict_proba', n_jobs=-1)[:, 1]
    
    print("Training Stage 2 Classifier...")
    fault_mask = (y_train_raw != 'normal') & (y_train_raw != 'transition')
    X_train_stage2 = X_train[fault_mask].copy()
    X_train_stage2['stage1_prob_anomalous'] = probs_train[fault_mask]
    y_train_stage2 = y_train_raw[fault_mask]
    
    stage2 = Stage2Classifier()
    stage2.fit(X_train_stage2, y_train_stage2)
    
    print("Assembling Hierarchical Pipeline...")
    pipeline = HierarchicalPipeline(stage1, stage2)
    
    print("Evaluating on Test Set...")
    y_pred, y_probs = pipeline.predict(X_test)
    
    normal_mask_test = (y_test_raw == 'normal')
    num_normal = normal_mask_test.sum()
    false_alarms = (y_pred[normal_mask_test] != 'normal').sum()
    far = false_alarms / num_normal
    
    active_mask = (y_test_raw != 'transition')
    active_acc = accuracy_score(y_test_raw[active_mask], y_pred[active_mask])
    
    full_acc = accuracy_score(y_test_raw, y_pred)
    
    y_test_binary = (y_test_raw != 'normal').astype(int)
    anomaly_preds = (y_probs >= stage1.operating_threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test_binary, anomaly_preds).ravel()
    outlier_recall = tp / (tp + fn)
    
    print(f"\n=== Hierarchical Inference Results ===")
    print(f"Test Full-Trajectory Accuracy: {full_acc*100:.2f}%")
    print(f"Test Active Phase Accuracy: {active_acc*100:.2f}%")
    print(f"Test Empirical FAR: {far*100:.2f}%")
    print(f"Test Anomaly Recall: {outlier_recall*100:.2f}%")

if __name__ == '__main__':
    main()

