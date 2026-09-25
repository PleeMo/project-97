import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'

const COPIES = 8 // labels per sheet (A4 fits 3×4 comfortably; 8 keeps them large)

/**
 * Printable QR label sheet for a batch — print it out and stick one label on
 * every case/pallet. Each label carries the batch code and the public
 * verification URL the QR points at. The chrome (header, buttons) is hidden
 * when printing.
 */
export default function PrintQr() {
  const { id } = useParams()
  const [batch, setBatch] = useState(null)
  const [qr, setQr] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getBatch(id).then(setBatch).catch((e) => setError(e.message))
    api.getQr(id).then(setQr).catch(() => {})
  }, [id])

  if (error) {
    return (
      <div className="min-h-screen bg-paper p-8">
        <p className="text-danger text-sm">{error}</p>
        <Link to="/batches" className="text-teal-dark text-sm hover:underline">← Back to batches</Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-paper p-6 print:p-0 print:bg-white">
      <header className="flex items-center justify-between mb-5 print:hidden">
        <div>
          <h1 className="font-display text-xl font-semibold">
            QR label sheet{batch ? ` — ${batch.batch_code}` : ''}
          </h1>
          <p className="text-ink/50 text-sm mt-1">
            One label per case or pallet · scanning opens the public verification page.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            to={`/batches/${id}`}
            className="border border-line bg-surface rounded-md px-3 py-2 text-sm text-ink/70 hover:border-teal transition-colors"
          >
            ← Back
          </Link>
          <button
            onClick={() => window.print()}
            className="bg-teal hover:bg-teal-dark text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            Print sheet 🖨
          </button>
        </div>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 print:grid-cols-3 print:gap-3">
        {Array.from({ length: COPIES }).map((_, i) => (
          <div
            key={i}
            className="bg-white border border-line rounded-lg p-4 text-center break-inside-avoid print:rounded-none print:border-gray-300"
          >
            {qr?.image_base64 ? (
              <img src={qr.image_base64} alt="QR code" className="w-36 h-36 mx-auto" />
            ) : (
              <div className="w-36 h-36 mx-auto flex items-center justify-center text-ink/30 text-xs">
                Loading…
              </div>
            )}
            <p className="font-mono text-sm mt-2 font-medium">{batch?.batch_code || '—'}</p>
            <p className="text-xs text-ink/60 truncate">{batch?.product_name || ''}</p>
            <p className="text-[10px] text-ink/40 mt-1.5">Scan to verify authenticity</p>
            <p className="text-[10px] text-ink/40 font-mono">{qr?.verify_path || '/verify/…'}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
