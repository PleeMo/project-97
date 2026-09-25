import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { TrendChart, Donut, BarChart } from '../components/Charts.jsx'

const STATUS_COLORS = {
  in_production: '#94A3B8',
  passed_qc: '#1F6F5C',
  failed_qc: '#B23A32',
  in_transit: '#C7752B',
  delivered: '#165445',
  recalled: '#7F1D1D',
}

function ChartCard({ title, hint, children }) {
  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="font-medium text-sm">{title}</h2>
        {hint && <span className="text-[10px] text-ink/40">{hint}</span>}
      </div>
      {children}
    </div>
  )
}

function StatCard({ label, value, tone = 'ink', hint }) {
  const toneClass = {
    ink: 'text-ink',
    teal: 'text-teal',
    danger: 'text-danger',
    amber: 'text-amber',
  }[tone]
  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <p className="text-xs text-ink/50">{label}</p>
      <p className={`font-display text-3xl font-semibold mt-1 ${toneClass}`}>{value}</p>
      {hint && <p className="text-[11px] text-ink/40 mt-0.5">{hint}</p>}
    </div>
  )
}

function ModelCard({ model, isAdmin, onRetrain, retraining }) {
  if (!model) {
    return (
      <div className="bg-surface border border-line rounded-xl p-5">
        <h2 className="font-medium text-sm mb-2">ML risk model</h2>
        <p className="text-xs text-ink/40">Loading model info…</p>
      </div>
    )
  }

  const holdout = model.holdout || {}
  const cv = model.cross_validation || {}
  const importances = model.feature_importances || []

  return (
    <div className="bg-surface border border-line rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-medium text-sm">ML risk model</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          model.source === 'ml' ? 'bg-teal-light text-teal-dark' : 'bg-amber-light text-amber'}`}>
          {model.source === 'ml' ? 'RandomForest' : 'rule-based fallback'}
        </span>
      </div>

      {model.source === 'ml' ? (
        <>
          <div className="grid grid-cols-4 gap-2 text-center mb-3">
            <div className="bg-paper rounded-md py-2">
              <p className="text-[10px] text-ink/50">Accuracy</p>
              <p className="text-sm font-mono">{(holdout.accuracy * 100).toFixed(1)}%</p>
            </div>
            <div className="bg-paper rounded-md py-2">
              <p className="text-[10px] text-ink/50">F1</p>
              <p className="text-sm font-mono">{holdout.f1?.toFixed(3)}</p>
            </div>
            <div className="bg-paper rounded-md py-2">
              <p className="text-[10px] text-ink/50">CV acc.</p>
              <p className="text-sm font-mono">
                {(cv.accuracy_mean * 100).toFixed(1)}% ±{(cv.accuracy_std * 100).toFixed(1)}
              </p>
            </div>
            <div className="bg-paper rounded-md py-2">
              <p className="text-[10px] text-ink/50">Samples</p>
              <p className="text-sm font-mono">{model.n_samples}</p>
            </div>
          </div>

          <p className="text-xs text-ink/50 mb-1.5">Feature importance</p>
          <div className="space-y-1.5">
            {importances.map((fi) => (
              <div key={fi.feature} className="flex items-center gap-2">
                <span className="text-[11px] font-mono w-32 shrink-0 text-ink/60">{fi.feature}</span>
                <div className="flex-1 h-2 bg-paper rounded-full overflow-hidden">
                  <div className="h-full bg-teal rounded-full"
                    style={{ width: `${Math.max(4, fi.importance * 100)}%` }} />
                </div>
                <span className="text-[11px] font-mono text-ink/50 w-10 text-right">
                  {(fi.importance * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between mt-3 pt-3 border-t border-line">
            <p className="text-[11px] text-ink/40">Trained {model.trained_at || '—'}</p>
            {isAdmin && (
              <button onClick={onRetrain} disabled={retraining}
                className="text-xs font-medium text-teal-dark hover:underline disabled:opacity-50">
                {retraining ? 'Retraining…' : '↻ Retrain model'}
              </button>
            )}
          </div>
        </>
      ) : (
        <p className="text-xs text-ink/50">{model.message}</p>
      )}
    </div>
  )
}

export default function DashboardHome({ session }) {
  const [summary, setSummary] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [batches, setBatches] = useState([])
  const [model, setModel] = useState(null)
  const [retraining, setRetraining] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const isAdmin = session?.user?.role === 'admin'

  useEffect(() => {
    api.summary().then(setSummary).catch((e) => setError(e.message))
    api.analytics().then(setAnalytics).catch(() => {})
    api.listBatches().then((b) => setBatches(b.slice(0, 5))).catch(() => {})
    api.modelInfo().then(setModel).catch(() => {})
  }, [])

  async function retrain() {
    setRetraining(true)
    setError('')
    try {
      const info = await api.retrain()
      setModel(info)
      setNotice(`Model retrained — holdout accuracy ${(info.holdout.accuracy * 100).toFixed(1)}%.`)
      api.summary().then(setSummary).catch(() => {})
    } catch (err) {
      setError(err.message)
    } finally {
      setRetraining(false)
    }
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="font-display text-2xl font-semibold">Welcome back, {session?.user?.name?.split(' ')[0]}</h1>
        <p className="text-ink/50 text-sm mt-1">Here's what's happening across your batches today.</p>
      </div>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}
      {notice && <p className="text-teal-dark text-sm mb-4">{notice}</p>}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
            <StatCard label="Total batches" value={summary.total_batches} />
            <StatCard label="Passed QC" value={summary.passed_qc} tone="teal" />
            <StatCard label="Failed QC" value={summary.failed_qc} tone="danger" />
            <StatCard label="In transit" value={summary.in_transit} tone="amber" />
            <StatCard label="Recalled" value={summary.recalled} tone="danger" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <StatCard label="QR scans (all time)" value={summary.total_scans} tone="teal"
              hint="public verification attempts" />
            <StatCard label="Flagged for counterfeiting" value={summary.flagged_batches}
              tone={summary.flagged_batches > 0 ? 'danger' : 'teal'}
              hint="unusual scan patterns in 24h" />
            <StatCard label="Cold-chain breaches (24h)" value={summary.cold_chain_breaches_24h}
              tone={summary.cold_chain_breaches_24h > 0 ? 'amber' : 'teal'}
              hint="readings outside 0–8°C" />
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Charts */}
        {analytics && (
          <>
            <ChartCard title="QR scans" hint="last 14 days">
              <TrendChart
                values={analytics.days.map((d) => d.scans)}
                labels={[analytics.days[0]?.date, analytics.days[13]?.date]}
                color="#1F6F5C"
              />
            </ChartCard>

            <ChartCard title="Cold-chain breaches" hint="readings outside 0–8 °C, last 14 days">
              <TrendChart
                values={analytics.days.map((d) => d.breaches)}
                labels={[analytics.days[0]?.date, analytics.days[13]?.date]}
                color="#C7752B"
              />
            </ChartCard>

            <ChartCard title="Batch status" hint="all batches">
              <Donut
                data={(summary?.status_breakdown || []).map((s) => ({
                  label: s.status.replace('_', ' '),
                  value: s.count,
                  color: STATUS_COLORS[s.status] || '#94A3B8',
                }))}
              />
            </ChartCard>

            <ChartCard title="Risk profile" hint="latest QC test per batch">
              <BarChart
                data={analytics.risk_buckets.map((b) => ({
                  label: b.bucket,
                  value: b.count,
                  color: { low: '#1F6F5C', moderate: '#C7752B', high: '#B23A32', untested: '#94A3B8' }[b.bucket],
                }))}
              />
            </ChartCard>
          </>
        )}

        <ModelCard model={model} isAdmin={isAdmin} onRetrain={retrain} retraining={retraining} />

        <div className="bg-surface border border-line rounded-xl">
          <div className="px-5 py-4 border-b border-line flex items-center justify-between">
            <h2 className="font-medium text-sm">Recent batches</h2>
            <Link to="/batches" className="text-xs text-teal-dark hover:underline">View all →</Link>
          </div>
          <div className="divide-y divide-line">
            {batches.map((b) => (
              <Link key={b.id} to={`/batches/${b.id}`} className="flex items-center justify-between px-5 py-3 hover:bg-paper transition-colors">
                <div>
                  <p className="text-sm font-medium">{b.product_name}</p>
                  <p className="text-xs text-ink/50 font-mono">{b.batch_code}</p>
                </div>
                <span className="text-xs text-ink/40 capitalize">{b.status.replace('_', ' ')}</span>
              </Link>
            ))}
            {batches.length === 0 && (
              <p className="px-5 py-6 text-sm text-ink/40 text-center">No batches yet — create one to get started.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
