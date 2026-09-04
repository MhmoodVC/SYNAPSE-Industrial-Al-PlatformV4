"""SYNAPSE pipeline entry point using persisted sensor data."""

from pathlib import Path

from inference.pipeline import run_persisted_pipeline


DEFAULT_DATA_PATH = Path(__file__).parent / "data" / "raw" / "synthetic_pump_dataset.csv"


def main() -> None:
    """Run the persisted sensor-to-decision validation pipeline."""
    result = run_persisted_pipeline(DEFAULT_DATA_PATH)
    print(f"Processed {result.observation_count} observations across {result.run_count} runs from {result.source_path}")
    print(f"Evidence cards: {result.evidence_count}; alerts: {result.alert_count}; simulations blocked: {result.simulation_blocked}")


if __name__ == "__main__":
    main()
