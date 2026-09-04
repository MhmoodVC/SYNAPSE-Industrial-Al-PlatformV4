'use client';

import React from 'react';
import { Activity, Zap, Thermometer, Gauge, Waves } from 'lucide-react';
import { TelemetryRecord } from '@/types/api';

interface TelemetryGridProps {
  telemetry: TelemetryRecord;
}

interface SensorConfig {
  id: keyof TelemetryRecord;
  historyKey: keyof TelemetryRecord;
  name: string;
  unit: string;
  nominal: number;
  icon: React.ReactNode;
  strokeColor: string;
  fillColor: string;
}

const SENSORS: SensorConfig[] = [
  {
    id: 'vibration',
    historyKey: 'vibration_history',
    name: 'Vibration RMS',
    unit: 'mm/s',
    nominal: 1.2,
    icon: <Activity size={16} className="text-rose-500" />,
    strokeColor: '#EF4444',
    fillColor: 'rgba(239, 68, 68, 0.1)',
  },
  {
    id: 'motor_current',
    historyKey: 'motor_current_history',
    name: 'Motor Current',
    unit: 'A',
    nominal: 45.0,
    icon: <Zap size={16} className="text-amber-500" />,
    strokeColor: '#F59E0B',
    fillColor: 'rgba(245, 158, 11, 0.1)',
  },
  {
    id: 'temperature',
    historyKey: 'temperature_history',
    name: 'Bearing Temp',
    unit: '°C',
    nominal: 68.0,
    icon: <Thermometer size={16} className="text-orange-500" />,
    strokeColor: '#F97316',
    fillColor: 'rgba(249, 115, 22, 0.1)',
  },
  {
    id: 'pressure',
    historyKey: 'pressure_history',
    name: 'Discharge Pressure',
    unit: 'bar',
    nominal: 8.5,
    icon: <Gauge size={16} className="text-blue-500" />,
    strokeColor: '#3B82F6',
    fillColor: 'rgba(59, 130, 246, 0.1)',
  },
  {
    id: 'flow',
    historyKey: 'flow_history',
    name: 'Discharge Flow',
    unit: 'm³/h',
    nominal: 120.0,
    icon: <Waves size={16} className="text-emerald-500" />,
    strokeColor: '#10B981',
    fillColor: 'rgba(16, 185, 129, 0.1)',
  },
];

export const TelemetryGrid: React.FC<TelemetryGridProps> = ({ telemetry }) => {
  const renderSparkline = (data: number[], stroke: string, fill: string) => {
    if (!data || data.length === 0) return null;

    const width = 160;
    const height = 46;
    const padding = 4;

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    const points = data.map((val, idx) => {
      const x = padding + (idx / Math.max(1, data.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((val - min) / range) * (height - 2 * padding);
      return `${x},${y}`;
    });

    const pathD = `M ${points.join(' L ')}`;
    const areaD = `${pathD} L ${width - padding},${height} L ${padding},${height} Z`;

    const lastPoint = points[points.length - 1]?.split(',');
    const lastX = lastPoint ? parseFloat(lastPoint[0]) : 0;
    const lastY = lastPoint ? parseFloat(lastPoint[1]) : 0;

    return (
      <svg className="w-full h-12 overflow-visible" viewBox={`0 0 ${width} ${height}`}>
        {/* Subtle grid line */}
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#E2E8F0"
          strokeDasharray="2,2"
        />
        {/* Area fill */}
        <path d={areaD} fill={fill} />
        {/* Line */}
        <path d={pathD} fill="none" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
        {/* Latest point circle */}
        {points.length > 0 && (
          <circle cx={lastX} cy={lastY} r="3" fill={stroke} />
        )}
      </svg>
    );
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
      <div className="flex items-center justify-between pb-4 border-b border-slate-200">
        <div>
          <h3 className="text-base font-bold text-[#061838]">
            Real-Time Telemetry Stream & Moving Window
          </h3>
          <p className="text-xs text-slate-500">
            30-sample sliding window with baseline deviation tracking
          </p>
        </div>
        <div className="flex items-center space-x-2 text-xs font-mono text-slate-500">
          <span>Operating Load:</span>
          <span className="font-bold text-[#061838] bg-slate-100 px-2 py-0.5 rounded">
            {telemetry?.operating_load != null ? `${(telemetry.operating_load * 100).toFixed(0)}%` : '100%'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mt-4">
        {SENSORS.map((sensor) => {
          const currentVal = (telemetry?.[sensor.id] as number) ?? 0;
          const history = (telemetry?.[sensor.historyKey] as number[]) ?? [];
          const delta = currentVal - sensor.nominal;
          const deltaPct = ((delta / sensor.nominal) * 100).toFixed(1);

          return (
            <div
              key={sensor.id}
              className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-200 transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-500 truncate" title={sensor.name}>
                    {sensor.name}
                  </span>
                  {sensor.icon}
                </div>
                <div className="flex items-baseline space-x-1.5 mt-2">
                  <span className="text-2xl font-black text-[#061838]">
                    {currentVal.toFixed(2)}
                  </span>
                  <span className="text-xs font-medium text-slate-400">
                    {sensor.unit}
                  </span>
                </div>
                <div className="flex items-center space-x-1 text-[11px] mt-0.5 font-medium">
                  <span className={delta >= 0 ? 'text-amber-600' : 'text-slate-500'}>
                    {delta >= 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2)}
                  </span>
                  <span className="text-slate-400">({delta >= 0 ? `+${deltaPct}` : deltaPct}%)</span>
                </div>
              </div>

              <div className="mt-3 pt-2 border-t border-slate-200/50">
                {renderSparkline(history, sensor.strokeColor, sensor.fillColor)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
