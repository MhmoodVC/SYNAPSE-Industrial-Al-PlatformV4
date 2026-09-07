import React from 'react';
import { BookOpen, Globe, FileText } from 'lucide-react';
import { EvidencePart } from '@/types/api';

interface ExplainableEvidenceProps {
  evidenceCard: EvidencePart;
}

export const ExplainableEvidence: React.FC<ExplainableEvidenceProps> = ({ evidenceCard }) => {
  return (
    <div className="w-full bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden mt-4 p-5">
      {/* Section 2: Industrial Standards & Compliance (ISO 10816-3 & UN SDGs) */}
      <div className="mb-6">
        <div className="flex items-center space-x-2 mb-3">
          <BookOpen size={16} className="text-indigo-600" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
            Industrial Standards & Compliance Suite
          </h4>
        </div>

        {/* ISO 10816-3 / ISO 20816-3 Vibration Severity Zones */}
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-600 mb-2">
            <span>ISO 10816-3 / ISO 20816-3 Vibration Severity Zones (Industrial Centrifugal Pumps)</span>
            <span className="text-[11px] font-mono text-slate-400">Class II & III Machinery</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-4 gap-2.5">
            <div className="p-2.5 rounded-lg border border-emerald-200 bg-emerald-50/60 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-emerald-900">Zone A</span>
                  <span className="text-[10px] font-mono font-bold text-emerald-700">&lt; 1.8 mm/s</span>
                </div>
                <p className="text-[11px] text-emerald-800 mt-1">
                  Pristine condition / Newly commissioned machinery.
                </p>
              </div>
              <span className="text-[9px] font-semibold uppercase text-emerald-600 mt-2">Optimal Health</span>
            </div>

            <div className="p-2.5 rounded-lg border border-blue-200 bg-blue-50/60 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-blue-900">Zone B</span>
                  <span className="text-[10px] font-mono font-bold text-blue-700">1.8 - 2.8 mm/s</span>
                </div>
                <p className="text-[11px] text-blue-800 mt-1">
                  Unrestricted continuous long-term operation.
                </p>
              </div>
              <span className="text-[9px] font-semibold uppercase text-blue-600 mt-2">Acceptable</span>
            </div>

            <div className="p-2.5 rounded-lg border border-amber-200 bg-amber-50/60 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-amber-900">Zone C</span>
                  <span className="text-[10px] font-mono font-bold text-amber-700">2.8 - 4.5 mm/s</span>
                </div>
                <p className="text-[11px] text-amber-800 mt-1">
                  Restricted operation; remedial de-rate action recommended.
                </p>
              </div>
              <span className="text-[9px] font-semibold uppercase text-amber-600 mt-2">Remedial Warning</span>
            </div>

            <div className="p-2.5 rounded-lg border border-rose-200 bg-rose-50/60 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-rose-900">Zone D</span>
                  <span className="text-[10px] font-mono font-bold text-rose-700">&gt; 4.5 mm/s</span>
                </div>
                <p className="text-[11px] text-rose-800 mt-1">
                  Critical danger zone; immediate trip or turnaround shutdown.
                </p>
              </div>
              <span className="text-[9px] font-semibold uppercase text-rose-600 mt-2">Trip / Shutdown</span>
            </div>
          </div>
        </div>

        {/* UN Sustainable Development Goals (SDGs) */}
        <div className="pt-3 border-t border-slate-100">
          <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-600 mb-2">
            <Globe size={13} className="text-emerald-600" />
            <span>United Nations Sustainability Alignment</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-start space-x-2.5">
              <span className="px-2 py-1 rounded text-xs font-black bg-orange-100 text-orange-800 border border-orange-200 shrink-0">
                SDG 9
              </span>
              <div>
                <span className="text-xs font-bold text-slate-800 block">Industry & Innovation</span>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Autonomous edge AI condition monitoring eliminating unscheduled plant downtime.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-start space-x-2.5">
              <span className="px-2 py-1 rounded text-xs font-black bg-amber-100 text-amber-800 border border-amber-200 shrink-0">
                SDG 12
              </span>
              <div>
                <span className="text-xs font-bold text-slate-800 block">Responsible Production</span>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Extends asset lifecycle through early de-rating, preventing premature component scrapping.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-lg border border-slate-200 bg-slate-50 flex items-start space-x-2.5">
              <span className="px-2 py-1 rounded text-xs font-black bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0">
                SDG 13
              </span>
              <div>
                <span className="text-xs font-bold text-slate-800 block">Climate Action</span>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Quantifies and eliminates parasitic motor load, curbing avoidable grid CO2 emissions.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Section 3: Traceable Evidence Card (4-Part Taxonomy & XAI Attribution) */}
      <div className="pt-5 border-t border-slate-200">
        <div className="flex items-center space-x-2 mb-3">
          <FileText size={15} className="text-blue-600" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
            Traceable Evidence Card (4-Part Taxonomy)
          </h4>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
              1. Primary Observation
            </span>
            <p className="text-xs font-medium text-slate-800 leading-relaxed">
              {evidenceCard?.observation || 'Awaiting live sensor stream...'}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
              2. Baseline Expectation
            </span>
            <p className="text-xs font-medium text-slate-800 leading-relaxed">
              {evidenceCard?.expected || 'Nominal operating envelope baseline'}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-blue-200 bg-blue-50/30">
            <span className="text-[10px] font-bold uppercase tracking-wider text-blue-700 block mb-1">
              3. Physical Interpretation
            </span>
            <p className="text-xs font-medium text-blue-950 leading-relaxed">
              {evidenceCard?.physics_interpretation || 'Hydrodynamic pressure & vibration analysis'}
            </p>
          </div>

          <div className="p-3.5 rounded-lg border border-emerald-200 bg-emerald-50/30">
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-700 block mb-1">
              4. Action Rationale
            </span>
            <p className="text-xs font-medium text-emerald-950 leading-relaxed">
              {evidenceCard?.action_rationale || 'Optimal policy recommendation based on expected loss'}
            </p>
          </div>
        </div>

        {/* Feature Attribution & Anomaly Contributions (XAI Progress Bars) */}
        {(evidenceCard as any)?.items && (evidenceCard as any).items.length > 0 && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-600">
                Feature Attribution & Anomaly Contributions (Robust-Z Breakdown)
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                Normalized Weight (%)
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {(evidenceCard as any).items.map((item: any, idx: number) => (
                <div
                  key={item.feature || idx}
                  className="p-2.5 rounded-lg border border-slate-200 bg-slate-50/60 flex flex-col justify-between space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-800 capitalize">
                      {String(item.feature).replace('_', ' ')}
                    </span>
                    <span className="text-xs font-mono font-bold text-amber-600">
                      {item.contribution_pct ?? 0}%
                    </span>
                  </div>

                  <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-amber-500 h-full rounded-full transition-all duration-300"
                      style={{ width: `${item.contribution_pct ?? 0}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                    <span>
                      Actual: <b className="text-slate-700">{item.value} {item.units || ''}</b>
                    </span>
                    <span>Base: {item.baseline} {item.units || ''}</span>
                    <span className="text-rose-600 font-bold">Δ: +{item.deviation}σ</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};