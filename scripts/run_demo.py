"""Run the documented SYNAPSE competition demo summary."""

from pathlib import Path

from inference.pipeline import run_persisted_pipeline
from inference.replay import load_replay_snapshot


PROJECT_ROOT = Path(__file__).parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "synthetic_pump_dataset.csv"


if __name__ == "__main__":
    pipeline = run_persisted_pipeline(DATA_PATH)
    snapshot = load_replay_snapshot(DATA_PATH, run_id="run-0002", row_index=80)
    print("SYNAPSE DEMO | SIMULATION")
    print(f"source={DATA_PATH}")
    print(f"pipeline_observations={pipeline.observation_count}")
    print(f"pipeline_alerts={pipeline.alert_count}")
    print(f"scenario_run={snapshot.evidence.run_id}")
    print(f"diagnosis={snapshot.diagnosis.diagnosis}")
    print(f"risk_score={snapshot.risk.score:.6f}")
    print(f"review_required={snapshot.guardrails.human_review_required}")
    print(f"recommendation={snapshot.arena.recommended_action}")
