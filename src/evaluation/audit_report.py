# FILE: src/evaluation/audit_report.py
import sys
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from sklearn.model_selection import cross_val_predict, GroupKFold

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from models.stage1_gate import Stage1Gate
from models.stage2_classifier import Stage2Classifier
from models.pipeline import HierarchicalPipeline


def _active_block(y_test_new: pd.Series, new_preds: np.ndarray, mask: pd.Series) -> dict:
    y_a = y_test_new[mask]
    p_a = new_preds[mask]
    acc = accuracy_score(y_a, p_a)
    mp, mr, mf, _ = precision_recall_fscore_support(y_a, p_a, average="macro", zero_division=0)
    wp_, wr_, wf_, _ = precision_recall_fscore_support(y_a, p_a, average="weighted", zero_division=0)
    return {
        "observations_count": int(mask.sum()),
        "accuracy": acc,
        "accuracy_percent": round(acc * 100, 2),
        "macro_precision": mp,
        "macro_precision_percent": round(mp * 100, 2),
        "macro_recall": mr,
        "macro_recall_percent": round(mr * 100, 2),
        "macro_f1": mf,
        "macro_f1_percent": round(mf * 100, 2),
        "weighted_precision": wp_,
        "weighted_precision_percent": round(wp_ * 100, 2),
        "weighted_recall": wr_,
        "weighted_recall_percent": round(wr_ * 100, 2),
        "weighted_f1": wf_,
        "weighted_f1_percent": round(wf_ * 100, 2),
    }


def main() -> None:
    DATA_PATH = PROJECT_ROOT / "data" / "processed" / "features_v2.parquet"
    df = pd.read_parquet(DATA_PATH)

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

    X_train_feat = train_df[feature_cols].fillna(0)
    X_test_feat = test_df[feature_cols].fillna(0)

    y_train_new = train_df["relabeled_fault"]
    y_test_new = test_df["relabeled_fault"]

    # --- Stage 1: grouped calibration ---
    y_train_binary = (y_train_new != "normal").astype(int)
    base_model = HistGradientBoostingClassifier(random_state=42)
    stage1 = Stage1Gate(base_model)
    stage1.fit(X_train_feat, y_train_binary, groups=train_df["run_id"])

    assert len(train_df["run_id"]) == len(X_train_feat), "Group length mismatch with X_train_feat"
    assert train_df.index.equals(X_train_feat.index), "Index misalignment between train_df and X_train_feat"

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
    # --- OOF EVALUATION AT TAU = 0.5810 ---
    from sklearn.metrics import confusion_matrix
    oof_preds = (oof_probs >= 0.5810).astype(int)
    tn_oof, fp_oof, fn_oof, tp_oof = confusion_matrix(y_binary_arr, oof_preds).ravel()
    print("\n" + "="*45)
    print(f"OOF False Alarm Rate (FAR): {fp_oof / (fp_oof + tn_oof):.5f}")
    print(f"OOF Anomaly Recall:         {tp_oof / (tp_oof + fn_oof):.5f}")
    print("="*45 + "\n")
    
    fault_mask = (y_train_new != "normal") & (y_train_new != "transition")
    X_train_stage2 = X_train_feat[fault_mask].copy()
    X_train_stage2["stage1_prob_anomalous"] = oof_probs[fault_mask]
    y_train_stage2 = y_train_new[fault_mask]

    stage2 = Stage2Classifier()
    stage2.fit(X_train_stage2, y_train_stage2)

    pipeline = HierarchicalPipeline(stage1, stage2)
    new_preds, new_probs = pipeline.predict(X_test_feat)

    # --- Full-trajectory metrics ---
    acc_penalizing = accuracy_score(y_test_new, new_preds)
    p, r, f, _ = precision_recall_fscore_support(y_test_new, new_preds, average="macro", zero_division=0)
    wp, wr, wf, _ = precision_recall_fscore_support(y_test_new, new_preds, average="weighted", zero_division=0)

    normal_mask = y_test_new == "normal"
    normal_spec = (new_preds[normal_mask] == "normal").sum() / normal_mask.sum()
    far = (new_preds[normal_mask] != "normal").sum() / normal_mask.sum()

    # --- Active phase: BOTH scopes, explicitly labeled, no silent choice ---
    active_mask_incl_normal = y_test_new != "transition"
    active_mask_faults_only = (y_test_new != "transition") & (y_test_new != "normal")

    active_incl_normal = _active_block(y_test_new, new_preds, active_mask_incl_normal)
    active_faults_only = _active_block(y_test_new, new_preds, active_mask_faults_only)

    # --- Anomaly gate metrics ---
    y_test_binary = (y_test_new != "normal").astype(int)
    anomaly_preds = (new_probs >= stage1.operating_threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test_binary, anomaly_preds).ravel()
    outlier_recall = tp / (tp + fn)

    labels = sorted(y_test_new.unique().tolist())
    cm = confusion_matrix(y_test_new, new_preds, labels=labels)
    cm_normalized = cm.astype("float") / cm.sum(axis=1)[:, np.newaxis]
    cm_norm_list = np.nan_to_num(cm_normalized).tolist()

    active_incl_normal["SCOPE_NOTE"] = "Includes 'normal' frames (excludes only 'transition')."
    active_faults_only["SCOPE_NOTE"] = "Excludes 'normal' AND 'transition' frames — degrading frames only."

    out_dict = {
        "source_dataset": "data/raw/synthetic_pump_dataset.csv",
        "evaluation_protocol": "Two-Stage Hierarchical (OOF, Per-Fault Transition Buffers, GroupKFold Calibration)",
        "sklearn_calibration_cv": "GroupKFold(n_splits=3), groups=run_id",
        "held_out_test_runs": sorted(test_run_set),
        "total_test_observations": len(y_test_new),
        "classes": labels,
        "full_trajectory": {
            "accuracy": acc_penalizing,
            "accuracy_percent": round(acc_penalizing * 100, 2),
            "macro_precision_percent": round(p * 100, 2),
            "macro_recall_percent": round(r * 100, 2),
            "macro_f1_percent": round(f * 100, 2),
            "weighted_precision_percent": round(wp * 100, 2),
            "weighted_recall_percent": round(wr * 100, 2),
            "weighted_f1_percent": round(wf * 100, 2),
            "normal_specificity": normal_spec,
            "normal_specificity_percent": round(normal_spec * 100, 2),
        },
        "active_fault_phase_incl_normal": active_incl_normal,
        "active_fault_phase_faults_only": active_faults_only,
        "anomaly_detector": {
            "model": "HierarchicalPipeline(HistGradientBoosting+ExtraTrees)",
            "operating_threshold": stage1.operating_threshold,
            "false_positive_rate": far,
            "false_positive_rate_percent": round(far * 100, 2),
            "outlier_recall": outlier_recall,
            "outlier_recall_percent": round(outlier_recall * 100, 2),
        },
        "confusion_matrix": cm_norm_list,
        "confusion_matrix_labels": labels,
    }

    dest1 = PROJECT_ROOT / "src" / "models" / "evaluation_metrics.json"
    dest2 = PROJECT_ROOT / "frontend" / "src" / "data" / "evaluation_metrics.json"

    with open(dest1, "w") as fh:
        json.dump(out_dict, fh, indent=2)
    shutil.copy(dest1, dest2)

    print("[AUDIT REPORT - GROUPED CALIBRATION + DUAL ACTIVE-PHASE SCOPE]")
    print(f"Full-Trajectory Accuracy: {acc_penalizing*100:.2f}%")
    print(f"Active Phase Accuracy (incl. normal): {active_incl_normal['accuracy_percent']}%")
    print(f"Active Phase Accuracy (faults only):  {active_faults_only['accuracy_percent']}%")
    print(f"Empirical Test FAR: {far*100:.2f}%")
    print(f"Anomaly Recall: {outlier_recall*100:.2f}%")
    print("Exported metrics to", dest1, "and", dest2)

    # Export frozen model for live inference
    import joblib
    export_dir = PROJECT_ROOT / "models" / "exported"
    export_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipeline,
            "feature_cols": feature_cols,
            "threshold": stage1.operating_threshold,
        },
        export_dir / "pipeline_live.joblib",
    )
    print(f"✅ Frozen model exported to {export_dir / 'pipeline_live.joblib'}")


if __name__ == "__main__":
    main()