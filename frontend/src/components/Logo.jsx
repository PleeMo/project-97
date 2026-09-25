import React from 'react'

/**
 * TraceCert brand mark: a droplet with a check — quality verified, origin
 * traced. Rendered inline so it scales crisply and needs no asset pipeline.
 */
export default function Logo({ className = 'w-8 h-8' }) {
  return (
    <svg viewBox="0 0 64 64" className={className} role="img" aria-label="TraceCert logo">
      <rect width="64" height="64" rx="15" fill="#1F6F5C" />
      <path
        d="M32 12C40 24 46 30 46 37a14 14 0 0 1-28 0c0-7 6-13 14-25z"
        fill="#FFFFFF"
        opacity="0.95"
      />
      <path
        d="M26 37l4.5 4.5L41 31"
        fill="none"
        stroke="#1F6F5C"
        strokeWidth="4.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
