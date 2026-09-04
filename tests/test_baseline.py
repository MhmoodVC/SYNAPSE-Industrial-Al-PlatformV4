from math import isfinite
from pathlib import Path

from data.persistence import export_synthetic_csv, load_synthetic_csv
from models.baseline import train_baseline_models, train_from_csv


def test_baselines_use_grouped_holdout_and_return_metrics(tmp_path: Path) -> None:
    path = tmp_path / "baseline.csv"
    export_synthetic_csv(path, seed=31, points_per_run=24, missing_rate=0.02)
    observations, truth = load_synthetic_csv(path)

    models, classifier_metrics, anomaly_metrics = train_baseline_models(observations, truth)

    assert classifier_metrics.test_runs == ("run-0011", "run-0010") or len(classifier_metrics.test_runs) == 2
    assert classifier_metrics.test_runs
    assert "run-0011" not in classifier_metrics.classes_in_training
    assert anomaly_metrics.normal_training_rows > 0
    assert anomaly_metrics.test_rows > 0
    assert all(isfinite(value) for value in (classifier_metrics.macro_f1, classifier_metrics.precision, classifier_metrics.recall, classifier_metrics.balanced_accuracy))
    assert all(isfinite(value) for value in (anomaly_metrics.balanced_accuracy, anomaly_metrics.precision, anomaly_metrics.recall))
    assert models.classifier is not None
    assert models.anomaly_detector is not None


def test_baselines_train_directly_from_persisted_csv(tmp_path: Path) -> None:
    path = tmp_path / "persisted.csv"
    export_synthetic_csv(path, seed=8, points_per_run=18, missing_rate=0)

    _, classifier_metrics, anomaly_metrics = train_from_csv(path)

    assert classifier_metrics.test_runs
    assert anomaly_metrics.test_rows > 0
