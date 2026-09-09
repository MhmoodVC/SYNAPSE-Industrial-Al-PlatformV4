# FILE: src/data/iot.py
"""IoT and MQTT streaming payload adapter for SYNAPSE sensor contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any, Dict, Optional, Union


class IoTPayloadError(ValueError):
    """Raised when an incoming IoT payload is malformed or unparseable."""


@dataclass
class SensorRecord:
    """Validated sensor reading conforming to SYNAPSE data contract."""
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


class IoTAdapter:
    """Production-ready adapter mapping external streaming messages to SensorRecord contracts."""

    VALID_REGIMES = {"low", "nominal", "high"}
    VALID_STATES = {"running", "stopped", "startup", "shutdown"}
    SENSOR_FIELDS = ["pressure", "flow", "temperature", "vibration", "motor_current"]

    def __init__(self, default_pump_id: str = "pump-001", default_run_id: str = "iot-stream") -> None:
        self.default_pump_id = default_pump_id
        self.default_run_id = default_run_id

    def ingest_payload(
        self,
        payload: Union[str, bytes, Dict[str, Any]],
    ) -> tuple[SensorRecord, tuple]:
        """Parse a single raw JSON or dict payload into a valid SensorRecord."""
        data = self._parse_raw(payload)
        issues = []

        run_id = str(data.get("run_id") or data.get("runId") or self.default_run_id)
        pump_id = str(data.get("pump_id") or data.get("pumpId") or self.default_pump_id)

        # Parse timestamp
        raw_ts = data.get("timestamp") or data.get("time") or data.get("ts")
        timestamp = self._parse_timestamp(raw_ts)

        # Parse sensor channels
        sensor_values: Dict[str, Optional[float]] = {}
        for field in self.SENSOR_FIELDS:
            val = data.get(field)
            if val is None:
                sensor_values[field] = None
            else:
                try:
                    num_val = float(val)
                    if num_val != num_val or num_val == float("inf") or num_val == float("-inf"):
                        sensor_values[field] = None
                    # ⚠️ vibration can be negative (bipolar accelerometer)
                    elif field != "vibration" and num_val < 0:
                        sensor_values[field] = None
                    else:
                        sensor_values[field] = num_val
                except (ValueError, TypeError):
                    sensor_values[field] = None

        # Operating load
        raw_load = data.get("operating_load")
        if raw_load is None:
            raw_load = data.get("load")
        if raw_load is None:
            raw_load = 0.70
        
        try:
            load = max(0.0, min(1.0, float(raw_load)))
        except (ValueError, TypeError):
            load = 0.70

        # Operating regime
        regime = str(data.get("operating_regime") or data.get("regime") or "").lower()
        if regime not in self.VALID_REGIMES:
            regime = "high" if load > 0.80 else "low" if load < 0.60 else "nominal"

        # Pump state
        state = str(data.get("pump_state") or data.get("state") or "running").lower()
        if state not in self.VALID_STATES:
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

    def _parse_raw(self, payload: Union[str, bytes, Dict[str, Any]]) -> Dict[str, Any]:
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

    def _parse_timestamp(self, raw_ts: Any) -> datetime:
        if isinstance(raw_ts, datetime):
            return raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
        if isinstance(raw_ts, (int, float)):
            return datetime.fromtimestamp(raw_ts, tz=timezone.utc)
        if isinstance(raw_ts, str):
            try:
                cleaned = raw_ts.replace("Z", "+00:00")
                return datetime.fromisoformat(cleaned)
            except ValueError:
                pass
        return datetime.now(timezone.utc)


def ingest_iot_payload(payload: Union[str, bytes, Dict[str, Any]]) -> SensorRecord:
    """Convenience helper to parse a single payload directly into a SensorRecord."""
    adapter = IoTAdapter()
    record, _ = adapter.ingest_payload(payload)
    return record