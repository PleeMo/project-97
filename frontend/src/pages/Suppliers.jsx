import React, { useEffect, useState } from 'react'
import { api } from '../api'
import Banner from '../components/Banner.jsx'

const CAN_EDIT = ['admin', 'producer']

export default function Suppliers({ session }) {
  const [suppliers, setSuppliers] = useState([])
  const [materials, setMaterials] = useState([])
  const [stats, setStats] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showSupplierForm, setShowSupplierForm] = useState(false)
  const [showMaterialForm, setShowMaterialForm] = useState(false)
  const [supplierForm, setSupplierForm] = useState({ name: '', location: '', contact: '' })
  const [materialForm, setMaterialForm] = useState({ supplier_id: '', material_type: '', quantity_kg: '' })

  const canEdit = CAN_EDIT.includes(session?.user?.role)

  function load() {
    api.listSuppliers().then(setSuppliers).catch((e) => setError(e.message))
    api.listRawMaterials().then(setMaterials).catch(() => {})
    api.supplierStats().then(setStats).catch(() => {})
  }

  useEffect(load, [])

  const statFor = (id) => stats.find((s) => s.supplier_id === id)

  async function submitSupplier(e) {
    e.preventDefault()
    setError('')
    try {
      await api.createSupplier({
        name: supplierForm.name,
        location: supplierForm.location || null,
        contact: supplierForm.contact || null,
      })
      setSupplierForm({ name: '', location: '', contact: '' })
      setShowSupplierForm(false)
      setNotice('Supplier added.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function submitMaterial(e) {
    e.preventDefault()
    setError('')
    try {
      await api.createRawMaterial({
        supplier_id: materialForm.supplier_id,
        material_type: materialForm.material_type,
        quantity_kg: materialForm.quantity_kg ? Number(materialForm.quantity_kg) : null,
      })
      setMaterialForm({ supplier_id: suppliers[0]?.id || '', material_type: '', quantity_kg: '' })
      setShowMaterialForm(false)
      setNotice('Raw material lot received.')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const supplierName = (id) => suppliers.find((s) => s.id === id)?.name || '—'

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold">Suppliers & raw materials</h1>
        <p className="text-ink/50 text-sm mt-1">
          Where every batch begins — supplier lots flow straight into production.
        </p>
      </div>

      <Banner kind="error" onDismiss={() => setError('')}>{error}</Banner>
      <Banner kind="success" onDismiss={() => setNotice('')}>{notice}</Banner>

      <div className="grid grid-cols-2 gap-6">
        {/* Suppliers */}
        <div className="bg-surface border border-line rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium text-sm">Suppliers</h2>
            {canEdit && (
              <button
                onClick={() => setShowSupplierForm((s) => !s)}
                className="text-xs font-medium text-teal-dark hover:underline"
              >
                {showSupplierForm ? 'Cancel' : '+ Add supplier'}
              </button>
            )}
          </div>

          {showSupplierForm && (
            <form onSubmit={submitSupplier} className="space-y-2 mb-4 pb-4 border-b border-line">
              <input placeholder="Name" required value={supplierForm.name}
                onChange={(e) => setSupplierForm({ ...supplierForm, name: e.target.value })}
                className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
              <input placeholder="Location" value={supplierForm.location}
                onChange={(e) => setSupplierForm({ ...supplierForm, location: e.target.value })}
                className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
              <input placeholder="Contact" value={supplierForm.contact}
                onChange={(e) => setSupplierForm({ ...supplierForm, contact: e.target.value })}
                className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
              <button type="submit" className="w-full bg-ink text-white text-xs font-medium rounded-md py-2">
                Save supplier
              </button>
            </form>
          )}

          <div className="divide-y divide-line">
            {suppliers.map((s) => {
              const st = statFor(s.id)
              return (
                <div key={s.id} className="py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">{s.name}</p>
                      <p className="text-xs text-ink/50">{s.location || '—'} · {s.contact || 'no contact'}</p>
                    </div>
                    {st?.recalls > 0 && (
                      <span className="shrink-0 text-[10px] bg-danger-light text-danger px-1.5 py-0.5 rounded font-medium">
                        {st.recalls} recall{st.recalls > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                  {st && (
                    <div className="flex flex-wrap gap-1.5 mt-2" data-testid="supplier-stats">
                      <span className="text-[10px] bg-paper rounded px-1.5 py-0.5">
                        {st.lots} lot{st.lots === 1 ? '' : 's'}
                      </span>
                      <span className="text-[10px] bg-paper rounded px-1.5 py-0.5">
                        {st.batches_linked} batch{st.batches_linked === 1 ? '' : 'es'}
                      </span>
                      {st.total_quantity_kg != null && (
                        <span className="text-[10px] bg-paper rounded px-1.5 py-0.5">
                          {st.total_quantity_kg} kg
                        </span>
                      )}
                      {st.qc_pass_rate != null ? (
                        <span className={`text-[10px] rounded px-1.5 py-0.5 ${
                          st.qc_pass_rate >= 0.8 ? 'bg-teal-light text-teal-dark'
                          : st.qc_pass_rate >= 0.5 ? 'bg-amber-light text-amber'
                          : 'bg-danger-light text-danger'
                        }`}>
                          QC pass {Math.round(st.qc_pass_rate * 100)}%
                        </span>
                      ) : (
                        <span className="text-[10px] bg-paper text-ink/40 rounded px-1.5 py-0.5">
                          untested
                        </span>
                      )}
                      {st.avg_risk_score != null && (
                        <span className={`text-[10px] rounded px-1.5 py-0.5 ${
                          st.avg_risk_score >= 50 ? 'bg-danger-light text-danger'
                          : st.avg_risk_score >= 25 ? 'bg-amber-light text-amber'
                          : 'bg-teal-light text-teal-dark'
                        }`}>
                          risk {st.avg_risk_score}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            {suppliers.length === 0 && (
              <p className="py-4 text-xs text-ink/40">No suppliers yet.</p>
            )}
          </div>
        </div>

        {/* Raw materials */}
        <div className="bg-surface border border-line rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-medium text-sm">Raw material lots</h2>
            {canEdit && (
              <button
                onClick={() => setShowMaterialForm((s) => !s)}
                className="text-xs font-medium text-teal-dark hover:underline"
                disabled={suppliers.length === 0}
              >
                {showMaterialForm ? 'Cancel' : '+ Receive lot'}
              </button>
            )}
          </div>

          {showMaterialForm && (
            <form onSubmit={submitMaterial} className="space-y-2 mb-4 pb-4 border-b border-line">
              <select required value={materialForm.supplier_id}
                onChange={(e) => setMaterialForm({ ...materialForm, supplier_id: e.target.value })}
                className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal">
                <option value="">Select supplier…</option>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <input placeholder="Material type (e.g. Passion Fruit)" required value={materialForm.material_type}
                onChange={(e) => setMaterialForm({ ...materialForm, material_type: e.target.value })}
                className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
              <input placeholder="Quantity (kg)" type="number" step="0.1" value={materialForm.quantity_kg}
                onChange={(e) => setMaterialForm({ ...materialForm, quantity_kg: e.target.value })}
                className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal" />
              <button type="submit" className="w-full bg-ink text-white text-xs font-medium rounded-md py-2">
                Receive lot
              </button>
            </form>
          )}

          <div className="divide-y divide-line">
            {materials.map((m) => (
              <div key={m.id} className="py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">{m.material_type}</p>
                  <p className="text-xs text-ink/50">{supplierName(m.supplier_id)}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-mono">{m.quantity_kg != null ? `${m.quantity_kg} kg` : '—'}</p>
                  <p className="text-xs text-ink/40">{new Date(m.received_date).toLocaleDateString()}</p>
                </div>
              </div>
            ))}
            {materials.length === 0 && (
              <p className="py-4 text-xs text-ink/40">No raw material lots yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
