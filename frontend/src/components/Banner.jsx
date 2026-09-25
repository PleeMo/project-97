import React from 'react'

const TONES = {
  error: 'bg-danger-light border-danger/30 text-danger',
  success: 'bg-teal-light border-teal/30 text-teal-dark',
  info: 'bg-surface border-line text-ink/70',
}

const ICONS = { error: '⚠', success: '✓', info: 'ℹ' }

/**
 * Standardised inline alert. Renders nothing when `children` is empty, so
 * pages can write `<Banner kind="error">{error}</Banner>` unconditionally.
 */
export default function Banner({ kind = 'info', children, onDismiss }) {
  if (!children) return null
  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className={`flex items-start gap-2 border rounded-lg px-4 py-2.5 text-sm mb-4 ${TONES[kind] || TONES.info}`}
    >
      <span aria-hidden="true" className="mt-0.5 shrink-0">{ICONS[kind] || ICONS.info}</span>
      <span className="flex-1">{children}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss message"
          className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
        >
          ×
        </button>
      )}
    </div>
  )
}
