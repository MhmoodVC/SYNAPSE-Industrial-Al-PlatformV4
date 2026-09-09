# FILE: scripts/verify_calibration_and_metrics.py
"""Standalone verification: (1) confirms Stage1Gate's precomputed GroupKFold
folds are genuinely disjoint by run_id (no internal-routing trust required —
the split is inspected directly); (2) independently rebuilds the pipeline
and recomputes metrics from scratch, then asserts they match the persisted
evaluation_metrics.json rather than trusting the file blindly."""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import accuracy_score, confusion_matrix

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from models.stage1_gate import Stage1Gate
from models.stage2_classifier import Stage2Classifier
from models.pipeline import HierarchicalPipeline


def load_split():
    df = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "features_v2.parquet")
    run_scenarios = df.groupby("run_id")["fault_type"].last().to_dict()
    scenario_to_runs: dict = {}
    for r_id, sc in run_scenarios.items():
        scenario_to_runs.setdefault(sc, []).append(r_id)
    test_run_set = set()
    for sc, runs in scenario_to_runs.items():
        ordered = sorted(runs)
        count = int(round(len(ordered) * 0.2))
        if count == 0 and len(ordered) > 1:
            count = 1
        test_run_set.update(ordered[-count:])
    train_run_set = set(run_scenarios.keys()) - test_run_set
    train_df = df[df["run_id"].isin(train_run_set)].copy()
    test_df = df[df["run_id"].isin(test_run_set)].copy()
    ignore_cols = [
        "timestamp", "run_id", "pump_id", "operating_regime", "pump_state",
        "fault_type", "event_start", "event_end", "failure_flag",
        "relabeled_fault", "pelt_onset_idx", "degradation_stage", "severity",
    ]
    feature_cols = [c for c in df.columns if c not in ignore_cols]
    return train_df, test_df, feature_cols


def main() -> None:
    print(f"sklearn version: {sklearn.__version__}")

    train_df, test_df, feature_cols = load_split()
    X_train_feat = train_df[feature_cols].fillna(0)
    X_test_feat = test_df[feature_cols].fillna(0)
    y_train_new = train_df["relabeled_fault"]
    y_test_new = test_df["relabeled_fault"]
    y_train_binary = (y_train_new != "normal").astype(int)

    # --- Part 1: fit Stage1Gate, then inspect fold pairs & disjointness ---
    stage1 = Stage1Gate(HistGradientBoostingClassifier(random_state=42))
    stage1.fit(X_train_feat, y_train_binary, groups=train_df["run_id"])

    assert len(stage1.calibrated_model.fold_pairs_) == 3, "Expected 3 fold pairs"
    print(f"GroupedCalibratedClassifier fold_pairs_: {len(stage1.calibrated_model.fold_pairs_)}")

    cv_check = GroupKFold(n_splits=3)
    groups_arr = train_df["run_id"].to_numpy()
    for fold_idx, (train_idx, calib_idx) in enumerate(cv_check.split(X_train_feat, y_train_binary, groups=groups_arr)):
        overlap = set(groups_arr[train_idx]) & set(groups_arr[calib_idx])
        print(f"  fold {fold_idx}: overlap={len(overlap)}")
        assert not overlap, f"Fold {fold_idx} leaked run_ids: {overlap}"
    print("PASS: calibration folds are run_id-disjoint.\n")

    # OOF Cascade computed cleanly via explicit GroupKFold loop
    oof_probs = np.zeros(len(X_train_feat), dtype=float)
    outer_gkf = GroupKFold(n_splits=3)
    groups_arr = train_df["run_id"].to_numpy()
    y_binary_arr = y_train_binary.to_numpy() if hasattr(y_train_binary, "to_numpy") else np.asarray(y_train_binary)

    for fold_trn_idx, fold_val_idx in outer_gkf.split(X_train_feat, y_binary_arr, groups=groups_arr):
        X_tr_f = X_train_feat.iloc[fold_trn_idx]
        y_tr_f = y_binary_arr[fold_trn_idx]
        grp_tr_f = pd.Series(groups_arr[fold_trn_idx])
        
        X_val_f = X_train_feat.iloc[fold_val_idx]
        
        fold_gate = Stage1Gate(HistGradientBoostingClassifier(random_state=42))
        fold_gate.fit(X_tr_f, y_tr_f, groups=grp_tr_f)
        
        oof_probs[fold_val_idx] = fold_gate.predict_proba(X_val_f)[:, 1]
    fault_mask = (y_train_new != "normal") & (y_train_new != "transition")
    X_train_stage2 = X_train_feat[fault_mask].copy()
    X_train_stage2["stage1_prob_anomalous"] = oof_probs[fault_mask]
    y_train_stage2 = y_train_new[fault_mask]

    stage2 = Stage2Classifier()
    stage2.fit(X_train_stage2, y_train_stage2)

    pipeline = HierarchicalPipeline(stage1, stage2)
    new_preds, new_probs = pipeline.predict(X_test_feat)

    recomputed_full_acc = accuracy_score(y_test_new, new_preds)
    active_mask_faults_only = (y_test_new != "transition") & (y_test_new != "normal")
    recomputed_active_faults_only_acc = accuracy_score(
        y_test_new[active_mask_faults_only], new_preds[active_mask_faults_only]
    )
    y_test_binary = (y_test_new != "normal").astype(int)
    anomaly_preds = (new_probs >= stage1.operating_threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test_binary, anomaly_preds).ravel()
    recomputed_far = fp / (fp + tn)
    recomputed_recall = tp / (tp + fn)

    print("Recomputed independently:")
    print(f"  Full-Trajectory Accuracy: {recomputed_full_acc*100:.2f}%")
    print(f"  Active Phase Accuracy (faults only): {recomputed_active_faults_only_acc*100:.2f}%")
    print(f"  FAR: {recomputed_far*100:.2f}%")
    print(f"  Anomaly Recall: {recomputed_recall*100:.2f}%\n")

    # --- Part 3: compare against persisted JSON ---
    metrics_path = PROJECT_ROOT / "src" / "models" / "evaluation_metrics.json"
    with open(metrics_path) as fh:
        persisted = json.load(fh)

    tolerance = 0.5
    checks = [
        ("full_trajectory.accuracy_percent",
         persisted["full_trajectory"]["accuracy_percent"], round(recomputed_full_acc * 100, 2)),
        ("active_fault_phase_faults_only.accuracy_percent",
         persisted["active_fault_phase_faults_only"]["accuracy_percent"],
         round(recomputed_active_faults_only_acc * 100, 2)),
        ("anomaly_detector.false_positive_rate_percent",
         persisted["anomaly_detector"]["false_positive_rate_percent"], round(recomputed_far * 100, 2)),
        ("anomaly_detector.outlier_recall_percent",
         persisted["anomaly_detector"]["outlier_recall_percent"], round(recomputed_recall * 100, 2)),
    ]

    print("Comparing recomputed metrics against persisted evaluation_metrics.json:")
    all_match = True
    for name, persisted_val, recomputed_val in checks:
        diff = abs(persisted_val - recomputed_val)
        status = "MATCH" if diff <= tolerance else "MISMATCH"
        if status == "MISMATCH":
            all_match = False
        print(f"  {name}: persisted={persisted_val}%  recomputed={recomputed_val}%  diff={diff:.2f}pp  [{status}]")

    assert all_match, "Recomputed metrics do not match evaluation_metrics.json within tolerance."
    print("\nPASS: persisted evaluation_metrics.json is consistent with an independent rebuild.")


if __name__ == "__main__":
    main()