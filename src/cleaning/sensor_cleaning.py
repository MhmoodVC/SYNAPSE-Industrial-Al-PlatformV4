"""Sensor quality checks and causal missing-value handling."""

from dataclasses import dataclass, replace
from typing import Optional

from data.contract import SENSOR_FIELDS, SensorRecord, ValidationIssue, validate_records


@dataclass(frozen=True)
class QualityFlag:
    run_id: str
    timestamp: object
    field: str
    code: str
    detail: str


@dataclass(frozen=True)
class CleaningResult:
    records: list[SensorRecord]
    quality_flags: list[QualityFlag]
    validation_issues: list[ValidationIssue]


def clean_records(records: list[SensorRecord], *, max_forward_fill: int = 2) -> CleaningResult:
    """Clean sensor records without using future observations.

    Invalid numeric values become missing and are flagged. Missing values are
    forward-filled only after a known value in the same run and only up to the
    configured consecutive-gap limit.
    """
    if max_forward_fill < 0:
        raise ValueError("max_forward_fill must be non-negative")
    issues = validate_records(records)
    flags: list[QualityFlag] = []
    cleaned: list[SensorRecord] = []
    previous_values: dict[str, dict[str, Optional[float]]] = {}
    gap_lengths: dict[str, dict[str, int]] = {}

    for record in records:
        values = {field: getattr(record, field) for field in SENSOR_FIELDS}
        run_previous = previous_values.setdefault(record.run_id, {})
        run_gaps = gap_lengths.setdefault(record.run_id, {})
        for issue in (item for item in issues if item.timestamp == record.timestamp and item.run_id == record.run_id):
            if issue.field in SENSOR_FIELDS and issue.code in {"not_finite", "negative_value"}:
                values[issue.field] = None
                flags.append(QualityFlag(record.run_id, record.timestamp, issue.field, issue.code, issue.message))
        for field, value in values.items():
            if value is None:
                run_gaps[field] = run_gaps.get(field, 0) + 1
                flags.append(QualityFlag(record.run_id, record.timestamp, field, "missing", "sensor value is missing"))
                if run_previous.get(field) is not None and run_gaps[field] <= max_forward_fill:
                    values[field] = run_previous[field]
                    flags.append(QualityFlag(record.run_id, record.timestamp, field, "forward_filled", "filled from previous value"))
            else:
                run_previous[field] = value
                run_gaps[field] = 0
        cleaned.append(replace(record, **values))
    return CleaningResult(cleaned, flags, issues)
