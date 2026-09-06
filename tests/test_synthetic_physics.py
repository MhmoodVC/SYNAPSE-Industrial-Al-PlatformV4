import numpy as np
from datetime import datetime, timezone
import random
from data.synthetic import generate_runs

def test_physics_affinity_laws_flow_restriction():
    obs, truth = generate_runs(
        scenarios=["flow_restriction", "normal"],
        points_per_run=100,
        missing_rate=0.0
    )
    res_obs = [o for o, t in zip(obs, truth) if t.fault_type == "flow_restriction" and t.severity > 0.8]
    norm_obs = [o for o, t in zip(obs, truth) if t.fault_type == "normal" and t.severity == 0.0]

    res_press = np.mean([o.pressure for o in res_obs])
    res_flow = np.mean([o.flow for o in res_obs])
    res_curr = np.mean([o.motor_current for o in res_obs])

    norm_press = np.mean([o.pressure for o in norm_obs])
    norm_flow = np.mean([o.flow for o in norm_obs])
    norm_curr = np.mean([o.motor_current for o in norm_obs])

    assert res_press > norm_press, f"Restriction must increase head pressure. Res: {res_press}, Norm: {norm_press}"
    assert res_flow < norm_flow, f"Restriction must decrease flow. Res: {res_flow}, Norm: {norm_flow}"
    assert res_curr < norm_curr, f"Restriction must decrease motor current (affinity). Res: {res_curr}, Norm: {norm_curr}"

def test_physics_cavitation_coupling():
    obs, truth = generate_runs(
        scenarios=["cavitation", "normal"],
        points_per_run=100,
        missing_rate=0.0
    )
    cav_obs = [o for o, t in zip(obs, truth) if t.fault_type == "cavitation" and t.severity > 0.8]
    norm_obs = [o for o, t in zip(obs, truth) if t.fault_type == "normal" and t.severity == 0.0]

    cav_press = np.mean([o.pressure for o in cav_obs])
    cav_vib = np.mean([o.vibration for o in cav_obs])
    norm_press = np.mean([o.pressure for o in norm_obs])
    norm_vib = np.mean([o.vibration for o in norm_obs])

    assert cav_press < norm_press, f"Cavitation must cause suction pressure drop. Cav: {cav_press}, Norm: {norm_press}"
    assert cav_vib > norm_vib + 1.0, f"Cavitation must cause severe vibration spike. Cav: {cav_vib}, Norm: {norm_vib}"

def test_physics_pressure_loss_vs_seal_leakage():
    obs, truth = generate_runs(
        scenarios=["pressure_loss", "seal_leakage", "normal"],
        points_per_run=100,
        missing_rate=0.0
    )
    pl_obs = [o for o, t in zip(obs, truth) if t.fault_type == "pressure_loss" and t.severity > 0.8]
    sl_obs = [o for o, t in zip(obs, truth) if t.fault_type == "seal_leakage" and t.severity > 0.8]
    norm_obs = [o for o, t in zip(obs, truth) if t.fault_type == "normal" and t.severity == 0.0]

    pl_flow = np.mean([o.flow for o in pl_obs])
    sl_flow = np.mean([o.flow for o in sl_obs])
    norm_flow = np.mean([o.flow for o in norm_obs])

    assert pl_flow > norm_flow, f"Downstream pressure loss should increase flow. PL: {pl_flow}, Norm: {norm_flow}"
    assert sl_flow < norm_flow, f"Seal leak should decrease flow. SL: {sl_flow}, Norm: {norm_flow}"

def test_thermodynamic_bounds_and_continuity():
    obs, truth = generate_runs(
        points_per_run=100,
        missing_rate=0.0
    )
    for o in obs:
        if o.pressure is not None: assert o.pressure >= 0, f"Unphysical negative pressure: {o.pressure}"
        if o.flow is not None: assert o.flow >= 0, f"Unphysical negative flow: {o.flow}"
        if o.temperature is not None: assert o.temperature >= 0, f"Unphysical negative temperature: {o.temperature}"
        if o.vibration is not None: assert o.vibration >= 0, f"Unphysical negative vibration: {o.vibration}"
        if o.motor_current is not None: assert o.motor_current >= 0, f"Unphysical negative current: {o.motor_current}"

if __name__ == "__main__":
    test_physics_affinity_laws_flow_restriction()
    test_physics_cavitation_coupling()
    test_physics_pressure_loss_vs_seal_leakage()
    test_thermodynamic_bounds_and_continuity()
    print("All physics and thermodynamic boundary constraints passed successfully.")
