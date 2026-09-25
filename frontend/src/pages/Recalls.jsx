import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

export default function Recalls() {
  const [recalls, setRecalls] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.listRecalls().then(setRecalls).catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <h1 className="font-display text-2xl font-semibold mb-1">Recalls</h1>
      <p className="text-ink/50 text-sm mb-6">A record of every recall and the locations it affected.</p>

      {error && <p className="text-danger text-sm mb-4">{error}</p>}

      <div className="space-y-4">
        {recalls.map((r) => (
          <div key={r.id} className="bg-surface border border-danger/20 rounded-xl p-5">
            <div className="flex items-start justify-between">
              <div>
                <Link to={`/batches/${r.batch_id}`} className="text-sm font-medium text-teal-dark hover:underline">
                  View batch →
                </Link>
                <p className="text-sm mt-1">{r.reason}</p>
              </div>
              <span className="text-xs text-ink/40">{new Date(r.date).toLocaleString()}</span>
            </div>
            {r.affected_locations && (
              <div className="mt-3 pt-3 border-t border-line">
                <p className="text-xs text-ink/40 mb-1">Affected locations</p>
                <div className="flex flex-wrap gap-1.5">
                  {r.affected_locations.split(', ').map((loc) => (
                    <span key={loc} className="text-xs bg-danger-light text-danger px-2 py-1 rounded-full">{loc}</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
        {recalls.length === 0 && (
          <p className="text-sm text-ink/40 text-center py-8 bg-surface border border-line rounded-xl">
            No recalls on record. That's a good thing.
          </p>
        )}
      </div>
    </div>
  )
}
