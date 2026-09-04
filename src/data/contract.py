"""Stable internal sensor data contract and validation."""

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Optional


SENSOR_FIELDS = ("pressure", "flow", "temperature", "vibration", "motor_current")
VALID_REGIMES = ("low", "nominal", "high")
VALID_STATES = ("running", "idle", "transitional")


@dataclass(frozen=True)
class SensorRecord:
    """Source-independent sensor representation used by downstream modules."""

    timestamp: datetime
    run_id: str
    pump_id: str
    pressure: Optional[float]
    flow: Optional[float]
    temperature: Optional[float]
    vibration: Optional[float]
    motor_current: Optional[float]
    operating_load: float
    operating_regime: str
    pump_state: str


@dataclass(frozen=True)
class ValidationIssue:
    """A contract violation or sensor quality issue."""

    run_id: str
    timestamp: Optional[datetime]
    field: str
    code: str
    message: str


class ContractError(ValueError):
    """Raised when records cannot be accepted by the internal contract."""


def validate_record(record: SensorRecord) -> list[ValidationIssue]:
    """Return all contract issues found in one sensor record."""
    issues: list[ValidationIssue] = []
    if record.timestamp.tzinfo is None or record.timestamp.utcoffset() is None:
        issues.append(_issue(record, "timestamp", "timezone_required", "timestamp must be timezone-aware"))
    for field in ("run_id", "pump_id"):
        if not getattr(record, field):
            issues.append(_issue(record, field, "required", f"{field} is required"))
    if record.operating_regime not in VALID_REGIMES:
        issues.append(_issue(record, "operating_regime", "invalid_value", "unknown operating regime"))
    if record.pump_state not in VALID_STATES:
        issues.append(_issue(record, "pump_state", "invalid_value", "unknown pump state"))
    if not math.isfinite(record.operating_load) or not 0 <= record.operating_load <= 1:
        issues.append(_issue(record, "operating_load", "out_of_range", "operating_load must be finite and between 0 and 1"))
    for field in SENSOR_FIELDS:
        value = getattr(record, field)
        if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
            issues.append(_issue(record, field, "not_finite", "sensor value must be finite or missing"))
        elif value is not None and field != "temperature" and value < 0:
            issues.append(_issue(record, field, "negative_value", "sensor value cannot be negative"))
    return issues


def validate_records(records: list[SensorRecord]) -> list[ValidationIssue]:
    """Validate record fields and ordering within each run."""
    issues: list[ValidationIssue] = []
    previous_by_run: dict[str, datetime] = {}
    for record in records:
        issues.extend(validate_record(record))
        previous = previous_by_run.get(record.run_id)
        if previous is not None and record.timestamp <= previous:
            issues.append(_issue(record, "timestamp", "not_increasing", "timestamps must increase within a run"))
        previous_by_run[record.run_id] = record.timestamp
    return issues


def require_valid_records(records: list[SensorRecord]) -> None:
    """Raise a concise error when any record violates the contract."""
    issues = validate_records(records)
    if issues:
        first = issues[0]
        raise ContractError(f"{first.code} in {first.field}: {first.message}")


def _issue(record: SensorRecord, field: str, code: str, message: str) -> ValidationIssue:
    return ValidationIssue(record.run_id, record.timestamp, field, code, message)
