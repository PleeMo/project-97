import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import StatusBadge from '../components/StatusBadge.jsx'
import Banner from '../components/Banner.jsx'

const CAN_CREATE = ['admin', 'producer']
const PAGE_SIZE = 10

export default function Batches({ session }) {
  const [batches, setBatches] = useState([])
  const [materials, setMaterials] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ product_name: '', volume_liters: '', expiry_date: '', raw_material_id: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [exporting, setExporting] = useState(false)

  const STATUS_OPTIONS = [
    ['in_production', 'In production'],
    ['passed_qc', 'Passed QC'],
    ['failed_qc', 'Failed QC'],
    ['in_transit', 'In transit'],
    ['delivered', 'Delivered'],
    ['recalled', 'Recalled'],
  ]

  function load() {
    setLoading(true)
    api.listBatches().then(setBatches).catch((e) => setError(e.message)).finally(() => setLoading(false))
  }

  useEffect(load, [])
  useEffect(() => {
    api.listRawMaterials().then(setMaterials).catch(() => {})
  }, [])
  // new filters → back to page 1
  useEffect(() => { setPage(1) }, [query, statusFilter])

  async function exportCsv() {
    setExporting(true)
    setError('')
    try {
      await api.downloadCsv('/export/batches.csv')
    } catch (err) {
      setError(err.message)
    } finally {
      setExporting(false)
    }
  }

  async function handleCreate(e) {
    e.preventDefault()
    setError('')
    try {
      await api.createBatch({
        product_name: form.product_name,
        raw_material_id: form.raw_material_id || null,
        volume_liters: form.volume_liters ? Number(form.volume_liters) : null,
        expiry_date: form.expiry_date ? new Date(form.expiry_date).toISOString() : null,
      })
      setForm({ product_name: '', volume_liters: '', expiry_date: '', raw_material_id: '' })
      setShowForm(false)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const materialLabel = (m) =>
    `${m.material_type} · ${m.quantity_kg != null ? `${m.quantity_kg} kg` : '— lot'}`

  const q = query.trim().toLowerCase()
  const filtered = batches.filter((b) =>
    (!q || b.batch_code.toLowerCase().includes(q) || b.product_name.toLowerCase().includes(q)) &&
    (!statusFilter || b.status === statusFilter)
  )
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const rangeFrom = filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1
  const rangeTo = Math.min(currentPage * PAGE_SIZE, filtered.length)

  const canCreate = CAN_CREATE.includes(session?.user?.role)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold">Batches</h1>
          <p className="text-ink/50 text-sm mt-1">Every production batch and its current status.</p>
        </div>
        {canCreate && (
          <button
            onClick={() => setShowForm((s) => !s)}
            className="bg-teal hover:bg-teal-dark text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            {showForm ? 'Cancel' : '+ New batch'}
          </button>
        )}
      </div>

      {showForm && (
        <form onSubmit={handleCreate} className="bg-surface border border-line rounded-xl p-5 mb-6 grid grid-cols-3 gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1">Product name</label>
            <input required value={form.product_name}
              onChange={(e) => setForm({ ...form, product_name: e.target.value })}
              className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1">Volume (liters)</label>
            <input type="number" step="0.1" value={form.volume_liters}
              onChange={(e) => setForm({ ...form, volume_liters: e.target.value })}
              className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1">Expiry date</label>
            <input type="date" value={form.expiry_date}
              onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
              className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
          </div>
          <div className="col-span-3">
            <label className="block text-xs font-medium text-ink/60 mb-1">Raw material lot (traceability starts here)</label>
            <select value={form.raw_material_id}
              onChange={(e) => setForm({ ...form, raw_material_id: e.target.value })}
              className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal">
              <option value="">— none selected —</option>
              {materials.map((m) => <option key={m.id} value={m.id}>{materialLabel(m)}</option>)}
            </select>
          </div>
          <div className="col-span-3">
            <button type="submit" className="bg-ink text-white px-4 py-2 rounded-md text-sm font-medium">Create batch</button>
          </div>
        </form>
      )}

      <Banner kind="error" onDismiss={() => setError('')}>{error}</Banner>

      <div className="flex gap-3 mb-4">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by batch code or product…"
          className="flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-md border border-line bg-surface px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
        >
          <option value="">All statuses ({batches.length})</option>
          {STATUS_OPTIONS.map(([value, label]) => {
            const n = batches.filter((b) => b.status === value).length
            return <option key={value} value={value}>{label} ({n})</option>
          })}
        </select>
        <button
          onClick={exportCsv}
          disabled={exporting}
          className="shrink-0 border border-line bg-surface rounded-md px-3 py-2 text-sm text-ink/70 hover:border-teal hover:text-teal-dark transition-colors disabled:opacity-50"
          title="Download every batch as a CSV spreadsheet"
        >
          {exporting ? 'Preparing…' : 'Export CSV ↓'}
        </button>
      </div>

      <div className="bg-surface border border-line rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-paper text-ink/50 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-5 py-3 font-medium">Batch code</th>
              <th className="text-left px-5 py-3 font-medium">Product</th>
              <th className="text-left px-5 py-3 font-medium">Produced</th>
              <th className="text-left px-5 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {pageRows.map((b) => (
              <tr key={b.id} className="hover:bg-paper transition-colors cursor-pointer">
                <td className="px-5 py-3">
                  <Link to={`/batches/${b.id}`} className="font-mono text-teal-dark hover:underline">{b.batch_code}</Link>
                </td>
                <td className="px-5 py-3">{b.product_name}</td>
                <td className="px-5 py-3 text-ink/60">{new Date(b.production_date).toLocaleDateString()}</td>
                <td className="px-5 py-3"><StatusBadge status={b.status} /></td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan="4" className="text-center py-8 text-ink/40">
                  {batches.length === 0
                    ? 'No batches yet.'
                    : 'No batches match your search.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {/* pagination */}
        {filtered.length > 0 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-line bg-paper/50 text-xs text-ink/60">
            <span data-testid="page-range">
              Showing {rangeFrom}–{rangeTo} of {filtered.length}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(currentPage - 1)}
                disabled={currentPage <= 1}
                className="px-3 py-1 rounded border border-line bg-surface disabled:opacity-40 hover:enabled:border-teal transition-colors"
              >
                ← Prev
              </button>
              <span className="px-2 py-1">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setPage(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className="px-3 py-1 rounded border border-line bg-surface disabled:opacity-40 hover:enabled:border-teal transition-colors"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
