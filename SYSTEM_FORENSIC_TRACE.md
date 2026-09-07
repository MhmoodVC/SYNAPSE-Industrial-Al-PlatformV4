# SYSTEM FORENSIC TRACE REPORT
**Author:** Principal SCADA Architect & Core Systems Reliability Auditor
**Scope:** Exhaustive non-destructive codebase audit for signal jitter, UI badge flickering, and unstable prognostics.

---

## 1. Disk & Import Integrity Verification

An analysis of the repository root against the `src/` backend engine confirms that **no module shadowing** is occurring. However, the root directory is cluttered with obsolete scratch scripts and test drivers that pose a maintainability risk.

### Safe-to-Delete Inventory (Root Directory Cleanup):
The following 24 files are temporary diagnostic scripts, single-run verification stubs, and test harnesses that can be safely purged to clean up the environment:
* `app.py`, `check_run.py`, `debug_normal.py`, `debug_normal2.py`, `fix_tests.py`
* `run_pipeline.py`, `test_deadband.py`, `test_decay.py`, `test_io.py`, `test_latch_flapping.py`
* `test_late.py`, `test_late2.py`, `test_live_api.py`, `test_raw.py`, `test_run0026.py`, `test_sigs.py`
* `test_sim.py`, `test_snap.py`, `test_t934.py`, `test_thermo.py`, `test_truth.py`
* `verify.py`, `verify2.py`, `verify_all_runs.py`

---

## 2. Forensic Finding 1: Prognostics & RUL Explosion / Collapse

**Affected File:** `src/analytics/extensions.py`
**Original Bug Location:** Lines ~230-234 (Legacy `estimate_remaining_useful_life`)

**Root Cause:**
The algorithm calculated the `degradation_rate` (`dz/dt`) as a 1-second instantaneous derivative over a tiny window. Because the sample rate is 1 Hz (1/3600 of an hour), any single-frame sensor noise (e.g., a momentary 0.5σ deviation) was multiplied by 3600.
* A 1-frame vibration variance of `1.0σ` translates to a slope of `3,600.0 σz/s`.
* A 2.5σ baseline offset becomes `9,000.0 σz/s`.
Furthermore, the `max(1e-4, ...)` floor artificially forced stable, non-degrading machinery into a massive positive slope, outputting ~45,000 hours of remaining life (which the UI clamped to `10,000+`). Transient noise frames would then instantly flip the RUL down to `1 hours`.

### Permanent Resolution Blueprint:
**Before (Buggy):**
```python
        # Simple linear rate over window
        delta_vib = vib_z_history[-1] - vib_z_history[0]
        delta_temp = temp_z_history[-1] - temp_z_history[0]
        duration_hours = max(1.0 / 3600.0, (n - 1) / 3600.0)
        slope_vib = max(1e-4, delta_vib / duration_hours)
        slope_temp = max(1e-4, delta_temp / duration_hours)
```

**After (Surgical Fix):** Replace the instantaneous derivative with a 15-frame rolling Exponential Moving Average (EMA, `alpha=0.05`), capped at a hard physical ceiling of 5.0 σ/hr.
```python
        window = min(15, n - 1)
        alpha = 0.05  # EMA smoothing factor
        frame_dt_hours = 1.0 / 3600.0

        def _ema_slope(series: list[float]) -> float:
            """EMA of per-frame first-differences, converted to sigma/hour."""
            start = max(0, len(series) - window - 1)
            diffs = [series[i + 1] - series[i] for i in range(start, len(series) - 1)]
            if not diffs: return 0.0
            ema = diffs[0]
            for d in diffs[1:]: ema = alpha * d + (1.0 - alpha) * ema
            rate = ema / frame_dt_hours
            return max(-5.0, min(5.0, rate))

        slope_vib = _ema_slope(vib_z_history)
        slope_temp = _ema_slope(temp_z_history)
```

---

## 3. Forensic Finding 2: ISA-18.2 Alert Flickering & Human Review Leak

**Affected File:** `src/api/main.py`
**Original Bug Location:** Lines ~520-530 (Legacy `get_full_snapshot`)

**Root Cause:**
The frontend ISA-18.2 debounce requirements were completely circumvented. `alert_state` was derived statelessly from scratch on every single GET request purely based on the instantaneous `risk.level` of the current frame. Worse, the API intentionally *overwrote* the true state machine `persistence_count` calculated in `replay.py` by hardcoding it to `15` if the frame was not normal, and `0` otherwise.

### Permanent Resolution Blueprint:
**Before (Buggy):**
```python
    # Alert state determination
    alert_state = "NORMAL"
    if risk.level.upper() in ["CRITICAL", "HIGH"] or risk.score >= 0.7:
        alert_state = "CRITICAL"
    elif risk.level.upper() in ["WARNING", "MEDIUM"] or risk.score >= 0.35:
        alert_state = "WARNING"
    elif snapshot.diagnosis.review_required:
        alert_state = "HUMAN_REVIEW"
        
    ...
    "persistence_count": min(target_idx + 1, 15 if alert_state != "NORMAL" else 0),
```

**After (Surgical Fix):** Explicitly map the alert state through the `snapshot.persistence_count` state machine to enforce the 4-frame latch and suppress `HUMAN_REVIEW` on transient noise.
```python
    raw_level = risk.level.upper() if risk else "NORMAL"
    if raw_level in ("CRITICAL", "HIGH") or risk.score >= 0.75:
        raw_alert = "CRITICAL"
    elif raw_level in ("WARNING", "MEDIUM") or risk.score >= 0.40:
        raw_alert = "WARNING"
    elif snapshot.diagnosis.review_required and not snapshot.persistence_count >= 3:
        raw_alert = "HUMAN_REVIEW"
    else:
        raw_alert = "NORMAL"

    is_latched = snapshot.persistence_count >= 3
    if is_latched:
        alert_state = "WARNING" if raw_alert in ("HUMAN_REVIEW", "NORMAL") else raw_alert
    else:
        alert_state = "NORMAL" if raw_alert in ("CRITICAL", "WARNING") and snapshot.persistence_count < 4 else raw_alert
        
    ...
    "persistence_count": snapshot.persistence_count,
```

---

## 4. Forensic Finding 3: Premature Action Thrashing

**Affected Files:** `src/api/main.py` and `src/decision/arena.py`
**Original Bug Location:** Legacy `_format_decision_options` in `main.py` & `build_decision_arena` in `arena.py`.

**Root Cause:**
The system behaved as an unconstrained financial optimizer. The API endpoint (`_format_decision_options`) looped through the candidate actions and blindly picked the one with the lowest `net_expected_loss`. Because the cost crossover threshold between `$1,400` (Maintenance) and `$400` (No Action) fluctuates violently with instantaneous risk inputs, the UI thrashed between extremes on nominal machines. The system completely lacked an ALARP (As Low As Reasonably Practicable) safety ceiling or API 670 Zone D compliance guardrails.

### Permanent Resolution Blueprint:
**Before (Buggy):**
```python
    best_action = "NO_ACTION"
    min_loss = float("inf")
    formatted_options: List[Dict[str, Any]] = []

    for opt in scaled_arena:
        ...
        est_cost = round(opt.estimated_cost, 2)
        if est_cost < min_loss:
            min_loss = est_cost
            best_action = action_id
```

**After (Surgical Fix):** Subordinate financial optimization to physical safety. Assign `disqualified=True` in `arena.py` for any action whose post-action failure probability exceeds `0.35`. Strip the naive `min_loss` loop from `main.py` entirely, binding strictly to the backend's enforced recommendation.

*In `src/decision/arena.py`:*
```python
    # Universal ALARP Safety Lock
    no_action_dq = (no_action_post_risk >= 0.35)
    derate_dq = (derate_post_risk >= 0.35)
    
    if no_action_dq and derate_dq:
        # Lock recommended action to maintenance, bypassing all financial comparison
        rec_action = "maintenance"
```
*In `src/api/main.py`:*
```python
    # Bind directly to the backend's governed action
    best_action = ACTION_ID_MAP.get(str(arena_recommended_action).lower(), str(arena_recommended_action).upper())
```
