'use client';

import React from 'react';
import { Play, Pause, RotateCcw, ShieldCheck, ChevronDown } from 'lucide-react';

export interface RunOption {
  id: string;
  label: string;
  faultType?: string;
}

interface NavbarProps {
  runs: (string | RunOption)[];
  selectedRun: string;
  onSelectRun: (run: string) => void;
  currentStep: number;
  maxStep: number;
  onStepChange: (step: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onReset: () => void;
  healthScore?: number;
  alertState: string;
}

export const Navbar: React.FC<NavbarProps> = ({
  runs,
  selectedRun,
  onSelectRun,
  currentStep,
  maxStep,
  onStepChange,
  isPlaying,
  onTogglePlay,
  onReset,
  alertState,
}) => {
  const getBadgeColor = (state: string) => {
    switch (state) {
      case 'NORMAL':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'WARNING':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'CRITICAL':
        return 'bg-rose-50 text-rose-700 border-rose-200';
      case 'HUMAN_REVIEW':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-white/95 backdrop-blur-md border-b border-slate-200 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand Logo & Name */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-lg overflow-hidden flex items-center justify-center bg-slate-50 border border-slate-200 shadow-inner">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/synapse_logo.png"
                alt="SYNAPSE Logo"
                className="w-8 h-8 object-contain"
              />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xl font-bold tracking-tight text-[#061838]">
                  SYNAPSE
                </span>
                <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  Industrial AI Diagnostic Suite
                </span>
              </div>
              <p className="text-[11px] font-medium text-slate-500 tracking-wide uppercase">
                Autonomous Centrifugal Pump Health & Decision Engine
              </p>
            </div>
          </div>

          {/* Center: Replay Controls & Timeline Scrubber */}
          <div className="hidden md:flex items-center space-x-4 bg-slate-50/80 px-4 py-1.5 rounded-xl border border-slate-200">
            {/* Play/Pause & Reset */}
            <div className="flex items-center space-x-1">
              <button
                onClick={onTogglePlay}
                className={`p-1.5 rounded-lg transition-colors ${
                  isPlaying
                    ? 'bg-amber-100 text-amber-800 hover:bg-amber-200'
                    : 'bg-[#061838] text-white hover:bg-[#0c2759]'
                }`}
                title={isPlaying ? 'Pause Replay' : 'Start Replay'}
              >
                {isPlaying ? <Pause size={15} /> : <Play size={15} />}
              </button>
              <button
                onClick={onReset}
                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 transition-colors"
                title="Reset Timeline to Step 0"
              >
                <RotateCcw size={15} />
              </button>
            </div>

            {/* Timeline Slider */}
            <div className="flex items-center space-x-3 min-w-[260px]">
              <span className="text-xs font-mono font-medium text-slate-500 w-16 text-right">
                T+{currentStep}s
              </span>
              <input
                type="range"
                min="0"
                max={Math.max(1, maxStep - 1)}
                value={currentStep}
                onChange={(e) => onStepChange(parseInt(e.target.value, 10))}
                onInput={(e) => onStepChange(parseInt((e.target as HTMLInputElement).value, 10))}
                className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#061838]"
              />
              <span className="text-xs font-mono font-medium text-slate-400">
                {maxStep}s
              </span>
            </div>
          </div>

          {/* Right Controls: Run Selector & Operational Status */}
          <div className="flex items-center space-x-3">
            {/* Run Selector Dropdown with Fault Scenarios */}
            <div className="relative">
              <select
                value={selectedRun}
                onChange={(e) => onSelectRun(e.target.value)}
                aria-label="Select Telemetry Run"
                className="appearance-none bg-white text-xs font-semibold text-slate-700 pl-3 pr-8 py-1.5 border border-slate-200 rounded-lg shadow-sm hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer max-w-[260px] truncate"
              >
                {runs.map((r) => {
                  const id = typeof r === 'string' ? r : r.id;
                  const label = typeof r === 'string' ? r.toUpperCase() : r.label;
                  return (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  );
                })}
              </select>
              <ChevronDown
                size={14}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
              />
            </div>

            {/* Live Status Badge */}
            <div
              className={`flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold border shadow-xs ${getBadgeColor(
                alertState
              )}`}
            >
              <span className="relative flex h-2 w-2">
                <span
                  className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    alertState === 'NORMAL' ? 'bg-emerald-400' : 'bg-amber-400'
                  }`}
                />
                <span
                  className={`relative inline-flex rounded-full h-2 w-2 ${
                    alertState === 'NORMAL' ? 'bg-emerald-500' : 'bg-amber-500'
                  }`}
                />
              </span>
              <span>{alertState}</span>
            </div>

            {/* Verification Guardrail Badge */}
            <div className="hidden lg:flex items-center space-x-1 px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 text-xs font-medium border border-slate-200">
              <ShieldCheck size={13} className="text-emerald-600" />
              <span>54/54 Tests</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
