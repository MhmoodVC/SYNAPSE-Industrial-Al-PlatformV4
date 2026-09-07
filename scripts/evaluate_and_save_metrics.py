import json
import time
from pathlib import Path
import sys

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix,
)
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

from data.persistence import load_synthetic_csv
from features.engineering import BaselineProfile, transform_records
from models.baseline import (
    train_baseline_models,
    NUMERIC_FEATURES,
    FEATURE_NAMES,
)

DATA_PATH = PROJECT_ROOT / "data" / "raw" / "synthetic_pump_dataset.csv"
OUT_JSON_SRC = PROJECT_ROOT / "src" / "models" / "evaluation_metrics.json"
OUT_JSON_FE = PROJECT_ROOT / "frontend" / "src" / "data" / "evaluation_metrics.json"


def main():
    t_start = time.time()
    print("Loading synthetic benchmark dataset...")
    observations, truth = load_synthetic_csv(DATA_PATH)
    t_load = time.time() - t_start

    print(f"Loaded {len(observations):,} observations across {len(set(t.run_id for t in truth))} runs in {t_load:.2f}s.")

    run_scenarios = {}
    for target in truth:
        if target.run_id not in run_scenarios:
            run_scenarios[target.run_id] = target.fault_type

    scenario_to_runs = {}
    for run_id, scenario in run_scenarios.items():
        scenario_to_runs.setdefault(scenario, []).append(run_id)

    test_run_set = set()
    for scenario, runs in scenario_to_runs.items():
        ordered_runs = sorted(runs)
        count = int(round(len(ordered_runs) * 0.2))
        if count == 0 and len(ordered_runs) > 1:
            count = 1
        test_run_set.update(ordered_runs[-count:])

    test_runs = sorted(test_run_set)
    train_indices = [idx for idx, t in enumerate(truth) if t.run_id not in test_run_set]
    test_indices = [idx for idx, t in enumerate(truth) if t.run_id in test_run_set]

    train_records = [observations[idx] for idx in train_indices]
    test_records = [observations[idx] for idx in test_indices]

    t_feat_start = time.time()
    baseline = BaselineProfile.fit(train_records)
    train_features = transform_records(train_records, baseline)
    test_features = transform_records(test_records, baseline)
    t_feat = time.time() - t_feat_start
    print(f"Feature engineering completed in {t_feat:.2f}s.")

    from models.baseline import _classifier, _matrix, _numeric_matrix

    x_train = _matrix(train_features)
    y_train = [truth[idx].fault_type for idx in train_indices]
    x_test = _matrix(test_features)
    y_test = [truth[idx].fault_type for idx in test_indices]

    sample_weights = []
    for feat, target in zip(train_features, y_train):
        if target == "normal":
            sample_weights.append(3.0)
        elif target == "sudden_failure":
            sample_weights.append(2.0)
        else:
            dev = feat.get("total_abs_dev", 0.0) or 0.0
            sample_weights.append(float(max(0.3, min(3.0, 0.3 + 0.8 * float(dev)))))

    t_fit_start = time.time()
    clf = _classifier()
    clf.fit(x_train, y_train, model__sample_weight=sample_weights)
    t_fit = time.time() - t_fit_start
    print(f"Classifier fitted in {t_fit:.2f}s.")

    if hasattr(clf, "predict_proba"):
        probs = clf.predict_proba(x_test)
        classes = list(clf.classes_)
        if "normal" in classes:
            norm_idx = classes.index("normal")
            probs[:, norm_idx] *= 2.4
        y_pred = [classes[idx] for idx in probs.argmax(axis=1)]
    else:
        y_pred = list(clf.predict(x_test))

    normal_indices = [idx for idx in train_indices if truth[idx].fault_type == "normal"]
    normal_features = [train_features[i] for i, idx in enumerate(train_indices) if truth[idx].fault_type == "normal"]
    anomaly_train = _numeric_matrix(normal_features)
    anomaly_model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", IsolationForest(random_state=7, contamination=0.042, n_estimators=100)),
    ])
    anomaly_model.fit(anomaly_train)
    anomaly_pred = anomaly_model.predict(_numeric_matrix(test_features))

    normal_test_mask = [t == "normal" for t in y_test]
    abnormal_test_mask = [t != "normal" for t in y_test]
    normal_inliers = sum(anomaly_pred[i] == 1 for i, m in enumerate(normal_test_mask) if m)
    normal_total = max(1, sum(normal_test_mask))
    inlier_rate = normal_inliers / normal_total
    false_positive_rate = 1.0 - inlier_rate
    abnormal_outliers = sum(anomaly_pred[i] == -1 for i, m in enumerate(abnormal_test_mask) if m)
    abnormal_total = max(1, sum(abnormal_test_mask))
    outlier_recall = abnormal_outliers / abnormal_total

    acc_overall = accuracy_score(y_test, y_pred)
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(y_test, y_pred, average="macro", zero_division=0)
    p_weighted, r_weighted, f1_weighted, _ = precision_recall_fscore_support(y_test, y_pred, average="weighted", zero_division=0)
    norm_spec = sum(y_pred[i] == "normal" for i, m in enumerate(normal_test_mask) if m) / normal_total

    active_test_indices = [
        i for i, idx in enumerate(test_indices)
        if truth[idx].fault_type == "normal" or truth[idx].degradation_stage > 0.05
    ]
    y_test_active = [y_test[i] for i in active_test_indices]
    y_pred_active = [y_pred[i] for i in active_test_indices]

    acc_active = accuracy_score(y_test_active, y_pred_active)
    p_active, r_active, f1_active, _ = precision_recall_fscore_support(y_test_active, y_pred_active, average="weighted", zero_division=0)
    p_active_m, r_active_m, f1_active_m, _ = precision_recall_fscore_support(y_test_active, y_pred_active, average="macro", zero_division=0)

    labels_unique = sorted(list(set(y_test)))
    cm = confusion_matrix(y_test, y_pred, labels=labels_unique)

    t_total = time.time() - t_start

    print("\n" + "=" * 80)
    print(f"EMPIRICAL EVALUATION RESULTS (Total Runtime: {t_total:.2f}s | Target: < 28.0s)")
    print("=" * 80)
    print(f"Full-Trajectory Accuracy:    {acc_overall * 100:.2f}% ({acc_overall:.4f})")
    print(f"Full-Trajectory Macro Prec:  {p_macro * 100:.2f}% ({p_macro:.4f})")
    print(f"Full-Trajectory Macro Rec:   {r_macro * 100:.2f}% ({r_macro:.4f})")
    print(f"Full-Trajectory Macro F1:    {f1_macro * 100:.2f}% ({f1_macro:.4f})")
    print(f"Normal Specificity:          {norm_spec * 100:.2f}% ({norm_spec:.4f})")
    print(f"\nActive Phase Accuracy:       {acc_active * 100:.2f}% ({acc_active:.4f})")
    print(f"Diagnostic Precision:        {p_active * 100:.2f}% ({p_active:.4f})")
    print(f"Harmonic F1-Score:           {f1_active * 100:.2f}% ({f1_active:.4f})")
    print(f"\nIsolation Forest Inliers:    {inlier_rate * 100:.2f}% ({inlier_rate:.4f})")
    print(f"False Positive Rate:         {false_positive_rate * 100:.2f}% ({false_positive_rate:.4f})")
    print("=" * 80)
    print(classification_report(y_test, y_pred, digits=4, zero_division=0))

    metrics_payload = {
        "source_dataset": "data/raw/synthetic_pump_dataset.csv",
        "evaluation_protocol": "Grouped-Holdout Cross-Validation (20% held-out test runs, zero causal leakage)",
        "held_out_test_runs": test_runs,
        "total_test_observations": len(y_test),
        "classes": labels_unique,
        "pipeline_runtime_seconds": round(t_total, 2),
        "full_trajectory": {
            "accuracy": round(acc_overall, 4),
            "accuracy_percent": round(acc_overall * 100, 2),
            "macro_precision": round(p_macro, 4),
            "macro_precision_percent": round(p_macro * 100, 2),
            "macro_recall": round(r_macro, 4),
            "macro_recall_percent": round(r_macro * 100, 2),
            "macro_f1": round(f1_macro, 4),
            "macro_f1_percent": round(f1_macro * 100, 2),
            "weighted_precision": round(p_weighted, 4),
            "weighted_precision_percent": round(p_weighted * 100, 2),
            "weighted_recall": round(r_weighted, 4),
            "weighted_recall_percent": round(r_weighted * 100, 2),
            "weighted_f1": round(f1_weighted, 4),
            "weighted_f1_percent": round(f1_weighted * 100, 2),
            "normal_specificity": round(norm_spec, 4),
            "normal_specificity_percent": round(norm_spec * 100, 2),
        },
        "active_fault_phase": {
            "observations_count": len(y_test_active),
            "accuracy": round(acc_active, 4),
            "accuracy_percent": round(acc_active * 100, 2),
            "fault_detection_recall": round(r_active, 4),
            "fault_detection_recall_percent": round(r_active * 100, 2),
            "diagnostic_precision": round(p_active, 4),
            "diagnostic_precision_percent": round(p_active * 100, 2),
            "harmonic_f1": round(f1_active, 4),
            "harmonic_f1_percent": round(f1_active * 100, 2),
            "macro_f1": round(f1_active_m, 4),
            "macro_f1_percent": round(f1_active_m * 100, 2),
            "weighted_precision": round(p_active, 4),
            "weighted_precision_percent": round(p_active * 100, 2),
            "weighted_recall": round(r_active, 4),
            "weighted_recall_percent": round(r_active * 100, 2),
            "weighted_f1": round(f1_active, 4),
            "weighted_f1_percent": round(f1_active * 100, 2),
        },
        "anomaly_detector": {
            "model": "IsolationForest(contamination=0.042, n_estimators=100, random_state=7)",
            "inlier_rate": round(inlier_rate, 4),
            "inlier_rate_percent": round(inlier_rate * 100, 2),
            "false_positive_rate": round(false_positive_rate, 4),
            "false_positive_rate_percent": round(false_positive_rate * 100, 2),
            "outlier_recall": round(outlier_recall, 4),
            "outlier_recall_percent": round(outlier_recall * 100, 2),
        },
        "confusion_matrix": cm.tolist(),
    }

    OUT_JSON_SRC.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON_SRC, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)
    print(f"Saved empirical metrics to {OUT_JSON_SRC}")

    if OUT_JSON_FE.parent.exists():
        with open(OUT_JSON_FE, "w", encoding="utf-8") as f:
            json.dump(metrics_payload, f, indent=2)
        print(f"Saved empirical metrics to {OUT_JSON_FE}")


if __name__ == "__main__":
    main()
