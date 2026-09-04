'use client';

import React, { useState, useMemo } from 'react';
import { AlertCircle, Wrench, Gauge, Sliders, ArrowRight, CheckCircle2 } from 'lucide-react';
import { DecisionOption } from '@/types/api';

interface DecisionArenaProps {
  options: DecisionOption[];
  recommendedAction: string;
  riskTolerance: number;
  onRiskToleranceChange: (val: number) => void;
  hourlyDowntimeCost: number;
  onHourlyDowntimeCostChange: (val: number) => void;
  onExecuteAction: (actionId: string) => void;
  isExecuting?: boolean;
}

export const DecisionArena: React.FC<DecisionArenaProps> = ({
  options,
  recommendedAction,
  riskTolerance,
  onRiskToleranceChange,
  hourlyDowntimeCost,
  onHourlyDowntimeCostChange,
  onExecuteAction,
  isExecuting = false,
}) => {
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null);

  // Instant local sensitivity scaling during active slider drag (60fps smooth feedback)
  const displayOptions = useMemo(() => {
    if (!options || options.length === 0) return [];
    const downtimeScale = Math.max(0.2, hourlyDowntimeCost / 500.0);
    const toleranceScale = Math.max(0.1, Math.min(3.0, riskTolerance));

    return options.map((opt) => {
      const directCost = opt.direct_cost || 0;
      const baseNetLoss = opt.net_expected_loss ?? directCost;
      const failureCostComponent = Math.max(0, baseNetLoss - directCost);
      const adjustedLoss = Math.round(directCost + failureCostComponent * downtimeScale * toleranceScale);
      return {
        ...opt,
        net_expected_loss: adjustedLoss,
      };
    });
  }, [options, riskTolerance, hourlyDowntimeCost]);

  // Dynamically calculate recommended action based on minimum loss
  const activeRecommended = useMemo(() => {
    if (!displayOptions || displayOptions.length === 0) return recommendedAction;
    let minLoss = Infinity;
    let bestId = recommendedAction;
    for (const opt of displayOptions) {
      if (opt.net_expected_loss < minLoss) {
        minLoss = opt.net_expected_loss;
        bestId = opt.action_id;
      }
    }
    return bestId;
  }, [displayOptions, recommendedAction]);

  const getActionIcon = (actionId: string) => {
    switch (actionId) {
      case 'NO_ACTION':
        return <Gauge className="text-slate-500" size={20} />;
      case 'DERATE_THROTTLE':
        return <Sliders className="text-amber-500" size={20} />;
      case 'IMMEDIATE_MAINTENANCE':
        return <Wrench className="text-blue-500" size={20} />;
      default:
        return <Gauge className="text-slate-500" size={20} />;
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      {/* Header & Controls Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-5 border-b border-slate-200 gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-0.5 rounded uppercase tracking-wider">
              Autonomous Governance
            </span>
            <span className="text-xs text-slate-400 font-mono">
              Loss Model: L = C_direct + P_f * C_fail * α
            </span>
          </div>
          <h2 className="text-lg font-bold text-[#061838] mt-1">
            Decision Arena & Actionable Operational Trade-offs
          </h2>
          <p className="text-xs text-slate-500">
            Compare expected losses across operational policies grounded in real-time degradation physics.
          </p>
        </div>

        {/* Live Sensitivity Sliders */}
        <div className="flex flex-wrap items-center gap-4 bg-slate-50 p-3 rounded-lg border border-slate-200">
          {/* Risk Tolerance Slider */}
          <div className="flex flex-col space-y-1 min-w-[140px]">
            <div className="flex justify-between text-[11px] font-semibold text-slate-600">
              <span>Risk Tolerance (α)</span>
              <span className="font-mono text-blue-600">{riskTolerance.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.05"
              value={riskTolerance}
              onChange={(e) => onRiskToleranceChange(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#061838]"
            />
          </div>

          {/* Downtime Cost Slider */}
          <div className="flex flex-col space-y-1 min-w-[160px]">
            <div className="flex justify-between text-[11px] font-semibold text-slate-600">
              <span>Downtime Cost ($/hr)</span>
              <span className="font-mono text-emerald-600">${hourlyDowntimeCost}/hr</span>
            </div>
            <input
              type="range"
              min="100"
              max="2000"
              step="50"
              value={hourlyDowntimeCost}
              onChange={(e) => onHourlyDowntimeCostChange(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-[#061838]"
            />
          </div>
        </div>
      </div>

      {/* 3-Column Decision Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-5">
        {displayOptions.map((option) => {
          const isRecommended = option.action_id === activeRecommended;

          return (
            <div
              key={option.action_id}
              onClick={() => setSelectedActionId(option.action_id)}
              className={`relative rounded-xl border p-4 transition-all cursor-pointer flex flex-col justify-between ${
                isRecommended
                  ? 'border-blue-500 bg-blue-50/20 ring-2 ring-blue-500/20 shadow-md'
                  : 'border-slate-200 bg-white hover:border-slate-300 shadow-sm'
              }`}
            >
              {/* Recommended Badge */}
              {isRecommended && (
                <div className="absolute -top-3 left-4 bg-blue-600 text-white text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full shadow-sm flex items-center space-x-1">
                  <CheckCircle2 size={11} />
                  <span>Recommended Optimal Policy</span>
                </div>
              )}

              <div>
                {/* Option Header */}
                <div className="flex items-center justify-between mt-1">
                  <div className="flex items-center space-x-2">
                    <div className="p-1.5 rounded-lg bg-slate-100 border border-slate-200">
                      {getActionIcon(option.action_id)}
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-[#061838] leading-tight">
                        {option.name}
                      </h3>
                      <span className="text-[10px] font-mono text-slate-400">
                        {option.action_id}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Net Expected Loss KPI */}
                <div className="mt-4 p-3 bg-slate-50 rounded-lg border border-slate-100">
                  <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Net Expected Loss
                  </span>
                  <div className="text-2xl font-black text-[#061838] mt-0.5">
                    ${option.net_expected_loss.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500 mt-2 pt-2 border-t border-slate-200/60">
                    <span>Direct Action Cost:</span>
                    <span className="font-semibold text-slate-700">
                      ${option.direct_cost.toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Physical Operating Profile */}
                <div className="space-y-1.5 mt-3 text-xs">
                  <div className="flex justify-between text-slate-600">
                    <span>Post-Action Load:</span>
                    <span className="font-mono font-bold text-slate-800">
                      {(option.post_action_load * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-600">
                    <span>Failure Probability:</span>
                    <span className={`font-mono font-bold ${option.failure_probability > 0.3 ? 'text-rose-600' : 'text-emerald-600'}`}>
                      {(option.failure_probability * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between text-slate-600">
                    <span>Composite Risk Score:</span>
                    <span className="font-mono font-bold text-slate-800">
                      {(option.risk_score * 100).toFixed(0)} / 100
                    </span>
                  </div>
                </div>

                {/* Justification Text */}
                <p className="text-[11px] text-slate-500 mt-3 italic border-l-2 border-slate-300 pl-2">
                  {option.justification}
                </p>
              </div>

              {/* Bottom Action Footer */}
              <div className="mt-4 pt-3 border-t border-slate-100 flex flex-col space-y-2">
                {option.requires_human_approval && (
                  <div className="flex items-center space-x-1 text-[10px] text-amber-700 bg-amber-50 px-2 py-1 rounded border border-amber-200">
                    <AlertCircle size={12} className="shrink-0" />
                    <span>Requires Authorized Human Operator Sign-Off</span>
                  </div>
                )}

                <button
                  disabled={isExecuting}
                  onClick={(e) => {
                    e.stopPropagation();
                    onExecuteAction(option.action_id);
                  }}
                  className={`w-full py-2 px-3 rounded-lg text-xs font-bold transition-all flex items-center justify-center space-x-1.5 shadow-sm ${
                    isRecommended
                      ? 'bg-[#061838] text-white hover:bg-[#0c2759] active:scale-[0.98]'
                      : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <span>{option.requires_human_approval ? 'Authorize & Execute' : 'Simulate Policy'}</span>
                  <ArrowRight size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
