import React from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from 'recharts';

/**
 * Quality Score Radial/Gauge Chart
 */
export function ScoreGauge({ score = 85, size = 180 }) {
  const normalizedScore = Math.max(0, Math.min(100, Math.round(score)));

  let color = '#10b981'; // emerald
  let label = 'Excellent';
  if (normalizedScore < 50) {
    color = '#ef4444'; // rose
    label = 'Critical';
  } else if (normalizedScore < 75) {
    color = '#f59e0b'; // amber
    label = 'Fair';
  } else if (normalizedScore < 90) {
    color = '#0284c7'; // brand
    label = 'Good';
  }

  const data = [
    { name: 'Score', value: normalizedScore },
    { name: 'Remaining', value: 100 - normalizedScore },
  ];

  return (
    <div className="flex flex-col items-center justify-center p-3">
      <div className="relative" style={{ width: size, height: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              startAngle={210}
              endAngle={-30}
              innerRadius={size * 0.35}
              outerRadius={size * 0.45}
              paddingAngle={2}
              dataKey="value"
            >
              <Cell fill={color} />
              <Cell fill="#e2e8f0" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-3xl font-extrabold text-slate-900 tracking-tight">{normalizedScore}</span>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">out of 100</span>
        </div>
      </div>
      <div className="mt-1 flex items-center gap-1.5 text-xs font-semibold" style={{ color }}>
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }}></span>
        {label} Quality
      </div>
    </div>
  );
}

/**
 * Missing Values by Column Bar Chart
 */
export function MissingDistributionChart({ data = [] }) {
  if (!data || data.length === 0) {
    return (
      <div className="h-56 flex items-center justify-center text-xs text-slate-400">
        No missing values detected.
      </div>
    );
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: '#64748b' }}
            interval={0}
            angle={-25}
            textAnchor="end"
          />
          <YAxis tick={{ fontSize: 11, fill: '#64748b' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderRadius: '8px',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
            }}
            formatter={(val) => [`${val}% missing`, 'Missingness']}
          />
          <Bar dataKey="missingPct" fill="#f59e0b" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Penalty / Issues Breakdown Bar Chart
 */
export function PenaltyBreakdownChart({ penalties = {} }) {
  const chartData = [
    { name: 'Missing', penalty: penalties.missing_penalty || 0, fill: '#f59e0b' },
    { name: 'Duplicates', penalty: penalties.duplicate_penalty || 0, fill: '#3b82f6' },
    { name: 'Validity', penalty: penalties.validity_penalty || 0, fill: '#ef4444' },
    { name: 'Consistency', penalty: penalties.consistency_penalty || 0, fill: '#8b5cf6' },
  ];

  return (
    <div className="h-52 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
          <XAxis type="number" tick={{ fontSize: 11, fill: '#64748b' }} domain={[0, 'dataMax + 5']} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#475569' }} width={80} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              borderRadius: '8px',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
            }}
            formatter={(val) => [`-${val} pts`, 'Score Deduction']}
          />
          <Bar dataKey="penalty" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
