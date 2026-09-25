import React, { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from '../components/StatusBadge.jsx'

const EVENT_LABELS = {
  produced: 'Produced',
  quality_check: 'Quality check',
  shipped: 'Shipped',
  received: 'Received',
  sold: 'Sold at retail',
  recalled: 'Recalled',
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function Verify() {
  const { batchCode } = useParams()
  const [code, setCode] = useState(batchCode || '')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)

  // Permission-free location hint (IANA timezone) — sent with every verification
  // so the backend can spot one code being "used" in several countries at once.
  const timezone = React.useMemo(() => {
    try { return Intl.DateTimeFormat().resolvedOptions().timeZone } catch { return null }
  }, [])

  async function runVerify(c) {
    if (!c) return
    setLoading(true)
    setSearched(true)
    try {
      const data = await api.verify(c, timezone)
      setResult(data)
    } catch (err) {
      setResult({ valid: false, message: 'Something went wrong verifying this code.' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (batchCode) runVerify(batchCode)
  }, [batchCode])

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8">
          <span className="text-4xl">🧪</span>
          <h1 className="font-display text-3xl font-semibold text-white mt-3">Verify your product</h1>
          <p className="text-white/50 text-sm mt-2">
            Scan the QR code on your bottle, or enter the batch code printed on the label.
          </p>
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); runVerify(code) }}
          className="flex gap-2 mb-8"
        >
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="e.g. BQ-2026-24509"
            className="flex-1 rounded-md border border-white/20 bg-white/5 text-white placeholder-white/30 px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-teal"
          />
          <button
            type="submit"
            className="bg-teal hover:bg-teal-dark text-white px-5 py-3 rounded-md text-sm font-medium transition-colors"
          >
            Verify
          </button>
        </form>

        {loading && <p className="text-white/50 text-center text-sm">Checking…</p>}

        {!loading && searched && result && (
          <div className="bg-surface rounded-2xl overflow-hidden shadow-2xl">
            {result.valid ? (
              <>
                <div className={`px-6 py-4 flex items-center gap-3 ${result.status === 'recalled' ? 'bg-danger' : 'bg-teal'}`}>
                  <span className="text-2xl">{result.status === 'recalled' ? '⚠️' : '✓'}</span>
                  <div>
                    <p className="text-white font-medium">{result.message}</p>
                    <p className="text-white/70 text-xs font-mono">{result.batch_code}</p>
                  </div>
                </div>

                {result.alert && (
                  <div className="bg-amber-light border-b border-amber/30 px-6 py-3 flex items-start gap-2">
                    <span className="text-amber">⚠️</span>
                    <p className="text-xs text-ink/80">{result.alert}</p>
                  </div>
                )}

                <div className="p-6 space-y-5">
                  <div>
                    <h2 className="font-display text-xl font-semibold">{result.product_name}</h2>
                    <div className="mt-1"><StatusBadge status={result.status} /></div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-ink/40 text-xs">Produced</p>
                      <p>{fmtDate(result.production_date)}</p>
                    </div>
                    <div>
                      <p className="text-ink/40 text-xs">Best before</p>
                      <p>{fmtDate(result.expiry_date)}</p>
                    </div>
                    <div>
                      <p className="text-ink/40 text-xs">Source</p>
                      <p>{result.supplier_name || '—'}</p>
                    </div>
                    <div>
                      <p className="text-ink/40 text-xs">Latest QC result</p>
                      <p className="capitalize">{result.latest_quality_result || '—'}</p>
                    </div>
                    <div>
                      <p className="text-ink/40 text-xs">Verification #</p>
                      <p className="font-mono">{result.scan_count ?? '—'}</p>
                    </div>
                  </div>

                  {result.journey?.length > 0 && (
                    <div>
                      <p className="text-ink/40 text-xs mb-2">Journey</p>
                      <ol className="space-y-2 border-l-2 border-line pl-4">
                        {result.journey.map((ev) => (
                          <li key={ev.id} className="relative">
                            <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-teal" />
                            <p className="text-sm font-medium">{EVENT_LABELS[ev.event_type] || ev.event_type}</p>
                            <p className="text-xs text-ink/50">{ev.location} · {fmtDate(ev.timestamp)}</p>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="p-8 text-center">
                <span className="text-3xl">✕</span>
                <p className="mt-2 font-medium">{result.message}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
