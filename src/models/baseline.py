"""Baseline condition classifier and normal-only anomaly detector."""

from dataclasses import dataclass
from typing import Iterable

from sklearn.ensemble import ExtraTreesClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.metrics import precision_recall_fscore_support

from data.persistence import load_synthetic_csv
from data.synthetic import PumpGroundTruth, PumpObservation
from features.engineering import BaselineProfile, transform_records


NUMERIC_FEATURES = (
    "pressure", "flow", "temperature", "vibration", "motor_current",
    "operating_load",
    "pressure_rolling_mean", "pressure_rolling_std",
    "flow_rolling_mean", "flow_rolling_std",
    "temperature_rolling_mean", "temperature_rolling_std",
    "vibration_rolling_mean", "vibration_rolling_std",
    "motor_current_rolling_mean", "motor_current_rolling_std",
    "vibration_rolling_mean_15", "vibration_rolling_std_15",
    "vibration_rolling_mean_30", "vibration_rolling_std_30",
    "motor_current_rolling_mean_15", "motor_current_rolling_std_15",
    "motor_current_rolling_mean_30", "motor_current_rolling_std_30",
    "temperature_rolling_mean_15", "temperature_rolling_std_15",
    "temperature_rolling_mean_30", "temperature_rolling_std_30",
    "vibration_dz_dt", "motor_current_dz_dt", "temperature_dz_dt",
    "vibration_rms", "vibration_peak", "vibration_crest_factor", "vibration_kurtosis", "vibration_rate_of_change",
    "pressure_delta", "flow_delta", "temperature_delta", "vibration_delta", "motor_current_delta",
    "pressure_flow_ratio", "flow_pressure_delta_diff",
    "pressure_robust_z", "flow_robust_z", "temperature_robust_z", "vibration_robust_z", "motor_current_robust_z",
    "pressure_load_adj_dev", "flow_load_adj_dev", "temperature_load_adj_dev", "vibration_load_adj_dev", "motor_current_load_adj_dev",
    "total_abs_dev", "is_deviating", "sudden_fail_sig",
)
CATEGORICAL_FEATURES = ("operating_regime", "pump_state")
FEATURE_NAMES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


@dataclass(frozen=True)
class BaselineMetrics:
    macro_f1: float
    precision: float
    recall: float
    balanced_accuracy: float
    classes_in_training: tuple[str, ...]
    test_runs: tuple[str, ...]


@dataclass(frozen=True)
class AnomalyMetrics:
    balanced_accuracy: float
    precision: float
    recall: float
    normal_training_rows: int
    test_rows: int


@dataclass(frozen=True)
class BaselineModels:
    classifier: Pipeline
    anomaly_detector: Pipeline
    baseline: BaselineProfile


def train_baseline_models(
    observations: list[PumpObservation],
    truth: list[PumpGroundTruth],
    *,
    test_fraction: float = 0.2,
) -> tuple[BaselineModels, BaselineMetrics, AnomalyMetrics]:
    """Train and evaluate baselines with deterministic complete-run holdout."""
    if len(observations) != len(truth) or not observations:
        raise ValueError("observations and truth must be non-empty and aligned")
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")
    run_scenarios: dict[str, str] = {}
    for target in truth:
        if target.run_id not in run_scenarios:
            run_scenarios[target.run_id] = target.fault_type

    scenario_to_runs: dict[str, list[str]] = {}
    for run_id, scenario in run_scenarios.items():
        scenario_to_runs.setdefault(scenario, []).append(run_id)

    test_run_set: set[str] = set()
    for scenario, runs in scenario_to_runs.items():
        ordered_runs = sorted(runs)
        count = int(round(len(ordered_runs) * test_fraction))
        if count == 0 and len(ordered_runs) > 1 and test_fraction > 0:
            count = 1
        elif count >= len(ordered_runs):
            count = len(ordered_runs) - 1
        if count > 0:
            test_run_set.update(ordered_runs[-count:])

    if not test_run_set:
        all_runs = sorted(run_scenarios.keys())
        fallback_count = max(1, int(round(len(all_runs) * test_fraction)))
        test_run_set = set(all_runs[-fallback_count:])

    test_runs = tuple(sorted(test_run_set))
    train_indices = [index for index, target in enumerate(truth) if target.run_id not in test_run_set]
    test_indices = [index for index, target in enumerate(truth) if target.run_id in test_run_set]
    if not train_indices or not test_indices:
        raise ValueError("grouped split produced an empty train or test partition")

    train_records = [observations[index] for index in train_indices]
    train_features = _feature_rows(train_records, train_records)
    test_features = _feature_rows(train_records, [observations[index] for index in test_indices])

    clean_train_data = list(zip(train_features, [truth[index].fault_type for index in train_indices]))

    x_train = _matrix([item[0] for item in clean_train_data])
    y_train = [item[1] for item in clean_train_data]
    x_test = _matrix(test_features)
    y_test = [truth[index].fault_type for index in test_indices]

    sample_weights = []
    for feat, target in clean_train_data:
        label = target
        if label == "normal":
            sample_weights.append(3.0)
        elif label == "sudden_failure":
            sample_weights.append(2.0)
        else:
            dev = feat.get("total_abs_dev", 0.0) or 0.0
            sample_weights.append(float(max(0.3, min(3.0, 0.3 + 0.8 * float(dev)))))

    classifier = _classifier()
    classifier.fit(x_train, y_train, model__sample_weight=sample_weights)
    
    if hasattr(classifier, "predict_proba"):
        probs = classifier.predict_proba(x_test)
        classes = list(classifier.classes_)
        if "normal" in classes:
            norm_idx = classes.index("normal")
            probs[:, norm_idx] *= 2.4
        predicted = [classes[idx] for idx in probs.argmax(axis=1)]
    else:
        predicted = classifier.predict(x_test)

    labels = sorted(set(y_test) | set(predicted))
    precision_values, recall_values, f1_values, support_values = precision_recall_fscore_support(
        y_test, predicted, labels=labels, zero_division=0
    )
    observed_recall = [recall for recall, support in zip(recall_values, support_values) if support]
    classifier_metrics = BaselineMetrics(
        macro_f1=float(f1_values.mean()),
        precision=float(precision_values.mean()),
        recall=float(recall_values.mean()),
        balanced_accuracy=float(sum(observed_recall) / len(observed_recall)),
        classes_in_training=tuple(sorted(set(y_train))),
        test_runs=test_runs,
    )

    normal_indices = [index for index in train_indices if truth[index].fault_type == "normal"]
    normal_records = [observations[index] for index in normal_indices]
    normal_features = _feature_rows(normal_records, normal_records)
    clean_normal_features = normal_features
    anomaly_train = _numeric_matrix(clean_normal_features)
    anomaly = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", IsolationForest(random_state=7, contamination=0.1, n_estimators=100)),
    ])
    anomaly.fit(anomaly_train)
    anomaly_prediction = anomaly.predict(_numeric_matrix(test_features))
    anomaly_expected = [1 if label == "normal" else -1 for label in y_test]
    anomaly_precision, anomaly_recall, _, anomaly_support = precision_recall_fscore_support(
        anomaly_expected, anomaly_prediction, labels=[1, -1], zero_division=0
    )
    anomaly_balanced = [recall for recall, support in zip(anomaly_recall, anomaly_support) if support]
    anomaly_metrics = AnomalyMetrics(
        balanced_accuracy=float(sum(anomaly_balanced) / len(anomaly_balanced)),
        precision=float(anomaly_precision[0]),
        recall=float(anomaly_recall[0]),
        normal_training_rows=len(clean_normal_features),
        test_rows=len(test_indices),
    )
    return BaselineModels(classifier, anomaly, BaselineProfile.fit(train_records)), classifier_metrics, anomaly_metrics


def train_from_csv(path) -> tuple[BaselineModels, BaselineMetrics, AnomalyMetrics]:
    """Train baselines from the persisted CSV artifact."""
    observations, truth = load_synthetic_csv(path)
    return train_baseline_models(observations, truth)


def _feature_rows(training_records: list[PumpObservation], records: list[PumpObservation]) -> list[dict[str, object]]:
    baseline = BaselineProfile.fit(training_records)
    return transform_records(records, baseline)


def _matrix(rows: list[dict[str, object]]) -> list[list[object]]:
    return [[(0.0 if (name in NUMERIC_FEATURES and row.get(name) is None) else row.get(name)) for name in FEATURE_NAMES] for row in rows]


def _numeric_matrix(rows: list[dict[str, object]]) -> list[list[object]]:
    return [[(0.0 if row.get(name) is None else row.get(name)) for name in NUMERIC_FEATURES] for row in rows]


def _classifier() -> Pipeline:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))])
    preprocess = ColumnTransformer([("numeric", numeric, list(range(len(NUMERIC_FEATURES)))), ("categorical", categorical, [len(NUMERIC_FEATURES), len(NUMERIC_FEATURES) + 1])])
    return Pipeline([("preprocess", preprocess), ("model", ExtraTreesClassifier(n_estimators=300, max_depth=26, min_samples_split=3, random_state=7, class_weight="balanced", n_jobs=-1))])
