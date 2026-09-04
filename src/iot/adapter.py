"""IoT and MQTT streaming payload adapter for SYNAPSE sensor contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Iterable, Optional, Union

from data.contract import (
    SENSOR_FIELDS,
    VALID_REGIMES,
    VALID_STATES,
    SensorRecord,
    ValidationIssue,
)


class IoTPayloadError(ValueError):
    """Raised when an incoming IoT payload is malformed or unparseable."""


class IoTAdapter:
    """Production-ready adapter mapping external streaming messages to SensorRecord contracts."""

    def __init__(self, default_pump_id: str = "pump-001", default_run_id: str = "iot-stream") -> None:
        self.default_pump_id = default_pump_id
        self.default_run_id = default_run_id

    def ingest_payload(
        self,
        payload: Union[str, bytes, dict[str, Any]],
    ) -> tuple[SensorRecord, tuple[ValidationIssue, ...]]:
        """Parse a single raw JSON or dict payload into a valid SensorRecord."""
        data = self._parse_raw(payload)
        issues: list[ValidationIssue] = []

        run_id = str(data.get("run_id") or data.get("runId") or self.default_run_id)
        pump_id = str(data.get("pump_id") or data.get("pumpId") or self.default_pump_id)

        # Parse timestamp
        raw_ts = data.get("timestamp") or data.get("time") or data.get("ts")
        timestamp = self._parse_timestamp(raw_ts, run_id, issues)

        # Parse sensor channels
        sensor_values: dict[str, Optional[float]] = {}
        for field in SENSOR_FIELDS:
            val = data.get(field)
            if val is None:
                sensor_values[field] = None
            else:
                try:
                    num_val = float(val)
                    if num_val != num_val or num_val == float("inf") or num_val == float("-inf"):
                        sensor_values[field] = None
                        issues.append(ValidationIssue(run_id, timestamp, field, "INVALID_VALUE", f"{field} is NaN or Inf"))
                    elif num_val < 0:
                        sensor_values[field] = None
                        issues.append(ValidationIssue(run_id, timestamp, field, "OUT_OF_RANGE", f"{field} cannot be negative"))
                    else:
                        sensor_values[field] = num_val
                except (ValueError, TypeError):
                    sensor_values[field] = None
                    issues.append(ValidationIssue(run_id, timestamp, field, "TYPE_ERROR", f"{field} must be numeric"))

        # Operating load
        raw_load = data.get("operating_load") or data.get("load") or 0.70
        try:
            load = max(0.0, min(1.0, float(raw_load)))
        except (ValueError, TypeError):
            load = 0.70
            issues.append(ValidationIssue(run_id, timestamp, "operating_load", "TYPE_ERROR", "invalid operating_load"))

        # Operating regime
        regime = str(data.get("operating_regime") or data.get("regime") or "").lower()
        if regime not in VALID_REGIMES:
            regime = "high" if load > 0.80 else "low" if load < 0.60 else "nominal"

        # Pump state
        state = str(data.get("pump_state") or data.get("state") or "running").lower()
        if state not in VALID_STATES:
            state = "running"

        record = SensorRecord(
            timestamp=timestamp,
            run_id=run_id,
            pump_id=pump_id,
            pressure=sensor_values["pressure"],
            flow=sensor_values["flow"],
            temperature=sensor_values["temperature"],
            vibration=sensor_values["vibration"],
            motor_current=sensor_values["motor_current"],
            operating_load=load,
            operating_regime=regime,
            pump_state=state,
        )
        return record, tuple(issues)

    def ingest_batch(
        self,
        payloads: Iterable[Union[str, bytes, dict[str, Any]]],
    ) -> tuple[list[SensorRecord], list[ValidationIssue]]:
        """Ingest a stream or batch of IoT messages."""
        records: list[SensorRecord] = []
        all_issues: list[ValidationIssue] = []
        for payload in payloads:
            record, issues = self.ingest_payload(payload)
            records.append(record)
            all_issues.extend(issues)
        return records, all_issues

    def _parse_raw(self, payload: Union[str, bytes, dict[str, Any]]) -> dict[str, Any]:
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, (str, bytes)):
            try:
                parsed = json.loads(payload)
                if not isinstance(parsed, dict):
                    raise IoTPayloadError("IoT JSON payload must be an object")
                return parsed
            except json.JSONDecodeError as err:
                raise IoTPayloadError(f"Malformed IoT JSON: {err}") from err
        raise IoTPayloadError(f"Unsupported IoT payload type: {type(payload)}")

    def _parse_timestamp(self, raw_ts: Any, run_id: str, issues: list[ValidationIssue]) -> datetime:
        if isinstance(raw_ts, datetime):
            return raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
        if isinstance(raw_ts, (int, float)):
            return datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        if isinstance(raw_ts, str):
            try:
                # Handle ISO format
                cleaned = raw_ts.replace("Z", "+00:00")
                return datetime.fromisoformat(cleaned)
            except ValueError:
                issues.append(ValidationIssue(run_id, None, "timestamp", "INVALID_TIMESTAMP", f"Cannot parse timestamp {raw_ts}"))
        return datetime.now(timezone.utc)


def ingest_iot_payload(payload: Union[str, bytes, dict[str, Any]]) -> SensorRecord:
    """Convenience helper to parse a single payload directly into a SensorRecord."""
    adapter = IoTAdapter()
    record, _ = adapter.ingest_payload(payload)
    return record
