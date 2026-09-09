# FILE: scripts/find_new_threshold.py
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold

PROJECT_ROOT = Path(r"C:\Users\user\Desktop\workExxson\ExFinal")
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from models.stage1_gate import Stage1Gate

df = pd.read_parquet(PROJECT_ROOT / "data" / "processed" / "features_v2.parquet")

run_scenarios = df.groupby("run_id")["fault_type"].last().to_dict()
scenario_to_runs = {}
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

ignore_cols = [
    "timestamp", "run_id", "pump_id", "operating_regime", "pump_state",
    "fault_type", "event_start", "event_end", "failure_flag",
    "relabeled_fault", "pelt_onset_idx", "degradation_stage", "severity",
]
feature_cols = [c for c in df.columns if c not in ignore_cols]

X_train_feat = train_df[feature_cols].fillna(0)
y_train_new = train_df["relabeled_fault"]
y_train_binary = (y_train_new != "normal").astype(int)

# ✅ من جيميناي: Cache للـ OOF
cached_oof_path = PROJECT_ROOT / "oof_probs_cache.npy"

if cached_oof_path.exists():
    print(f"✅ Loading cached OOF probabilities from {cached_oof_path.name}...")
    oof_probs = np.load(cached_oof_path)
    print(f"   Loaded {len(oof_probs)} samples.")
else:
    print("Generating OOF probabilities from training data (3-fold GroupKFold)...")
    oof_probs = np.zeros(len(X_train_feat), dtype=float)
    outer_gkf = GroupKFold(n_splits=3)
    groups_arr = train_df["run_id"].to_numpy()
    y_binary_arr = y_train_binary.to_numpy()

    for fold_idx, (fold_trn_idx, fold_val_idx) in enumerate(outer_gkf.split(X_train_feat, y_binary_arr, groups=groups_arr)):
        print(f"  Fold {fold_idx + 1}/3...")
        X_tr_f = X_train_feat.iloc[fold_trn_idx]
        y_tr_f = y_binary_arr[fold_trn_idx]
        grp_tr_f = pd.Series(groups_arr[fold_trn_idx])
        X_val_f = X_train_feat.iloc[fold_val_idx]

        fold_gate = Stage1Gate(HistGradientBoostingClassifier(random_state=42))
        fold_gate.fit(X_tr_f, y_tr_f, groups=grp_tr_f)
        oof_probs[fold_val_idx] = fold_gate.predict_proba(X_val_f)[:, 1]

    np.save(cached_oof_path, oof_probs)
    print(f"✅ Saved OOF probabilities to {cached_oof_path.name}.")

y_binary_arr = y_train_binary.to_numpy()
normal_mask = (y_binary_arr == 0)
anomaly_mask = (y_binary_arr == 1)

# ✅ من جيميناي: حساب الـ Percentile الدقيق
exact_th = float(np.percentile(oof_probs[normal_mask], (1.0 - 0.0420) * 100))
print(f"\n📊 Exact 95.80th percentile on normal frames: {exact_th:.4f}")
print(f"   (Theoretical threshold for FAR = 4.20% if perfectly calibrated)")

# ✅ من حلّي: نطاق أوسع + diagnostics
print(f"\n🔍 Sweeping threshold candidates (0.25 to 0.85, 601 steps) on OOF predictions...")
candidates = []
for th in np.linspace(0.25, 0.85, 601):
    preds = (oof_probs >= th).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_binary_arr, preds).ravel()
    far = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    candidates.append((th, far, recall))

# Filter: FAR <= 0.0420
valid = [c for c in candidates if c[1] <= 0.0420]

if valid:
    best = sorted(valid, key=lambda x: (-x[2], x[1], x[0]))[0]
    print(f"\n{'='*60}")
    print(f"✅ OPTIMAL THRESHOLD (from OOF training data):")
    print(f"  Threshold: {best[0]:.4f}")
    print(f"  OOF FAR: {best[1]*100:.2f}% (constraint: ≤ 4.20%)")
    print(f"  OOF Anomaly Recall: {best[2]*100:.2f}%")
    print(f"{'='*60}")
    print("\n📝 This threshold was selected WITHOUT touching the test set.")
    print("   Update Stage1Gate.FROZEN_OPERATING_THRESHOLD_AUDIT_RUN_4 to this value,")
    print("   then re-run audit_report.py and verify_calibration_and_metrics.py.")
    
    # ✅ من حلّي: Nearby alternatives
    best_idx = candidates.index(best)
    print("\n🔎 Nearby alternatives (±5 candidates):")
    print("Threshold | FAR      | Recall")
    print("-" * 35)
    for i in range(max(0, best_idx-5), min(len(candidates), best_idx+6)):
        th, far, rec = candidates[i]
        marker = " ← SELECTED" if i == best_idx else ""
        print(f"{th:.4f}    | {far*100:6.2f}% | {rec*100:6.2f}%{marker}")
else:
    min_far_candidate = min(candidates, key=lambda x: x[1])
    print(f"\n{'='*60}")
    print(f"❌ No threshold found with FAR ≤ 4.20% in range [0.25, 0.85]")
    print(f"{'='*60}")
    print(f"\n⚠️  Minimum achievable OOF FAR: {min_far_candidate[1]*100:.2f}% at threshold {min_far_candidate[0]:.4f}")
    print(f"   Recall at that threshold: {min_far_candidate[2]*100:.2f}%")
    
    # ✅ من حلّي: 10 أقل FAR
    print("\n🔎 10 candidates with LOWEST FAR (even if > 4.20%):")
    print("Threshold | FAR      | Recall")
    print("-" * 35)
    sorted_by_far = sorted(candidates, key=lambda x: x[1])
    for th, far, rec in sorted_by_far[:10]:
        print(f"{th:.4f}    | {far*100:6.2f}% | {rec*100:6.2f}%")
    
    print("\n💡 Consider:")
    print("   • Relaxing FAR constraint slightly (e.g., 4.5% or 5.0%)")
    print("   • Checking GroupedCalibratedClassifier fit quality")
    print("   • Inspecting OOF probability distribution (oof_probs_cache.npy)")