"""Event-level alert evaluation metrics and false alarm budget enforcement."""

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from decision.alerts import Alert


@dataclass(frozen=True)
class AlertEvaluationMetrics:
    total_events: int
    detected_events: int
    missed_events: int
    event_recall: float
    total_alerts_emitted: int
    false_alarms: int
    false_alarm_rate: float
    budget_compliant: bool
    mean_detection_delay_seconds: Optional[float]


def evaluate_event_alerts(
    truth: Iterable[object],
    alerts: Iterable[Alert],
    *,
    false_alarm_budget: float = 0.05,
) -> AlertEvaluationMetrics:
    """Evaluate event-level alert recall, detection delay, and false alarm budget."""
    run_events: dict[str, dict[str, object]] = {}
    for item in truth:
        run_id = getattr(item, "run_id", None)
        fault_type = getattr(item, "fault_type", None)
        event_start = getattr(item, "event_start", None)
        event_end = getattr(item, "event_end", None)
        if run_id and run_id not in run_events:
            run_events[run_id] = {
                "fault_type": fault_type,
                "event_start": event_start,
                "event_end": event_end,
            }

    alerts_by_run: dict[str, list[Alert]] = {}
    all_alerts = list(alerts)
    for alert in all_alerts:
        alerts_by_run.setdefault(alert.run_id, []).append(alert)

    fault_runs = {
        run_id: meta
        for run_id, meta in run_events.items()
        if meta["fault_type"] != "normal" and meta["event_start"] is not None
    }

    detected_count = 0
    delays: list[float] = []
    for run_id, meta in fault_runs.items():
        run_alerts = alerts_by_run.get(run_id, [])
        valid_alerts = [
            a for a in run_alerts
            if a.timestamp >= meta["event_start"] and (meta["event_end"] is None or a.timestamp <= meta["event_end"])
        ]
        if valid_alerts:
            detected_count += 1
            first_alert = min(valid_alerts, key=lambda a: a.timestamp)
            delay = (first_alert.timestamp - meta["event_start"]).total_seconds()
            delays.append(max(0.0, delay))

    total_events = len(fault_runs)
    missed_count = total_events - detected_count
    event_recall = detected_count / total_events if total_events > 0 else 1.0

    false_alarms = 0
    for alert in all_alerts:
        meta = run_events.get(alert.run_id)
        if meta is None or meta["fault_type"] == "normal":
            false_alarms += 1
        elif meta["event_start"] is not None and alert.timestamp < meta["event_start"]:
            false_alarms += 1

    total_alerts = len(all_alerts)
    false_alarm_rate = false_alarms / total_alerts if total_alerts > 0 else 0.0
    budget_compliant = false_alarm_rate <= false_alarm_budget
    mean_delay = (sum(delays) / len(delays)) if delays else None

    return AlertEvaluationMetrics(
        total_events=total_events,
        detected_events=detected_count,
        missed_events=missed_count,
        event_recall=round(event_recall, 4),
        total_alerts_emitted=total_alerts,
        false_alarms=false_alarms,
        false_alarm_rate=round(false_alarm_rate, 4),
        budget_compliant=budget_compliant,
        mean_detection_delay_seconds=round(mean_delay, 2) if mean_delay is not None else None,
    )
