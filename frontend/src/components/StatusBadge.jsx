import React from 'react'

const STYLES = {
  in_production: 'bg-line text-ink/70',
  passed_qc: 'bg-teal-light text-teal-dark',
  failed_qc: 'bg-danger-light text-danger',
  in_transit: 'bg-amber-light text-amber',
  delivered: 'bg-teal-light text-teal-dark',
  recalled: 'bg-danger text-white',
}

const LABELS = {
  in_production: 'In production',
  passed_qc: 'Passed QC',
  failed_qc: 'Failed QC',
  in_transit: 'In transit',
  delivered: 'Delivered',
  recalled: 'Recalled',
}

export default function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${STYLES[status] || 'bg-line text-ink/70'}`}>
      {LABELS[status] || status}
    </span>
  )
}
