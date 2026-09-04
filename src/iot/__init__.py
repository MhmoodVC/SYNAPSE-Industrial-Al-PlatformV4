"""IoT streaming and telemetry ingestion adapters for SYNAPSE."""

from .adapter import IoTAdapter, IoTPayloadError, ingest_iot_payload

__all__ = [
    "IoTAdapter",
    "IoTPayloadError",
    "ingest_iot_payload",
]
