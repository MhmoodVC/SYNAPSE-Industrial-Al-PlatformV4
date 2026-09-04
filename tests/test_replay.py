from pathlib import Path

from data.persistence import load_synthetic_csv
from inference.replay import load_replay_snapshot


PROJECT_ROOT = Path(__file__).parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "synthetic_pump_dataset.csv"


def test_replay_snapshot_composes_existing_layers_from_csv() -> None:
    observations, truth = load_synthetic_csv(DATA_PATH)
    run_id = truth[0].run_id

    snapshot = load_replay_snapshot(DATA_PATH, run_id=run_id, row_index=10)

    assert len(observations) == len(truth) == 110000
    assert len({item.run_id for item in truth}) == 110
    assert len(snapshot.observations) == 1000
    assert snapshot.current_features["run_id"] == run_id
    assert snapshot.evidence.run_id == run_id
    assert len(snapshot.risk.contributions) == 4
    assert len(snapshot.arena.options) == 3
    assert snapshot.guardrails.status in {"UNKNOWN", "FAIL", "PASS"}
