from pathlib import Path

from inference.pipeline import run_persisted_pipeline


PROJECT_ROOT = Path(__file__).parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "synthetic_pump_dataset.csv"


def test_persisted_pipeline_reaches_every_decision_stage() -> None:
    result = run_persisted_pipeline(DATA_PATH)

    assert result.observation_count == result.truth_count == 110000
    assert result.run_count == 110
    assert result.diagnosis_count == result.evidence_count == result.arena_count == result.guardrail_count == 110000
    assert result.quality_flag_count > 0
    assert result.simulation_blocked is True
