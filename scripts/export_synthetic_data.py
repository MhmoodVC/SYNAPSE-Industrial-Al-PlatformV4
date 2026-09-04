"""Generate the default persisted SYNAPSE synthetic dataset."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data.persistence import export_synthetic_csv
from data.synthetic import FAULT_TYPES
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "synthetic_pump_dataset.csv"


if __name__ == "__main__":
    runs_per_scenario = 10
    scenarios = [scenario for scenario in FAULT_TYPES for _ in range(runs_per_scenario)]
    rows, missing_cells = export_synthetic_csv(
        DATA_PATH,
        scenarios=scenarios,
        points_per_run=1000,
        missing_rate=0.015,
    )
    print(f"Exported {rows} rows across {len(scenarios)} runs to {DATA_PATH}")
    print(f"Missing sensor cells: {missing_cells}")
