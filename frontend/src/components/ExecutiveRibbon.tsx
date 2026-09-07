'use client';

import React from 'react';
import { Leaf, Clock, UserCheck, Activity } from 'lucide-react';
import { PrognosticsResult, SustainabilityMetrics, GuardrailStatus } from '@/types/api';

interface ExecutiveRibbonProps {
  healthScore: number;
  alertState: string;
  persistenceCount: number;
  multiSensorConfirmed: boolean;
  guardrails: GuardrailStatus;
  prognostics: PrognosticsResult;
  sustainability: SustainabilityMetrics;
}

export const ExecutiveRibbon: React.FC<ExecutiveRibbonProps> = ({
  healthScore,
  alertState,
  persistenceCount,
  multiSensorConfirmed,
  guardrails,
  prognostics,
  sustainability,
}) => {
  // SVG Donut calculation
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const normalizedScore = Math.max(0, Math.min(100, healthScore));
  const strokeDashoffset = circumference - (normalizedScore / 100) * circumference;

  const getHealthColor = (score: number) => {
    if (score >= 80) return { stroke: '#10B981', text: 'text-emerald-600', bg: 'bg-emerald-50' };
    if (score >= 50) return { stroke: '#F59E0B', text: 'text-amber-600', bg: 'bg-amber-50' };
    return { stroke: '#EF4444', text: 'text-rose-600', bg: 'bg-rose-50' };
  };

  const healthColor = getHealthColor(healthScore);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* 1. Asset Health Score Ring */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-slate-300 transition-all">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Asset Health Index
            </span>
            <div className="flex items-baseline space-x-1 mt-1">
              <span className={`text-3xl font-extrabold tracking-tight ${healthColor.text}`}>
                {healthScore.toFixed(1)}
              </span>
              <span className="text-sm font-medium text-slate-400">/ 100</span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              {healthScore >= 80 ? 'Nominal Dynamic Range' : healthScore >= 50 ? 'Developing Degradation' : 'Imminent Hazard'}
            </p>
          </div>

          <div className="relative flex items-center justify-center w-20 h-20">
            <svg className="w-20 h-20 transform -rotate-90">
              <circle
                cx="40"
                cy="40"
                r={radius}
                stroke="#F1F5F9"
                strokeWidth="7"
                fill="none"
              />
              <circle
                cx="40"
                cy="40"
                r={radius}
                stroke={healthColor.stroke}
                strokeWidth="7"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                fill="none"
                className="transition-all duration-700 ease-out"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center text-center">
              <Activity size={16} className={healthColor.text} />
            </div>
          </div>
        </div>
      </div>

      {/* 2. Anomaly & Alert Engine Status */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Alert Persistence Filter
            </span>
            {guardrails?.human_in_the_loop_required && (
              <span className="flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800" title="Human In The Loop Gate Active">
                <UserCheck size={11} />
                <span>HITL</span>
              </span>
            )}
          </div>
          <div className="flex items-center space-x-2 mt-2">
            <span
              className={`px-2.5 py-1 rounded-md text-sm font-bold border ${
                alertState === 'NORMAL'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : alertState === 'WARNING'
                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                  : 'bg-rose-50 text-rose-700 border-rose-200'
              }`}
            >
              {alertState}
            </span>
            <div className="text-xs text-slate-600">
              <span className="font-semibold text-slate-800">{persistenceCount} / 5</span> consecutive samples
            </div>
          </div>
        </div>

        <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Multi-Sensor Confirmation:</span>
          <span className={`font-semibold ${multiSensorConfirmed ? 'text-rose-600' : 'text-slate-400'}`}>
            {multiSensorConfirmed ? 'POSITIVE (Confirmed)' : 'NEGATIVE (Divergent)'}
          </span>
        </div>
      </div>

      {/* 3. Eco-Efficiency & Carbon Footprint (Tagged with SDG 12 & SDG 13) */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Eco-Efficiency Impact
            </span>
            <div className="flex items-center space-x-1">
              <span className="px-1.5 py-0.5 rounded text-[9px] font-extrabold bg-amber-100 text-amber-800 border border-amber-200" title="UN SDG 12: Responsible Consumption & Production">
                SDG 12
              </span>
              <span className="px-1.5 py-0.5 rounded text-[9px] font-extrabold bg-emerald-100 text-emerald-800 border border-emerald-200" title="UN SDG 13: Climate Action">
                SDG 13
              </span>
            </div>
          </div>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-3xl font-extrabold text-[#061838]">
              {(sustainability?.excess_power_kw ?? sustainability?.excess_kw)?.toFixed(1) ?? '0.0'}
            </span>
            <span className="text-sm font-medium text-slate-400">kW excess</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1">
            Parasitic hydraulic & friction load
          </p>
        </div>

        <div className="mt-3 pt-2 border-t border-slate-100 grid grid-cols-2 gap-2 text-xs">
          <div>
            <span className="text-slate-400 block text-[10px] uppercase font-medium">CO₂ Waste</span>
            <span className="font-semibold text-slate-700">
              {(sustainability?.avoidable_co2_kg_per_h ?? sustainability?.co2_kg_hr ?? sustainability?.co2_waste_kg_h)?.toFixed(2) ?? '0.00'} kg/h
            </span>
          </div>
          <div>
            <span className="text-slate-400 block text-[10px] uppercase font-medium">Annual Penalty</span>
            <span className="font-semibold text-amber-700">
              {(sustainability?.annual_carbon_waste_tonnes ?? sustainability?.annual_co2_tonnes ?? sustainability?.annual_penalty_t)?.toFixed(1) ?? '0.0'} t/yr
            </span>
          </div>
        </div>
      </div>

      {/* 4. Physics RUL Prognostics */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Prognostics (RUL)
            </span>
            <span className="flex items-center space-x-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-800">
              <Clock size={11} />
              <span>Physics</span>
            </span>
          </div>
          <div className="flex items-baseline space-x-1 mt-1">
            <span className="text-3xl font-extrabold text-[#061838]">
              {prognostics?.rul_hours != null && prognostics.rul_hours < 9999
                ? prognostics.rul_hours.toFixed(0)
                : '10,000+'}
            </span>
            <span className="text-sm font-medium text-slate-400">hours</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 truncate" title={prognostics?.limiting_factor}>
            Limiting: <span className="font-medium text-slate-700">{prognostics?.limiting_factor || 'Dynamic Envelope'}</span>
          </p>
        </div>

        <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <span>Degradation rate (dz/dt):</span>
          <span className="font-mono font-bold text-slate-700">
            {prognostics?.degradation_velocity != null
              ? (prognostics.degradation_velocity * 1000).toFixed(2) + ' mZ/s'
              : '0.00 mZ/s'}
          </span>
        </div>
      </div>
    </div>
  );
};
