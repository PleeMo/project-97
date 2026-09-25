import React from 'react'

/* Dependency-free SVG charts — hand-rolled so the project stays on plain React. */

const TEAL = '#1F6F5C'
const AMBER = '#C7752B'
const DANGER = '#B23A32'
const LINE = '#DCE3DF'
const INK = '#14231F'

/**
 * Area/line trend over an ordered list of numbers.
 * props: values (number[]), labels (string[] optional), color, height, threshold
 */
export function TrendChart({ values = [], labels = [], color = TEAL, height = 120, threshold = null }) {
  if (!values.length) return <p className="text-xs text-ink/40">No data yet.</p>

  const W = 560
  const PAD_X = 8
  const PAD_Y = 12
  const max = Math.max(...values, threshold ?? 0, 1)
  const n = values.length

  const x = (i) => PAD_X + (i * (W - 2 * PAD_X)) / Math.max(1, n - 1)
  const y = (v) => height - PAD_Y - (v / max) * (height - 2 * PAD_Y)

  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${x(n - 1).toFixed(1)},${height - PAD_Y} L${x(0).toFixed(1)},${height - PAD_Y} Z`

  const total = values.reduce((a, b) => a + b, 0)

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" style={{ height }} role="img">
        <path d={area} fill={color} opacity="0.12" />
        <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
        {threshold != null && y(threshold) > 0 && (
          <line x1={PAD_X} y1={y(threshold)} x2={W - PAD_X} y2={y(threshold)}
            stroke={DANGER} strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />
        )}
        {values.map((v, i) =>
          v > 0 ? <circle key={i} cx={x(i)} cy={y(v)} r="2.5" fill={color} /> : null
        )}
        <text x={PAD_X} y={10} fontSize="10" fill="#7A8783">max {max}</text>
      </svg>
      <div className="flex justify-between text-[10px] text-ink/40 mt-0.5">
        <span>{labels[0] || ''}</span>
        <span className="text-ink/60 font-medium">total {total}</span>
        <span>{labels[labels.length - 1] || ''}</span>
      </div>
    </div>
  )
}

/**
 * Donut chart with legend.
 * props: data [{label, value, color}], size
 */
export function Donut({ data = [], size = 130 }) {
  const total = data.reduce((s, d) => s + d.value, 0)
  const R = 54
  const C = 2 * Math.PI * R
  let offset = 0

  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 140 140" style={{ width: size, height: size }}>
        <circle cx="70" cy="70" r={R} fill="none" stroke={LINE} strokeWidth="16" />
        {total > 0 && data.map((d) => {
          const frac = d.value / total
          const dash = `${(frac * C).toFixed(2)} ${C.toFixed(2)}`
          const el = (
            <circle key={d.label} cx="70" cy="70" r={R} fill="none"
              stroke={d.color} strokeWidth="16"
              strokeDasharray={dash} strokeDashoffset={-offset}
              transform="rotate(-90 70 70)" />
          )
          offset += frac * C
          return el
        })}
        <text x="70" y="66" textAnchor="middle" fontSize="22" fontWeight="600" fill={INK}>
          {total}
        </text>
        <text x="70" y="84" textAnchor="middle" fontSize="10" fill="#7A8783">batches</text>
      </svg>
      <ul className="space-y-1.5 text-xs">
        {data.map((d) => (
          <li key={d.label} className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
            <span className="text-ink/70">{d.label}</span>
            <span className="font-mono text-ink/50">{d.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Sparkline of risk scores across a batch's QC tests, with the fail threshold.
 * props: values (number[])
 */
export function RiskHistory({ values = [] }) {
  if (values.length < 2) return null

  const W = 320
  const H = 54
  const x = (i) => 4 + (i * (W - 8)) / (values.length - 1)
  const y = (v) => H - 6 - (Math.min(v, 100) / 100) * (H - 12)
  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
        <rect x="0" y={y(100)} width={W} height={y(50) - y(100)} fill={DANGER} opacity="0.07" />
        <line x1="0" y1={y(50)} x2={W} y2={y(50)} stroke={DANGER} strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
        <path d={line} fill="none" stroke={INK} strokeWidth="1.8" />
        {values.map((v, i) => (
          <circle key={i} cx={x(i)} cy={y(v)} r="3"
            fill={v >= 50 ? DANGER : v >= 25 ? AMBER : TEAL} />
        ))}
      </svg>
      <p className="text-[10px] text-ink/40">
        risk history across {values.length} tests · dashed line = fail threshold (50)
      </p>
    </div>
  )
}

/**
 * Small vertical bar chart.
 * props: data [{label, value, color}]
 */
export function BarChart({ data = [], height = 90 }) {
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <div className="flex items-end gap-3" style={{ height }}>
      {data.map((d) => (
        <div key={d.label} className="flex-1 flex flex-col items-center justify-end h-full">
          <span className="text-[10px] font-mono text-ink/60 mb-0.5">{d.value}</span>
          <div className="w-full rounded-t transition-all"
            style={{
              height: `${Math.max(4, (d.value / max) * 100)}%`,
              background: d.color || TEAL,
              opacity: d.value === 0 ? 0.25 : 1,
            }} />
          <span className="text-[10px] text-ink/50 mt-1 capitalize">{d.label}</span>
        </div>
      ))}
    </div>
  )
}
