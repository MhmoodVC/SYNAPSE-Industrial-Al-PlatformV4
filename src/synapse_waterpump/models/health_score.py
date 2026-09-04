"""Bridge to models.health_score."""

from models.health_score import (
    MIN_STD,
    SENSOR_FIELDS,
    SENSOR_WEIGHTS,
    HealthScoreResult,
    compute_health_score,
)

__all__ = [
    "MIN_STD",
    "SENSOR_FIELDS",
    "SENSOR_WEIGHTS",
    "HealthScoreResult",
    "compute_health_score",
]
