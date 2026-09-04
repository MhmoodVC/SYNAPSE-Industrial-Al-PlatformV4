"""Unit and contract integration tests for IoT streaming adapter."""

from datetime import datetime, timezone
import json
import pytest

from iot import IoTAdapter, IoTPayloadError, ingest_iot_payload
from data.contract import SensorRecord
from features.engineering import BaselineProfile, transform_records
from decision.diagnosis import diagnose
from decision.risk_engine import assess_risk
from explainability.evidence import build_evidence_card


def test_iot_adapter_ingests_valid_json_payload() -> None:
    adapter = IoTAdapter()
    raw_payload = json.dumps({
        "timestamp": "2025-01-01T10:00:00Z",
        "run_id": "iot-run-001",
        "pump_id": "pump-101",
        "pressure": 4.82,
        "flow": 38.5,
        "temperature": 42.1,
        "vibration": 1.62,
        "motor_current": 8.75,
        "operating_load": 0.72,
        "operating_regime": "nominal",
        "pump_state": "running",
    })

    record, issues = adapter.ingest_payload(raw_payload)
    assert isinstance(record, SensorRecord)
    assert len(issues) == 0
    assert record.run_id == "iot-run-001"
    assert record.pump_id == "pump-101"
    assert record.pressure == 4.82
    assert record.flow == 38.5
    assert record.temperature == 42.1
    assert record.vibration == 1.62
    assert record.motor_current == 8.75
    assert record.operating_load == 0.72
    assert record.operating_regime == "nominal"
    assert record.pump_state == "running"


def test_iot_adapter_handles_missing_and_corrupt_values() -> None:
    adapter = IoTAdapter()
    corrupt_payload = {
        "timestamp": "2025-01-01T10:01:00Z",
        "pressure": -5.0,  # Negative pressure is out of range
        "flow": "invalid_number",  # Non-numeric
        "temperature": 45.0,
        "vibration": None,
        "motor_current": float("nan"),  # NaN
    }

    record, issues = adapter.ingest_payload(corrupt_payload)
    assert record.pressure is None
    assert record.flow is None
    assert record.temperature == 45.0
    assert record.vibration is None
    assert record.motor_current is None
    assert len(issues) >= 3
    issue_codes = {iss.code for iss in issues}
    assert "OUT_OF_RANGE" in issue_codes
    assert "TYPE_ERROR" in issue_codes
    assert "INVALID_VALUE" in issue_codes


def test_iot_adapter_rejects_malformed_json() -> None:
    adapter = IoTAdapter()
    with pytest.raises(IoTPayloadError):
        adapter.ingest_payload("{bad json: true,")


def test_iot_payload_downstream_pipeline_compatibility() -> None:
    adapter = IoTAdapter()
    raw_batch = [
        {
            "timestamp": f"2025-01-01T10:{i:02d}:00Z",
            "run_id": "iot-stream-01",
            "pump_id": "pump-001",
            "pressure": 4.8 + i * 0.01,
            "flow": 38.0 + i * 0.1,
            "temperature": 42.0 + i * 0.05,
            "vibration": 1.55 + i * 0.02,
            "motor_current": 8.5 + i * 0.03,
            "operating_load": 0.70,
        }
        for i in range(20)
    ]

    records, issues = adapter.ingest_batch(raw_batch)
    assert len(records) == 20
    assert len(issues) == 0

    # Downstream feature transformation
    baseline = BaselineProfile.fit(records)
    features = transform_records(records, baseline)
    assert len(features) == 20
    latest = features[-1]

    # Diagnosis & Risk assessment
    diag = diagnose(latest)
    risk = assess_risk(diag, persistence=0.5, operating_load=float(latest["operating_load"]))
    assert 0.0 <= risk.score <= 1.0

    # Evidence Card generation
    card = build_evidence_card(
        latest,
        diag,
        baseline,
        timestamp=latest["timestamp"],
        run_id=str(latest["run_id"]),
        pump_id=str(latest["pump_id"]),
    )
    assert card.run_id == "iot-stream-01"
    assert len(card.evidence) > 0
