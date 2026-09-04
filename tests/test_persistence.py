from pathlib import Path

from data.persistence import CSV_FIELDS, export_synthetic_csv, load_synthetic_csv
from data.synthetic import generate_runs


def test_csv_round_trip_preserves_observations_and_truth(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.csv"
    observations, truth = generate_runs(
        seed=21,
        pump_ids=("pump-a", "pump-b"),
        scenarios=("normal", "cavitation", "sudden_failure"),
        points_per_run=18,
        missing_rate=0.08,
    )

    rows, missing_cells = export_synthetic_csv(
        path,
        seed=21,
        pump_ids=("pump-a", "pump-b"),
        scenarios=("normal", "cavitation", "sudden_failure"),
        points_per_run=18,
        missing_rate=0.08,
    )
    loaded_observations, loaded_truth = load_synthetic_csv(path)

    assert rows == len(observations) == len(truth)
    assert missing_cells > 0
    assert path.exists()
    assert loaded_observations == observations
    assert loaded_truth == truth


def test_csv_has_observation_and_target_schema(tmp_path: Path) -> None:
    path = tmp_path / "schema.csv"
    export_synthetic_csv(path, scenarios=("normal",), points_per_run=12, missing_rate=0)

    header = path.read_text(encoding="utf-8").splitlines()[0].split(",")

    assert header == list(CSV_FIELDS)
    assert "fault_type" in header
    assert "failure_flag" in header
