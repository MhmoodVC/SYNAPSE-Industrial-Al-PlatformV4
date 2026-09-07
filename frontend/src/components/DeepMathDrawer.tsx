'use client';

import React, { useState, useEffect } from 'react';
import {
  ChevronDown,
  ChevronUp,
  Cpu,
  ShieldCheck,
  CheckCircle2,
  FileText,
  Scale,
  Award,
  BookOpen,
  Globe,
  Database,
  Layers,
} from 'lucide-react';
import { EvidencePart, GuardrailStatus } from '@/types/api';
import empiricalMetricsDefault from '@/data/evaluation_metrics.json';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface DeepMathDrawerProps {
  evidenceCard: EvidencePart;
  guardrails: GuardrailStatus;
  alertState: string;
  metrics?: any;
}

export const DeepMathDrawer: React.FC<DeepMathDrawerProps> = ({
  evidenceCard,
  guardrails,
  alertState,
  metrics: propMetrics,
}) => {
  const [isOpen, setIsOpen] = useState(true);
  const [metrics, setMetrics] = useState(propMetrics || empiricalMetricsDefault);

  useEffect(() => {
    if (propMetrics) {
      setMetrics(propMetrics);
      return;
    }
    async function fetchEmpiricalMetrics() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/models/metrics`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.full_trajectory) {
            setMetrics(data);
          }
        }
      } catch (err) {
        // Fall back to verified local artifact
      }
    }
    fetchEmpiricalMetrics();
  }, []);

  const full = metrics.full_trajectory;
  const active = metrics.active_fault_phase;
  const anom = metrics.anomaly_detector;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden transition-all">
      {/* Drawer Header Toggle */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-5 py-4 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white hover:bg-slate-100/70 border-b border-slate-200 transition-colors"
      >
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-[#061838] text-white">
            <Cpu size={18} />
          </div>
          <div className="text-left">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-bold text-[#061838]">
                🔬 Engineering Deep-Dive, AI Verification & ISO Compliance
              </span>
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800">
                Ground-Truth Verified
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Empirical ML benchmarks, ISO 10816/20816 vibration taxonomy, UN SDGs & mathematical proofs
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 text-slate-400">
          <span className="text-xs font-semibold">{isOpen ? 'Collapse Drawer' : 'Expand Drawer'}</span>
          {isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </button>

      {/* Drawer Body */}
      {isOpen && (
        <div className="p-5 space-y-6">
          {/* Section 1: AI Model Verification & Empirical Ground-Truth Benchmarks */}
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2 border-b border-slate-100 gap-2 mb-3">
              <div className="flex items-center space-x-2">
                <Award size={16} className="text-blue-600" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Empirical Model Verification & Ground-Truth Test Benchmarks
                </h4>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-[10px] font-mono font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                  22 Held-out Test Runs (22,000 Obs)
                </span>
                <span className="text-[10px] font-mono font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                  Zero Causal Leakage
                </span>
              </div>
            </div>

            {/* Subsection 1: Primary Operational Performance — Active Fault Phase */}
            <div className="p-4 bg-gradient-to-br from-emerald-50/70 via-white to-slate-50 rounded-xl border border-emerald-200/90 shadow-sm space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span className="text-xs font-bold uppercase tracking-wide text-emerald-950">
                      Primary Operational Metric: Active Fault Phase Performance
                    </span>
                    <span className="text-[10px] font-mono font-bold text-emerald-800 bg-emerald-100/80 px-2 py-0.5 rounded-full border border-emerald-300">
                      Ground-Truth Verified
                    </span>
                  </div>
                  <p className="text-[11px] text-emerald-800/90 mt-0.5 font-medium">
                    Evaluated during active physical degradation (stage &gt; 0.05) across 22 held-out test runs.
                  </p>
                </div>
                <span className="text-[10px] font-mono text-slate-500 self-start sm:self-center">
                  Active Samples: N={active.observations_count.toLocaleString()}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
                <div className="p-3.5 bg-white rounded-lg border border-emerald-200/90 shadow-[0_1px_3px_rgba(16,185,129,0.08)]">
                  <span className="text-[10px] uppercase font-bold text-emerald-800 block">
                    Fault Detection Recall
                  </span>
                  <div className="text-2xl sm:text-3xl font-black text-emerald-700 mt-1 tracking-tight">
                    {active.fault_detection_recall_percent?.toFixed(1) || active.weighted_recall_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono block mt-1">
                    exact: {(active.fault_detection_recall || active.weighted_recall || 0).toFixed(4)}
                  </span>
                </div>

                <div className="p-3.5 bg-white rounded-lg border border-emerald-200/90 shadow-[0_1px_3px_rgba(16,185,129,0.08)]">
                  <span className="text-[10px] uppercase font-bold text-emerald-800 block">
                    Diagnostic Precision
                  </span>
                  <div className="text-2xl sm:text-3xl font-black text-emerald-700 mt-1 tracking-tight">
                    {active.diagnostic_precision_percent?.toFixed(1) || active.weighted_precision_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono block mt-1">
                    exact: {(active.diagnostic_precision || active.weighted_precision || 0).toFixed(4)}
                  </span>
                </div>

                <div className="p-3.5 bg-white rounded-lg border border-emerald-200/90 shadow-[0_1px_3px_rgba(16,185,129,0.08)]">
                  <span className="text-[10px] uppercase font-bold text-emerald-800 block">
                    Active Phase Accuracy
                  </span>
                  <div className="text-2xl sm:text-3xl font-black text-emerald-700 mt-1 tracking-tight">
                    {active.accuracy_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono block mt-1">
                    exact: {(active.accuracy || 0).toFixed(4)}
                  </span>
                </div>

                <div className="p-3.5 bg-white rounded-lg border border-emerald-200/90 shadow-[0_1px_3px_rgba(16,185,129,0.08)]">
                  <span className="text-[10px] uppercase font-bold text-emerald-800 block">
                    Harmonic F1-Score
                  </span>
                  <div className="text-2xl sm:text-3xl font-black text-emerald-700 mt-1 tracking-tight">
                    {active.harmonic_f1_percent?.toFixed(1) || active.weighted_f1_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono block mt-1">
                    exact: {(active.harmonic_f1 || active.weighted_f1 || 0).toFixed(4)}
                  </span>
                </div>
              </div>
            </div>

            {/* Subsection 2: Secondary Diagnostic Context — Full-Trajectory Evaluation */}
            <div className="mt-4 p-4 bg-slate-50/80 rounded-xl border border-slate-200 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wide text-slate-700">
                    Secondary Diagnostic Context: Full-Trajectory Evaluation
                  </span>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    End-to-end evaluation across entire 1,000-sample test runs (N={metrics.total_test_observations.toLocaleString()})
                  </p>
                </div>
                <span className="text-[10px] font-mono text-slate-400">
                  Classifier: {metrics?.model ?? 'HierarchicalPipeline(HistGradientBoosting+ExtraTrees)'}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Pre-Fault Normal Specificity
                  </span>
                  <div className="text-2xl font-black text-blue-700 mt-0.5">
                    {full.normal_specificity_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-500 font-medium block mt-1 leading-snug">
                    Correctly recognizes healthy state prior to fault onset
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono block mt-0.5">
                    exact: {(full.normal_specificity || 0).toFixed(4)}
                  </span>
                </div>

                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Point-wise Overall Accuracy
                  </span>
                  <div className="text-2xl font-black text-[#061838] mt-0.5">
                    {full.accuracy_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-500 font-medium block mt-1 leading-snug">
                    Reflects healthy lead-in steps labeled under run-level fault IDs
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono block mt-0.5">
                    exact: {(full.accuracy || 0).toFixed(4)}
                  </span>
                </div>

                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Macro Precision
                  </span>
                  <div className="text-2xl font-black text-indigo-700 mt-0.5">
                    {full.macro_precision_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-500 font-medium block mt-1 leading-snug">
                    Unweighted mean precision across all 11 fault classes
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono block mt-0.5">
                    exact: {(full.macro_precision || 0).toFixed(4)}
                  </span>
                </div>

                <div className="p-3 bg-white rounded-lg border border-slate-200">
                  <span className="text-[10px] uppercase font-bold text-slate-500 block">
                    Macro F1-Score
                  </span>
                  <div className="text-2xl font-black text-purple-700 mt-0.5">
                    {full.macro_f1_percent?.toFixed(1) || '0.0'}%
                  </div>
                  <span className="text-[10px] text-slate-500 font-medium block mt-1 leading-snug">
                    Unweighted harmonic mean across all 11 fault categories
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono block mt-0.5">
                    exact: {(full.macro_f1 || 0).toFixed(4)}
                  </span>
                </div>
              </div>

              {/* Engineering Note Callout */}
              <div className="p-2.5 rounded-lg bg-blue-50/70 border border-blue-200 text-xs text-blue-900 flex items-start space-x-2">
                <FileText size={15} className="text-blue-600 shrink-0 mt-0.5" />
                <div className="leading-relaxed">
                  <strong className="font-semibold">Engineering Note:</strong> Synthetic runs include an initial healthy lead-in (~350s). The model correctly maintains a &apos;normal&apos; prediction during baseline operation rather than generating false early alarms.
                </div>
              </div>
            </div>

          </div>

          {/* Section 4: Mathematical Formulations & Causal Proofs */}
          <div className="pt-5 border-t border-slate-200">
            <div className="flex items-center space-x-2 mb-3">
              <Scale size={15} className="text-purple-600" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Rigorous Mathematical Formulations
              </h4>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 font-mono text-xs">
                <div className="text-[11px] font-sans font-bold text-slate-700 mb-1">
                  Robust Z-Score Normalization (Median & MAD)
                </div>
                <div className="p-2.5 bg-white rounded border border-slate-200 text-slate-800 text-center font-serif text-sm">
                  z_i = ( x_i - median(x_b) ) / ( 1.4826 · MAD(x_b) )
                </div>
                <p className="text-[11px] font-sans text-slate-500 mt-2">
                  Invariant to heavy-tailed sensor outliers and asymmetric degradation spikes.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 font-mono text-xs">
                <div className="text-[11px] font-sans font-bold text-slate-700 mb-1">
                  Parasitic Power & Avoidable Carbon Waste
                </div>
                <div className="p-2.5 bg-white rounded border border-slate-200 text-slate-800 text-center font-serif text-sm">
                  P_excess = max(0, P_actual - P_nominal(load)) | CO2_waste = P_excess · EF_grid
                </div>
                <p className="text-[11px] font-sans text-slate-500 mt-2">
                  Quantifies financial & ESG losses from hydraulic recirculation and mechanical drag.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 font-mono text-xs">
                <div className="text-[11px] font-sans font-bold text-slate-700 mb-1">
                  First-Order Prognostics Velocity & Remaining Useful Life
                </div>
                <div className="p-2.5 bg-white rounded border border-slate-200 text-slate-800 text-center font-serif text-sm">
                  dz/dt = Δz / Δt  ==&gt;  RUL = ( z_crit - z(t) ) / ( dz/dt )
                </div>
                <p className="text-[11px] font-sans text-slate-500 mt-2">
                  Physics-constrained linear extrapolation preventing catastrophic over-estimation.
                </p>
              </div>

              <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 font-mono text-xs">
                <div className="text-[11px] font-sans font-bold text-slate-700 mb-1">
                  Bayesian Action Expected Loss (Decision Arena)
                </div>
                <div className="p-2.5 bg-white rounded border border-slate-200 text-slate-800 text-center font-serif text-sm">
                  L(a) = C_direct(a) + P_f(a) · C_failure(C_down) · α
                </div>
                <p className="text-[11px] font-sans text-slate-500 mt-2">
                  Scales operational downtime costs by plant risk tolerance factor α.
                </p>
              </div>
            </div>
          </div>

          {/* Section 5: Safety Guardrail Matrix */}
          <div className="pt-5 border-t border-slate-200">
            <div className="flex items-center space-x-2 mb-3">
              <ShieldCheck size={15} className="text-emerald-600" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                Safety Guardrails & Regulatory Boundaries
              </h4>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-3 bg-emerald-50/50 border border-emerald-200 rounded-lg flex items-center space-x-2">
                <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                <div>
                  <span className="font-bold text-emerald-900 block">ISO 10816-3 Compliant</span>
                  <span className="text-[11px] text-emerald-700">Vibration zone limits enforced</span>
                </div>
              </div>

              <div className="p-3 bg-blue-50/50 border border-blue-200 rounded-lg flex items-center space-x-2">
                <CheckCircle2 size={16} className="text-blue-600 shrink-0" />
                <div>
                  <span className="font-bold text-blue-900 block">Mandatory Operator HITL Gate</span>
                  <span className="text-[11px] text-blue-700">Required for critical shutdowns</span>
                </div>
              </div>

              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center space-x-2">
                <CheckCircle2 size={16} className="text-slate-600 shrink-0" />
                <div>
                  <span className="font-bold text-slate-900 block">Persistence Window Filter</span>
                  <span className="text-[11px] text-slate-600">Suppresses transient false alarms</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
