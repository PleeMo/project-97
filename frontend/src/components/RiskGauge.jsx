import React from 'react'

export default function RiskGauge({ score }) {
  if (score === null || score === undefined) {
    return <span className="text-ink/40 text-sm">No QC data yet</span>
  }
  const color = score >= 50 ? '#B23A32' : score >= 25 ? '#C7752B' : '#1F6F5C'
  return (
    <div className="flex items-center gap-3">
      <div className="relative w-14 h-14">
        <svg viewBox="0 0 36 36" className="w-14 h-14 -rotate-90">
          <circle cx="18" cy="18" r="15.5" fill="none" stroke="#DCE3DF" strokeWidth="3.5" />
          <circle
            cx="18" cy="18" r="15.5" fill="none" stroke={color} strokeWidth="3.5"
            strokeDasharray={`${(score / 100) * 97.4} 97.4`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-xs font-mono font-medium">
          {Math.round(score)}
        </div>
      </div>
      <div className="text-sm">
        <div className="font-medium" style={{ color }}>
          {score >= 50 ? 'High risk' : score >= 25 ? 'Moderate risk' : 'Low risk'}
        </div>
        <div className="text-ink/50 text-xs">ML risk score / 100</div>
      </div>
    </div>
  )
}
