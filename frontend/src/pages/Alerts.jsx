import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const TYPE_META = {
  counterfeit: { icon: '🚨', label: 'Possible cloned QR code' },
  qc_failed: { icon: '🧪', label: 'Failed quality control' },
  recalled: { icon: '⚠️', label: 'Active recall' },
  cold_chain: { icon: '🌡️', label: 'Cold-chain breach' },
  expiring: { icon: '⏳', label: 'Expiring stock' },
}

const SEVERITY_STYLE = {
  critical: 'bg-danger-light text-danger border-danger/25',
  warning: 'bg-amber-light text-amber border-amber/25',
  info: 'bg-teal-light text-teal-dark border-teal/25',
}

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    api.alerts().then(setAlerts).catch((e) => setError(e.message))
  }, [])

  const shown = filter === 'all' ? alerts : alerts.filter((a) => a.severity === filter)
  const counts = alerts.reduce((acc, a) => ({ ...acc, [a.severity]: (acc[a.severity] || 0) + 1 }), {})

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold">Alerts</h1>
          <p className="text-ink/50 text-sm mt-1">
            Everything needing attention — counterfeit flags, QC failures, cold-chain breaches, expiring stock.
          </p>
        </div>
        <div className="flex gap-2 text-xs">
          {['all', 'critical', 'warning'].map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-full capitalize border transition-colors ${
                filter === f ? 'bg-ink text-white border-ink' : 'bg-surface text-ink/60 border-line hover:border-ink/30'
              }`}>
              {f}{f !== 'all' && counts[f] ? ` (${counts[f]})` : ''}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}

      <div className="space-y-3">
        {shown.map((a) => {
          const meta = TYPE_META[a.type] || { icon: '•', label: a.type }
          return (
            <div key={a.id}
              className={`bg-surface border rounded-xl p-4 flex items-start gap-4 ${SEVERITY_STYLE[a.severity] || ''}`}>
              <span className="text-xl leading-none">{meta.icon}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{meta.label}</span>
                  <span className={`text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded font-medium ${
                    a.severity === 'critical' ? 'bg-danger text-white' : 'bg-amber text-white'
                  }`}>{a.severity}</span>
                  <span className="text-xs text-ink/40">{new Date(a.created_at).toLocaleString()}</span>
                </div>
                <p className="text-sm text-ink/80 mt-1">{a.message}</p>
                <Link to={`/batches/${a.batch_id}`}
                  className="text-xs text-teal-dark hover:underline inline-block mt-1">
                  {a.batch_code} · {a.product_name} →
                </Link>
              </div>
            </div>
          )
        })}

        {shown.length === 0 && !error && (
          <p className="text-sm text-ink/40 text-center py-10 bg-surface border border-line rounded-xl">
            Nothing needs attention{filter !== 'all' ? ` (${filter} only)` : ''}. 🎉
          </p>
        )}
      </div>
    </div>
  )
}
