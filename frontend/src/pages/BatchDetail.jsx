import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from '../components/StatusBadge.jsx'
import RiskGauge from '../components/RiskGauge.jsx'
import { RiskHistory } from '../components/Charts.jsx'

// Which logistics events the backend accepts from each batch status
// (mirrors ALLOWED_FROM in backend/app/routers/supply_chain.py).
const ALLOWED_FROM = {
  in_production: [],
  passed_qc: ['shipped'],
  failed_qc: [],
  in_transit: ['received', 'shipped', 'sold'],
  delivered: ['sold'],
  recalled: [],
}

const LIFECYCLE_HINTS = {
  in_production: 'Log a quality test to release this batch.',
  failed_qc: 'QC failed — a passing re-test is required before it can move.',
  recalled: 'Recalled: no further movement or testing is allowed.',
}

const EVENT_TYPES = ['shipped', 'received', 'sold']  // options are filtered per status at render time

/* ---------- unified timeline (kinds → colors) ---------- */
const TIMELINE_TONE = {
  production: 'bg-ink',
  qc: 'bg-teal',
  event: 'bg-teal',
  scan: 'bg-amber',
  breach: 'bg-danger',
  recall: 'bg-danger',
}

const TIMELINE_LABEL = {
  production: 'Production',
  qc: 'Quality',
  event: 'Logistics',
  scan: 'Scan',
  breach: 'Cold chain',
  recall: 'Recall',
}

/* ---------- cold-chain sparkline ---------- */
function TempChart({ readings, safeMin, safeMax }) {
  if (!readings?.length) return <p className="text-xs text-ink/40">No temperature readings yet.</p>

  const W = 560, H = 150, PAD = 10
  const temps = readings.map((r) => r.temperature_c)
  const min = Math.min(...temps, safeMin) - 1
  const max = Math.max(...temps, safeMax) + 1
  const span = Math.max(0.1, max - min)

  const x = (i) => PAD + (i * (W - 2 * PAD)) / Math.max(1, readings.length - 1)
  const y = (t) => H - PAD - ((t - min) / span) * (H - 2 * PAD)

  const path = readings
    .map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(r.temperature_c).toFixed(1)}`)
    .join(' ')

  const breaches = readings
    .map((r, i) => ({ r, i }))
    .filter(({ r }) => r.temperature_c < safeMin || r.temperature_c > safeMax)

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-36" role="img" aria-label="Cold chain temperature chart">
        {/* safe band */}
        <rect x={PAD} y={y(safeMax)} width={W - 2 * PAD} height={Math.max(1, y(safeMin) - y(safeMax))}
          fill="#E7F0EC" />
        <line x1={PAD} y1={y(safeMax)} x2={W - PAD} y2={y(safeMax)} stroke="#1F6F5C" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
        <line x1={PAD} y1={y(safeMin)} x2={W - PAD} y2={y(safeMin)} stroke="#1F6F5C" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
        {/* readings */}
        <path d={path} fill="none" stroke="#14231F" strokeWidth="2" strokeLinejoin="round" />
        {/* breaches */}
        {breaches.map(({ r, i }) => (
          <circle key={r.id || i} cx={x(i)} cy={y(r.temperature_c)} r="3.5" fill="#B23A32" />
        ))}
        {/* axis labels */}
        <text x={PAD} y={12} fontSize="10" fill="#7A8783">{max.toFixed(1)}°C</text>
        <text x={PAD} y={H - 2} fontSize="10" fill="#7A8783">{min.toFixed(1)}°C</text>
        <text x={W - PAD} y={y(safeMax) - 4} fontSize="10" fill="#1F6F5C" textAnchor="end">
          safe ≤ {safeMax}°C
        </text>
      </svg>
      <div className="flex gap-4 text-[11px] text-ink/50 mt-1">
        <span>{readings.length} readings</span>
        <span className="text-danger">● {breaches.length} out of safe range</span>
        <span>first {new Date(readings[0].recorded_at).toLocaleString()}</span>
      </div>
    </div>
  )
}

const RISK_TONE = {
  low: 'bg-teal-light text-teal-dark',
  medium: 'bg-amber-light text-amber',
  high: 'bg-danger-light text-danger',
}

export default function BatchDetail({ session }) {
  const { id } = useParams()
  const [batch, setBatch] = useState(null)
  const [qr, setQr] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [qcForm, setQcForm] = useState({ ph: '', brix: '', microbial_cfu: '', temperature_c: '', notes: '' })
  const [preview, setPreview] = useState(null)
  const [eventForm, setEventForm] = useState({ event_type: 'shipped', location: '', notes: '' })
  const [recallReason, setRecallReason] = useState('')
  const [cold, setCold] = useState(null)
  const [scans, setScans] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [showAllTimeline, setShowAllTimeline] = useState(false)
  const [simBusy, setSimBusy] = useState(false)

  const role = session?.user?.role
  const canLogQc = ['admin', 'producer'].includes(role)
  const canLogEvent = ['admin', 'producer', 'distributor', 'retailer'].includes(role)
  const canRecall = ['admin', 'producer'].includes(role)
  const canSimulate = ['admin', 'producer', 'distributor'].includes(role)

  function load() {
    api.getBatch(id).then(setBatch).catch((e) => setError(e.message))
    api.getQr(id).then(setQr).catch(() => {})
    api.getColdChain(id).then(setCold).catch(() => {})
    api.scanAnalysis(id).then(setScans).catch(() => setScans(null)) // 403 for non-QC roles
    api.batchTimeline(id).then(setTimeline).catch(() => setTimeline(null))
    setShowAllTimeline(false)
  }

  useEffect(load, [id])

  // live "what-if" ML preview as the QC form is filled in
  useEffect(() => {
    const hasAny = Object.entries(qcForm).some(([k, v]) => k !== 'notes' && v !== '')
    if (!hasAny) { setPreview(null); return }
    const params = {}
    if (qcForm.ph) params.ph = qcForm.ph
    if (qcForm.brix) params.brix = qcForm.brix
    if (qcForm.microbial_cfu) params.microbial_cfu = qcForm.microbial_cfu
    if (qcForm.temperature_c) params.temperature_c = qcForm.temperature_c
    const t = setTimeout(() => {
      api.predictRisk(params).then(setPreview).catch(() => {})
    }, 350)
    return () => clearTimeout(t)
  }, [qcForm])

  async function submitQc(e) {
    e.preventDefault()
    setError('')
    try {
      await api.createQualityTest({
        batch_id: id,
        ph: qcForm.ph ? Number(qcForm.ph) : null,
        brix: qcForm.brix ? Number(qcForm.brix) : null,
        microbial_cfu: qcForm.microbial_cfu ? Number(qcForm.microbial_cfu) : null,
        temperature_c: qcForm.temperature_c ? Number(qcForm.temperature_c) : null,
        notes: qcForm.notes || null,
      })
      setQcForm({ ph: '', brix: '', microbial_cfu: '', temperature_c: '', notes: '' })
      setPreview(null)
      setNotice('Quality test logged.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function submitEvent(e) {
    e.preventDefault()
    setError('')
    try {
      await api.createEvent({ batch_id: id, ...eventForm })
      setEventForm({ event_type: 'shipped', location: '', notes: '' })
      setNotice('Supply chain event logged.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function submitRecall(e) {
    e.preventDefault()
    setError('')
    try {
      await api.triggerRecall({ batch_id: id, reason: recallReason })
      setRecallReason('')
      setNotice('Recall triggered — downstream locations flagged.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function simulate(induceBreach) {
    setSimBusy(true)
    setError('')
    try {
      await api.simulateColdChain(id, {
        hours: 24, interval_minutes: 30, induce_breach: induceBreach,
      })
      setNotice(induceBreach ? 'Shipment simulated with a refrigeration failure.' : 'Shipment simulated.')
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSimBusy(false)
    }
  }

  async function uploadCert(testId, file) {
    setError('')
    try {
      await api.uploadCertificate(testId, file)
      setNotice(`Certificate "${file.name}" attached.`)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function downloadCert(testId) {
    try {
      const { blob, filename } = await api.downloadCertificate(testId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 5000)
    } catch (err) {
      setError(err.message)
    }
  }

  if (!batch) return <p className="text-ink/50 text-sm">{error || 'Loading…'}</p>

  const latestTest = batch.quality_tests?.[batch.quality_tests.length - 1]
  const stats = cold?.stats

  const status = batch.status
  const allowedEvents = ALLOWED_FROM[status] || []
  const lifecycleHint = LIFECYCLE_HINTS[status]
  const riskHistory = (batch.quality_tests || [])
    .map((t) => t.risk_score)
    .filter((v) => v !== null && v !== undefined)

  const expiry = batch.expiry_date ? new Date(batch.expiry_date) : null
  const daysToExpiry = expiry ? Math.ceil((expiry - Date.now()) / 86400000) : null
  const expiryTone = daysToExpiry == null ? null
    : daysToExpiry < 0 ? 'expired'
    : daysToExpiry <= 14 ? 'soon' : 'ok'

  const rawMaterial = batch.raw_material

  return (
    <div>
      <Link to="/batches" className="text-xs text-ink/50 hover:underline">← Back to batches</Link>

      <div className="flex items-start justify-between mt-2 mb-5">
        <div>
          <h1 className="font-display text-2xl font-semibold">{batch.product_name}</h1>
          <p className="font-mono text-sm text-ink/50 mt-1">{batch.batch_code}</p>
          <div className="mt-2"><StatusBadge status={batch.status} /></div>
        </div>
        {qr?.image_base64 && (
          <div className="text-center bg-surface border border-line rounded-xl p-3">
            <img src={qr.image_base64} alt="QR code" className="w-28 h-28" />
            <p className="text-[10px] text-ink/40 mt-1">Scan → {qr.verify_path}</p>
            <p className="text-[10px] text-ink/50 mt-0.5">{qr.scan_count || 0} scans to date</p>
            <a href={qr.image_base64} download={`${batch.batch_code}-qr.png`}
              className="text-[10px] text-teal-dark hover:underline inline-block mt-1">
              Download PNG ↓
            </a>
            <Link to={`/print/qr/${batch.id}`}
              className="block text-[10px] text-teal-dark hover:underline mt-0.5">
              Print label sheet 🖨
            </Link>
          </div>
        )}
      </div>

      {/* Traceability strip: where this batch came from and how long it keeps */}
      <div className="bg-surface border border-line rounded-xl px-5 py-3 mb-6 flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <p className="text-[10px] text-ink/40 uppercase tracking-wide">Produced</p>
          <p>{new Date(batch.production_date).toLocaleDateString()}</p>
        </div>
        <div>
          <p className="text-[10px] text-ink/40 uppercase tracking-wide">Best before</p>
          <p className="flex items-center gap-2">
            {expiry ? expiry.toLocaleDateString() : '—'}
            {expiryTone === 'expired' && (
              <span className="text-[10px] bg-danger text-white px-1.5 py-0.5 rounded">EXPIRED</span>
            )}
            {expiryTone === 'soon' && (
              <span className="text-[10px] bg-amber text-white px-1.5 py-0.5 rounded">{daysToExpiry}d LEFT</span>
            )}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-ink/40 uppercase tracking-wide">Volume</p>
          <p>{batch.volume_liters != null ? `${batch.volume_liters} L` : '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-ink/40 uppercase tracking-wide">Raw material</p>
          <p>{rawMaterial ? rawMaterial.material_type : '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-ink/40 uppercase tracking-wide">Supplier</p>
          <p>{rawMaterial?.supplier?.name || '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-ink/40 uppercase tracking-wide">Lot received</p>
          <p>{rawMaterial ? new Date(rawMaterial.received_date).toLocaleDateString() : '—'}</p>
        </div>
      </div>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}
      {notice && <p className="text-teal-dark text-sm mb-4">{notice}</p>}

      <div className="grid grid-cols-2 gap-6">
        {/* Quality tests */}
        <div className="bg-surface border border-line rounded-xl p-5">
          <h2 className="font-medium text-sm mb-4">Quality control</h2>

          {latestTest && (
            <div className="mb-4 pb-4 border-b border-line">
              <RiskGauge score={latestTest.risk_score} />
              {riskHistory.length >= 2 && (
                <div className="mt-3">
                  <RiskHistory values={riskHistory} />
                </div>
              )}
            </div>
          )}

          <div className="space-y-2 max-h-48 overflow-y-auto mb-4">
            {batch.quality_tests?.slice().reverse().map((t) => (
              <div key={t.id} className="text-xs bg-paper rounded-md px-3 py-2 flex items-center justify-between gap-2">
                <span className="truncate">
                  pH {t.ph ?? '—'} · Brix {t.brix ?? '—'} · CFU {t.microbial_cfu ?? '—'} · {t.temperature_c ?? '—'}°C
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  <span className={t.result === 'fail' ? 'text-danger font-medium' : 'text-teal-dark font-medium'}>
                    {t.result}
                  </span>
                  {t.certificate_filename && (
                    <button type="button" onClick={() => downloadCert(t.id)}
                      title={`Download ${t.certificate_filename}`}
                      className="hover:scale-110 transition-transform">📎</button>
                  )}
                  {canLogQc && (
                    <label title="Attach lab certificate (PDF/PNG/JPEG)" className="cursor-pointer opacity-60 hover:opacity-100">
                      ➕
                      <input type="file" accept=".pdf,.png,.jpg,.jpeg" className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0]
                          if (file) uploadCert(t.id, file)
                          e.target.value = ''
                        }} />
                    </label>
                  )}
                </span>
              </div>
            ))}
            {(!batch.quality_tests || batch.quality_tests.length === 0) && (
              <p className="text-xs text-ink/40">No tests logged yet.</p>
            )}
          </div>

          {canLogQc && status !== 'recalled' && (
            <form onSubmit={submitQc} className="space-y-2 pt-3 border-t border-line">
              <div className="grid grid-cols-2 gap-2">
                <input placeholder="pH" type="number" step="0.01" value={qcForm.ph}
                  onChange={(e) => setQcForm({ ...qcForm, ph: e.target.value })}
                  className="rounded-md border border-line px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal" />
                <input placeholder="Brix" type="number" step="0.1" value={qcForm.brix}
                  onChange={(e) => setQcForm({ ...qcForm, brix: e.target.value })}
                  className="rounded-md border border-line px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal" />
                <input placeholder="Microbial CFU/mL" type="number" step="0.1" value={qcForm.microbial_cfu}
                  onChange={(e) => setQcForm({ ...qcForm, microbial_cfu: e.target.value })}
                  className="rounded-md border border-line px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal" />
                <input placeholder="Temp °C" type="number" step="0.1" value={qcForm.temperature_c}
                  onChange={(e) => setQcForm({ ...qcForm, temperature_c: e.target.value })}
                  className="rounded-md border border-line px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal" />
              </div>
              {preview && (
                <p className="text-xs text-ink/50">
                  Live prediction: <span className="font-medium" style={{ color: preview.risk_score >= 50 ? '#B23A32' : '#1F6F5C' }}>
                    {preview.result} ({preview.risk_score}/100)
                  </span>
                  {preview.source === 'rule_based' && ' · rule-based fallback'}
                </p>
              )}
              <button type="submit" className="w-full bg-ink text-white text-xs font-medium rounded-md py-2">
                Log quality test
              </button>
            </form>
          )}
        </div>

        {/* Supply chain */}
        <div className="bg-surface border border-line rounded-xl p-5">
          <h2 className="font-medium text-sm mb-4">Supply chain journey</h2>
          <ol className="space-y-2 max-h-48 overflow-y-auto mb-4 border-l-2 border-line pl-4">
            {batch.events?.map((ev) => (
              <li key={ev.id} className="relative text-xs">
                <span className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-teal" />
                <span className="font-medium capitalize">{ev.event_type.replace('_', ' ')}</span>
                <span className="text-ink/50"> · {ev.location} · {new Date(ev.timestamp).toLocaleString()}</span>
              </li>
            ))}
            {(!batch.events || batch.events.length === 0) && (
              <p className="text-xs text-ink/40">No events logged yet.</p>
            )}
          </ol>

          {canLogEvent && allowedEvents.length > 0 && (
            <form onSubmit={submitEvent} className="space-y-2 pt-3 border-t border-line">
              <select
                value={allowedEvents.includes(eventForm.event_type) ? eventForm.event_type : allowedEvents[0]}
                onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })}
                className="w-full rounded-md border border-line px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal">
                {allowedEvents.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input placeholder="Location" value={eventForm.location} required
                onChange={(e) => setEventForm({ ...eventForm, location: e.target.value })}
                className="w-full rounded-md border border-line px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-teal" />
              <button type="submit" className="w-full bg-ink text-white text-xs font-medium rounded-md py-2">
                Log event
              </button>
            </form>
          )}
          {canLogEvent && allowedEvents.length === 0 && (
            <p className="text-xs text-ink/50 pt-3 border-t border-line">
              {lifecycleHint || 'No further events can be logged for this batch.'}
            </p>
          )}
        </div>
      </div>

      {/* Cold chain + anti-counterfeit */}
      <div className="grid grid-cols-2 gap-6 mt-6">
        <div className="bg-surface border border-line rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-sm">Cold chain</h2>
            {canSimulate && (
              <div className="flex gap-3 text-xs">
                <button onClick={() => simulate(false)} disabled={simBusy}
                  className="text-teal-dark hover:underline disabled:opacity-50">Simulate shipment</button>
                <button onClick={() => simulate(true)} disabled={simBusy}
                  className="text-danger hover:underline disabled:opacity-50">Simulate failure</button>
              </div>
            )}
          </div>

          {stats && stats.readings > 0 ? (
            <>
              <TempChart readings={cold.readings} safeMin={stats.safe_min_c} safeMax={stats.safe_max_c} />
              <div className="grid grid-cols-4 gap-2 mt-3 text-center">
                <div className="bg-paper rounded-md py-2">
                  <p className="text-[10px] text-ink/50">Min</p>
                  <p className="text-sm font-mono">{stats.min_c}°C</p>
                </div>
                <div className="bg-paper rounded-md py-2">
                  <p className="text-[10px] text-ink/50">Avg</p>
                  <p className="text-sm font-mono">{stats.avg_c}°C</p>
                </div>
                <div className="bg-paper rounded-md py-2">
                  <p className="text-[10px] text-ink/50">Max</p>
                  <p className="text-sm font-mono">{stats.max_c}°C</p>
                </div>
                <div className={`rounded-md py-2 ${stats.breaches > 0 ? 'bg-danger-light' : 'bg-teal-light'}`}>
                  <p className="text-[10px] text-ink/50">Breaches</p>
                  <p className={`text-sm font-mono ${stats.breaches > 0 ? 'text-danger' : 'text-teal-dark'}`}>
                    {stats.breaches}
                  </p>
                </div>
              </div>
            </>
          ) : (
            <p className="text-xs text-ink/40">
              No telemetry yet{canSimulate ? ' — simulate a shipment to see the chart.' : '.'}
            </p>
          )}
        </div>

        {scans && (
          <div className="bg-surface border border-line rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-medium text-sm">Anti-counterfeit</h2>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${RISK_TONE[scans.risk_level] || RISK_TONE.low}`}>
                {scans.risk_level} risk
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-3 text-center">
              <div className="bg-paper rounded-md py-2">
                <p className="text-[10px] text-ink/50">Total scans</p>
                <p className="text-sm font-mono">{scans.total_scans}</p>
              </div>
              <div className="bg-paper rounded-md py-2">
                <p className="text-[10px] text-ink/50">Last 24h</p>
                <p className="text-sm font-mono">{scans.scans_24h}</p>
              </div>
              <div className="bg-paper rounded-md py-2">
                <p className="text-[10px] text-ink/50">Locations 24h</p>
                <p className="text-sm font-mono">{scans.distinct_locations_24h}</p>
              </div>
            </div>

            {scans.flags.length > 0 ? (
              <ul className="space-y-1.5 mb-3">
                {scans.flags.map((f, i) => (
                  <li key={i} className="text-xs text-danger bg-danger-light rounded-md px-3 py-2">⚠ {f}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-teal-dark bg-teal-light rounded-md px-3 py-2 mb-3">
                ✓ Scan pattern looks normal for a genuine product.
              </p>
            )}

            <div className="border-t border-line pt-2 max-h-32 overflow-y-auto">
              {scans.recent_scans.map((s) => (
                <div key={s.id} className="text-[11px] text-ink/60 flex justify-between py-0.5">
                  <span className="truncate">{s.location || 'unknown location'}</span>
                  <span className="text-ink/40 shrink-0 ml-2">{new Date(s.scanned_at).toLocaleString()}</span>
                </div>
              ))}
              {scans.recent_scans.length === 0 && (
                <p className="text-[11px] text-ink/40">Nobody has scanned this code yet.</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Full timeline: every story this batch has to tell, newest first */}
      {timeline && timeline.entries.length > 0 && (
        <div className="bg-surface border border-line rounded-xl p-5 mt-6" data-testid="batch-timeline">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium text-sm">Full timeline</h2>
            <span className="text-[11px] text-ink/40">
              {timeline.counts.total} entries
              {timeline.counts.recall > 0 && ` · ${timeline.counts.recall} recall`}
              {timeline.counts.breach > 0 && ` · ${timeline.counts.breach} breaches`}
            </span>
          </div>
          <ol className="space-y-2.5 border-l-2 border-line pl-4 max-h-80 overflow-y-auto">
            {(showAllTimeline ? timeline.entries : timeline.entries.slice(0, 10)).map((e, i) => (
              <li key={`${e.at}-${i}`} className="relative text-xs">
                <span className={`absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full ${
                  e.severity === 'critical' ? 'bg-danger'
                  : e.severity === 'warning' ? 'bg-amber'
                  : TIMELINE_TONE[e.kind] || 'bg-teal'
                }`} />
                <span className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium">{e.title}</span>
                  <span className="text-[9px] uppercase tracking-wide bg-paper text-ink/50 px-1.5 py-0.5 rounded">
                    {TIMELINE_LABEL[e.kind] || e.kind}
                  </span>
                </span>
                {e.detail && <p className="text-ink/50 mt-0.5">{e.detail}</p>}
                <p className="text-ink/35 mt-0.5">{new Date(e.at).toLocaleString()}</p>
              </li>
            ))}
          </ol>
          {timeline.entries.length > 10 && (
            <button
              onClick={() => setShowAllTimeline((v) => !v)}
              className="mt-3 text-xs text-teal-dark hover:underline"
            >
              {showAllTimeline
                ? 'Show latest 10 only'
                : `Show all ${timeline.entries.length} entries ↑`}
            </button>
          )}
        </div>
      )}

      {canRecall && batch.status !== 'recalled' && (
        <div className="mt-6 bg-danger-light border border-danger/20 rounded-xl p-5">
          <h2 className="font-medium text-sm text-danger mb-2">Trigger recall</h2>
          <p className="text-xs text-ink/60 mb-3">This flags every downstream location this batch has reached.</p>
          <form onSubmit={submitRecall} className="flex gap-2">
            <input placeholder="Reason for recall" value={recallReason} required
              onChange={(e) => setRecallReason(e.target.value)}
              className="flex-1 rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-danger" />
            <button type="submit" className="bg-danger text-white px-4 py-2 rounded-md text-sm font-medium">
              Recall batch
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
