from datetime import datetime, timezone

from cleaning.sensor_cleaning import clean_records
from data.contract import SensorRecord, validate_records


TIMESTAMP = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_record(**changes: object) -> SensorRecord:
    values = {
        "timestamp": TIMESTAMP,
        "run_id": "run-1",
        "pump_id": "pump-1",
        "pressure": 4.5,
        "flow": 38.0,
        "temperature": 48.0,
        "vibration": 1.8,
        "motor_current": 9.0,
        "operating_load": 0.7,
        "operating_regime": "nominal",
        "pump_state": "running",
    }
    values.update(changes)
    return SensorRecord(**values)


def test_contract_reports_invalid_values_and_time_order() -> None:
    records = [
        make_record(pressure=-1.0),
        make_record(timestamp=TIMESTAMP),
    ]

    issues = validate_records(records)

    assert {issue.code for issue in issues} == {"negative_value", "not_increasing"}


def test_cleaning_flags_invalid_values_and_forward_fills_causally() -> None:
    records = [
        make_record(),
        make_record(timestamp=TIMESTAMP.replace(second=1), pressure=None),
        make_record(timestamp=TIMESTAMP.replace(second=2), pressure=float("nan")),
        make_record(timestamp=TIMESTAMP.replace(second=3), pressure=4.8),
    ]

    result = clean_records(records, max_forward_fill=1)

    assert result.records[1].pressure == 4.5
    assert result.records[2].pressure is None
    assert result.records[3].pressure == 4.8
    assert any(flag.code == "negative_value" for flag in result.quality_flags) is False
    assert any(flag.code == "not_finite" for flag in result.quality_flags)
    assert any(flag.code == "forward_filled" for flag in result.quality_flags)


def test_cleaning_preserves_record_identity_and_reports_contract_issues() -> None:
    record = make_record(operating_load=1.5)

    result = clean_records([record])

    assert result.records[0].run_id == "run-1"
    assert result.records[0].pump_id == "pump-1"
    assert any(issue.field == "operating_load" for issue in result.validation_issues)
