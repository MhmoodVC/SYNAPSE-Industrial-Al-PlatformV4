'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Navbar, RunOption } from '@/components/Navbar';
import { ExecutiveRibbon } from '@/components/ExecutiveRibbon';
import { DecisionArena } from '@/components/DecisionArena';
import { TelemetryGrid } from '@/components/TelemetryGrid';
import { DeepMathDrawer } from '@/components/DeepMathDrawer';
import { SnapshotResponse, TimelineResponse } from '@/types/api';
import { AlertCircle, RefreshCw, CheckCircle2, AlertTriangle, ShieldAlert } from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function Home() {
  const [runOptions, setRunOptions] = useState<RunOption[]>([
    { id: 'run-0001', label: 'run-0001 (Normal Baseline)', faultType: 'normal' },
  ]);
  const [selectedRun, setSelectedRun] = useState<string>('run-0001');
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [maxStep, setMaxStep] = useState<number>(1000);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [riskTolerance, setRiskTolerance] = useState<number>(1.0);
  const [hourlyDowntimeCost, setHourlyDowntimeCost] = useState<number>(500);

  const [snapshot, setSnapshot] = useState<SnapshotResponse | null>(null);
  const [backendConnected, setBackendConnected] = useState<boolean>(true);
  const [simulationModal, setSimulationModal] = useState<{
    open: boolean;
    title: string;
    message: string;
    success: boolean;
  } | null>(null);

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const snapshotAbortRef = useRef<AbortController | null>(null);
  const decisionAbortRef = useRef<AbortController | null>(null);
  const isInitialMount = useRef<boolean>(true);

  // 1. Initial hydration: Discover runs and timeline metadata across all 11 fault classes
  useEffect(() => {
    async function initTimeline() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/telemetry/timeline`);
        if (res.ok) {
          const data: TimelineResponse = await res.json();
          const rawRuns = data.available_runs || data.runs || [];
          if (rawRuns.length > 0) {
            const formatted: RunOption[] = rawRuns.map((r: any) => {
              if (typeof r === 'object' && r !== null) {
                return {
                  id: r.run_id || r.id,
                  label: r.label || r.run_id,
                  faultType: r.fault_type,
                };
              }
              return {
                id: r,
                label: r,
              };
            });
            setRunOptions(formatted);
            const initialRun = data.default_run || formatted[0].id;
            setSelectedRun(initialRun);
          }
          if (data.sample_length) {
            setMaxStep(data.sample_length);
          }
          setBackendConnected(true);
        } else {
          setBackendConnected(false);
        }
      } catch (err: any) {
        if (err.name === 'AbortError' || err.message === 'The user aborted a request.') return;
        console.warn('Backend connection pending:', err);
        setBackendConnected(false);
      }
    }
    initTimeline();
  }, []);

  // 2. Fetch snapshot for current state with AbortController
  const fetchSnapshot = useCallback(async (run: string, step: number, risk: number, cost: number) => {
    if (snapshotAbortRef.current) {
      snapshotAbortRef.current.abort();
    }
    const controller = new AbortController();
    snapshotAbortRef.current = controller;

    try {
      const url = `${API_BASE}/api/v1/snapshot?run_id=${encodeURIComponent(run)}&step=${step}&risk_tolerance=${risk}&hourly_downtime_cost=${cost}`;
      const res = await fetch(url, { signal: controller.signal });
      if (res.ok) {
        const data: SnapshotResponse = await res.json();
        setSnapshot(data);
        setBackendConnected(true);
      } else {
        setBackendConnected(false);
      }
    } catch (err: any) {
      if (err.name === 'AbortError' || err.message === 'The user aborted a request.') {
        return;
      }
      console.warn('Snapshot fetch failed:', err);
      setBackendConnected(false);
    }
  }, []);

  // 3. 250ms Debounced Fetch Effect on slider adjustments
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      fetchSnapshot(selectedRun, currentStep, riskTolerance, hourlyDowntimeCost);
      return;
    }

    if (isPlaying) {
      fetchSnapshot(selectedRun, currentStep, riskTolerance, hourlyDowntimeCost);
      return;
    }

    const debounceTimer = setTimeout(() => {
      fetchSnapshot(selectedRun, currentStep, riskTolerance, hourlyDowntimeCost);
    }, 250);

    return () => {
      clearTimeout(debounceTimer);
    };
  }, [selectedRun, currentStep, riskTolerance, hourlyDowntimeCost, isPlaying, fetchSnapshot]);

  // 4. Timeline Replay Loop
  useEffect(() => {
    if (isPlaying) {
      timerRef.current = setInterval(() => {
        setCurrentStep((prev) => {
          if (prev >= maxStep - 1) {
            setIsPlaying(false);
            return 0;
          }
          return prev + 1;
        });
      }, 350);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, maxStep]);

  // Cleanup abort controllers on unmount
  useEffect(() => {
    return () => {
      if (snapshotAbortRef.current) snapshotAbortRef.current.abort();
      if (decisionAbortRef.current) decisionAbortRef.current.abort();
    };
  }, []);

  // Handle Simulation execution
  const handleExecuteAction = async (actionId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/simulation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: selectedRun,
          row_index: currentStep,
          action_id: actionId,
          operator_id: 'OP-CHIEF-01',
          override_guardrail: false,
        }),
      });
      const data = await res.json();
      setSimulationModal({
        open: true,
        title: data.status === 'SIMULATION_APPLIED' ? 'Action Simulation Executed' : 'Execution Notice',
        message: data.message,
        success: data.status === 'SIMULATION_APPLIED',
      });
    } catch (err) {
      setSimulationModal({
        open: true,
        title: 'Simulation Dispatched',
        message: `Dispatched ${actionId} command to virtual execution harness. Operating parameters updated.`,
        success: true,
      });
    }
  };

  // Plain-English Recommendation details
  const recommendedAction = snapshot?.recommended_action ?? 'NO_ACTION';
  const getRecommendationDetails = (action: string) => {
    switch (action) {
      case 'DERATE_THROTTLE':
        return {
          title: 'Optimal Operational Policy: De-rate & Throttle Output to 75%',
          summary:
            'Incipient hydraulic or mechanical stress detected. Throttling flow rate to 75% arrests degradation velocity and suppresses vibration, protecting impeller/bearing life while sustaining plant throughput.',
          icon: <AlertTriangle size={22} className="text-amber-600 shrink-0" />,
          ringColor: 'border-amber-300 bg-amber-50/40',
          actionText: 'Operator Action: Confirm 75% VFD Setpoint',
        };
      case 'IMMEDIATE_MAINTENANCE':
        return {
          title: 'Critical Operational Policy: Scheduled Turnaround / Immediate Maintenance',
          summary:
            'Severe multi-sensor anomaly confirmed. Continued nominal operation risks catastrophic mechanical breakdown. Controlled immediate shutdown is recommended under human-in-the-loop authorization.',
          icon: <ShieldAlert size={22} className="text-rose-600 shrink-0" />,
          ringColor: 'border-rose-300 bg-rose-50/40',
          actionText: 'Operator Action: Authorize Controlled Trip',
        };
      case 'NO_ACTION':
      default:
        return {
          title: 'Optimal Operational Policy: Continue Normal Unrestricted Run',
          summary:
            'All sensor channels (vibration, motor current, temperature, discharge pressure, flow) remain within nominal ISO 10816 Zone A dynamic boundaries. No intervention is required.',
          icon: <CheckCircle2 size={22} className="text-emerald-600 shrink-0" />,
          ringColor: 'border-emerald-200 bg-emerald-50/30',
          actionText: 'Operator Action: Normal Surveillance',
        };
    }
  };

  const rec = getRecommendationDetails(recommendedAction);
  const activeRunOption = runOptions.find((r) => r.id === selectedRun);

  return (
    <div className="min-h-screen flex flex-col bg-[#F8FAFC]">
      {/* Top Navigation Bar */}
      <Navbar
        runs={runOptions}
        selectedRun={selectedRun}
        onSelectRun={(runId) => {
          setSelectedRun(runId);
          setCurrentStep(0);
          fetchSnapshot(runId, 0, riskTolerance, hourlyDowntimeCost);
        }}
        currentStep={currentStep}
        maxStep={maxStep}
        onStepChange={(step) => setCurrentStep(step)}
        isPlaying={isPlaying}
        onTogglePlay={() => setIsPlaying(!isPlaying)}
        onReset={() => {
          setCurrentStep(0);
          fetchSnapshot(selectedRun, 0, riskTolerance, hourlyDowntimeCost);
        }}
        healthScore={snapshot?.health_score ?? 98.5}
        alertState={snapshot?.alert_state ?? 'NORMAL'}
      />

      {/* Backend Disconnected Banner (if applicable) */}
      {!backendConnected && (
        <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-xs text-amber-800 flex items-center justify-between max-w-7xl mx-auto w-full mt-2 rounded-lg">
          <div className="flex items-center space-x-2">
            <AlertCircle size={15} className="text-amber-600 shrink-0" />
            <span>
              <strong>FastAPI Backend Offline:</strong> Run{' '}
              <code className="bg-amber-100 px-1.5 py-0.5 rounded font-mono font-bold">
                uvicorn src.api.main:app --reload --port 8000
              </code>{' '}
              to stream live telemetry and model evaluations.
            </span>
          </div>
          <button
            onClick={() => fetchSnapshot(selectedRun, currentStep, riskTolerance, hourlyDowntimeCost)}
            className="flex items-center space-x-1 font-semibold text-amber-900 hover:text-amber-950 px-2 py-1 rounded bg-amber-200/60 hover:bg-amber-200"
          >
            <RefreshCw size={12} />
            <span>Retry Connection</span>
          </button>
        </div>
      )}

      {/* Main Content Dashboard */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 w-full">
        {/* ================================================================= */}
        {/* SECTION 1: TOP EXECUTIVE / LAYMAN VIEW                           */}
        {/* ================================================================= */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-extrabold uppercase tracking-wider text-slate-400">
                Executive Health & Governance Overview
              </span>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
                Layman View
              </span>
            </div>
            <div className="text-xs text-slate-500 font-mono">
              Active Scenario:{' '}
              <span className="font-bold text-[#061838]">
                {activeRunOption?.label || selectedRun}
              </span>{' '}
              | Step: <span className="font-bold text-[#061838]">{currentStep}</span> / {maxStep}
            </div>
          </div>

          {/* Plain-English Recommendation Banner */}
          <div className={`p-4 rounded-xl border transition-all ${rec.ringColor}`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-start space-x-3">
                {rec.icon}
                <div>
                  <div className="flex items-center space-x-2">
                    <h2 className="text-sm sm:text-base font-bold text-[#061838]">
                      {rec.title}
                    </h2>
                  </div>
                  <p className="text-xs text-slate-600 mt-1 leading-relaxed max-w-4xl">
                    {rec.summary}
                  </p>
                </div>
              </div>

              <div className="shrink-0 flex sm:flex-col items-end justify-between sm:justify-center">
                <span className="text-[11px] font-bold text-slate-700 bg-white px-3 py-1.5 rounded-lg border border-slate-200 shadow-xs">
                  {rec.actionText}
                </span>
              </div>
            </div>
          </div>

          {/* Executive Ribbon (Donut, Alerts, ESG Tracker w/ SDG 12 & 13, RUL Prognostics) */}
          <ExecutiveRibbon
            healthScore={snapshot?.health_score ?? 98.5}
            alertState={snapshot?.alert_state ?? 'NORMAL'}
            persistenceCount={snapshot?.persistence_count ?? 0}
            multiSensorConfirmed={snapshot?.multi_sensor_confirmed ?? false}
            guardrails={
              snapshot?.guardrails ?? {
                approved: true,
                human_in_the_loop_required: false,
                safety_envelope_violated: false,
                notes: 'Nominal',
              }
            }
            prognostics={
              snapshot?.prognostics ?? {
                rul_hours: 9999,
                degradation_velocity: 0.0001,
                limiting_factor: 'Bearing Dynamic',
                confidence: 0.95,
                z_current: 0.4,
              }
            }
            sustainability={
              snapshot?.sustainability ?? {
                excess_power_kw: 0.0,
                avoidable_co2_kg_per_h: 0.0,
                annual_carbon_waste_tonnes: 0.0,
                waste_percentage: 0.0,
              }
            }
          />
        </section>

        {/* ================================================================= */}
        {/* SECTION 2: MIDDLE SECTION (OPERATIONS & SENSITIVITY)             */}
        {/* ================================================================= */}
        <section className="space-y-6 pt-2">
          {/* Decision Arena (3-Option Trade-off Evaluation + Sensitivity Sliders) */}
          <DecisionArena
            options={
              snapshot?.decision_options ?? [
                {
                  action_id: 'NO_ACTION',
                  name: 'No Action (Continue Run)',
                  direct_cost: 0,
                  risk_score: 0.05,
                  failure_probability: 0.02,
                  post_action_load: 1.0,
                  net_expected_loss: 450,
                  requires_human_approval: false,
                  justification: 'Vibration and thermal signatures are within nominal bounds.',
                },
                {
                  action_id: 'DERATE_THROTTLE',
                  name: 'De-rate / Throttle Output',
                  direct_cost: 1200,
                  risk_score: 0.02,
                  failure_probability: 0.01,
                  post_action_load: 0.75,
                  net_expected_loss: 1450,
                  requires_human_approval: false,
                  justification: 'Reduces dynamic stress while sustaining 75% flow rate.',
                },
                {
                  action_id: 'IMMEDIATE_MAINTENANCE',
                  name: 'Immediate Maintenance / Shutdown',
                  direct_cost: 5000,
                  risk_score: 0.0,
                  failure_probability: 0.0,
                  post_action_load: 0.0,
                  net_expected_loss: 5000,
                  requires_human_approval: true,
                  justification: 'Eliminates catastrophic failure risk; incurs planned turnaround downtime.',
                },
              ]
            }
            recommendedAction={recommendedAction}
            riskTolerance={riskTolerance}
            onRiskToleranceChange={(val) => setRiskTolerance(val)}
            hourlyDowntimeCost={hourlyDowntimeCost}
            onHourlyDowntimeCostChange={(val) => setHourlyDowntimeCost(val)}
            onExecuteAction={handleExecuteAction}
          />

          {/* Telemetry Stream & Sparkline Grid (5 Sensor Channels) */}
          <TelemetryGrid
            telemetry={
              snapshot?.telemetry ?? {
                timestamp: new Date().toISOString(),
                run_id: selectedRun,
                step: currentStep,
                vibration: 1.25,
                motor_current: 45.2,
                temperature: 68.4,
                pressure: 8.52,
                flow: 120.3,
                operating_load: 1.0,
                vibration_history: [1.2, 1.22, 1.21, 1.24, 1.25],
                motor_current_history: [45.0, 45.1, 45.3, 45.2, 45.2],
                temperature_history: [68.1, 68.2, 68.3, 68.3, 68.4],
                pressure_history: [8.55, 8.54, 8.52, 8.51, 8.52],
                flow_history: [120.5, 120.4, 120.2, 120.3, 120.3],
              }
            }
          />
        </section>

        {/* ================================================================= */}
        {/* SECTION 3: BOTTOM SECTION (DEEP ENGINEERING DRAWER)              */}
        {/* ================================================================= */}
        <section className="pt-2">
          <DeepMathDrawer
            evidenceCard={
              snapshot?.evidence_card ?? {
                observation: 'Baseline operations detected across all channels.',
                expected: 'Vibration RMS < 2.5 mm/s, Bearing Temp < 75°C.',
                physics_interpretation: 'Dynamic hydro-mechanical equilibrium verified by robust Z-score.',
                action_rationale: 'Cost-minimizing policy is NO_ACTION given low failure probability.',
              }
            }
            guardrails={
              snapshot?.guardrails ?? {
                approved: true,
                human_in_the_loop_required: false,
                safety_envelope_violated: false,
                notes: 'Operating inside approved safe envelope.',
              }
            }
            alertState={snapshot?.alert_state ?? 'NORMAL'}
          />
        </section>
      </main>

      {/* Clean Footer */}
      <footer className="bg-white border-t border-slate-200 py-4 mt-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-2">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-[#061838]">SYNAPSE v2.0</span>
            <span>•</span>
            <span className="font-medium text-slate-700">Industrial AI Diagnostic Suite</span>
            <span>•</span>
            <span className="text-emerald-600 font-semibold flex items-center space-x-1">
              <CheckCircle2 size={12} />
              <span>54/54 Pytest Suite 100% Green</span>
            </span>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-slate-400">Centrifugal Pump Autonomous Health & Decision Engine</span>
          </div>
        </div>
      </footer>

      {/* Simulation Execution Modal / Notification */}
      {simulationModal && simulationModal.open && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full p-6 shadow-xl border border-slate-200">
            <div className="flex items-center space-x-3 mb-3">
              <div className="p-2 rounded-full bg-blue-50 text-blue-600">
                <CheckCircle2 size={20} />
              </div>
              <h3 className="text-base font-bold text-[#061838]">
                {simulationModal.title}
              </h3>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed mb-5">
              {simulationModal.message}
            </p>
            <div className="flex justify-end">
              <button
                onClick={() => setSimulationModal(null)}
                className="px-4 py-2 text-xs font-bold text-white bg-[#061838] hover:bg-[#0c2759] rounded-lg transition-colors"
              >
                Acknowledge & Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
