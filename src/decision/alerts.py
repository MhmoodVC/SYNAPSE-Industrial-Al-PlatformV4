"""Persistence, hysteresis, cooldown, and hard-limit alert handling."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .risk_engine import RiskAssessment


@dataclass(frozen=True)
class Alert:
    timestamp: datetime
    run_id: str
    pump_id: str
    alert_type: str
    level: str
    message: str
    risk_score: Optional[float]
    confirmed_by: tuple[str, ...] = ()


@dataclass
class _AlertState:
    active: bool = False
    consecutive_high: int = 0
    last_emitted: Optional[datetime] = None


class AlertEngine:
    """Stateful alert engine; callers feed records in timestamp order."""

    def __init__(
        self,
        *,
        persistence: int = 2,
        trigger_threshold: float = 0.40,
        clear_threshold: float = 0.25,
        cooldown: timedelta = timedelta(minutes=5),
        require_multi_sensor: bool = False,
    ) -> None:
        if persistence < 1:
            raise ValueError("persistence must be at least 1")
        if not 0 <= clear_threshold < trigger_threshold <= 1:
            raise ValueError("thresholds must satisfy 0 <= clear < trigger <= 1")
        self.persistence = persistence
        self.trigger_threshold = trigger_threshold
        self.clear_threshold = clear_threshold
        self.cooldown = cooldown
        self.require_multi_sensor = require_multi_sensor
        self._states: dict[tuple[str, str], _AlertState] = {}

    def process(
        self,
        *,
        timestamp: datetime,
        run_id: str,
        pump_id: str,
        assessment: RiskAssessment,
        hard_limit_message: Optional[str] = None,
        confirming_sensors: Optional[tuple[str, ...]] = None,
    ) -> tuple[Alert, ...]:
        """Process one timestamp and return newly emitted alerts."""
        alerts: list[Alert] = []
        if hard_limit_message:
            alerts.append(Alert(timestamp, run_id, pump_id, "HARD_LIMIT", "critical", hard_limit_message, None))
        key = (run_id, pump_id)
        state = self._states.setdefault(key, _AlertState())
        if assessment.score >= self.trigger_threshold:
            state.consecutive_high += 1
        else:
            state.consecutive_high = 0
        can_emit = state.last_emitted is None or timestamp - state.last_emitted >= self.cooldown
        
        # Multi-sensor confirmation check
        multi_confirmed = True
        confirmed_by = confirming_sensors or ()
        if self.require_multi_sensor and confirming_sensors is not None:
            if len(confirming_sensors) < 2:
                multi_confirmed = False

        if not state.active and state.consecutive_high >= self.persistence and can_emit and multi_confirmed:
            state.active = True
            state.last_emitted = timestamp
            alerts.append(
                Alert(
                    timestamp,
                    run_id,
                    pump_id,
                    "AI_DIAGNOSTIC",
                    assessment.level,
                    "persistent risk threshold exceeded",
                    assessment.score,
                    confirmed_by=confirmed_by,
                )
            )
        elif state.active and assessment.score <= self.clear_threshold:
            state.active = False
            state.consecutive_high = 0
        return tuple(alerts)
