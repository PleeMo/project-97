import React, { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api, clearSession, API_URL } from '../api'
import Logo from './Logo.jsx'

const navItem = ({ isActive }) =>
  `block px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
    isActive ? 'bg-teal text-white' : 'text-ink/70 hover:bg-teal-light hover:text-teal-dark'
  }`

function NavSection({ label, children }) {
  return (
    <div>
      <p className="px-4 pt-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink/35">
        {label}
      </p>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

export default function Layout({ session, onLogout }) {
  const navigate = useNavigate()
  const user = session?.user
  const [alertCount, setAlertCount] = useState(0)
  const [navOpen, setNavOpen] = useState(false)
  const [apiUp, setApiUp] = useState(null)   // null = still checking

  const canManageSupply = ['admin', 'producer'].includes(user?.role)

  useEffect(() => {
    let alive = true
    const load = () => api.alerts()
      .then((a) => alive && setAlertCount(a.length))
      .catch(() => {})
    load()
    const t = setInterval(load, 60_000)   // keep the badge fresh
    return () => { alive = false; clearInterval(t) }
  }, [])

  useEffect(() => {
    let alive = true
    const ping = () => api.health()
      .then((h) => alive && setApiUp(h.status === 'ok'))
      .catch(() => alive && setApiUp(false))
    ping()
    const t = setInterval(ping, 60_000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  function logout() {
    clearSession()
    onLogout()
    navigate('/login')
  }

  const closeNav = () => setNavOpen(false)

  return (
    <div className="min-h-screen bg-paper">
      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-30 flex items-center justify-between px-4 py-3 bg-surface border-b border-line">
        <div className="flex items-center gap-2">
          <Logo className="w-7 h-7" />
          <span className="font-display text-lg font-semibold tracking-tight">TraceCert</span>
        </div>
        <button
          type="button"
          onClick={() => setNavOpen((v) => !v)}
          aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
          aria-expanded={navOpen}
          className="w-9 h-9 flex items-center justify-center rounded-md border border-line text-ink/70 hover:bg-teal-light transition-colors"
        >
          {navOpen ? '✕' : '☰'}
        </button>
      </header>

      {/* Mobile backdrop */}
      {navOpen && (
        <div
          className="fixed inset-0 bg-ink/40 z-30 md:hidden"
          onClick={closeNav}
          aria-hidden="true"
        />
      )}

      <div className="flex min-h-screen">
        <aside
          className={`fixed md:static inset-y-0 left-0 z-40 w-64 shrink-0 border-r border-line bg-surface flex flex-col transform transition-transform duration-200 ${
            navOpen ? 'translate-x-0' : '-translate-x-full'
          } md:translate-x-0`}
        >
          <div className="px-6 py-6 border-b border-line">
            <div className="flex items-center gap-2.5">
              <Logo className="w-9 h-9" />
              <div>
                <span className="font-display text-xl font-semibold tracking-tight block leading-tight">
                  TraceCert
                </span>
                <p className="text-[11px] text-ink/50">Beverage QA &amp; Traceability</p>
              </div>
            </div>
          </div>

          <nav className="flex-1 px-3 py-3 space-y-4 overflow-y-auto">
            <NavSection label="Workspace">
              <NavLink to="/" end className={navItem} onClick={closeNav}>Overview</NavLink>
              <NavLink to="/batches" className={navItem} onClick={closeNav}>Batches</NavLink>
              {canManageSupply && (
                <NavLink to="/suppliers" className={navItem} onClick={closeNav}>Suppliers</NavLink>
              )}
              <NavLink to="/recalls" className={navItem} onClick={closeNav}>Recalls</NavLink>
              <NavLink to="/alerts" className={navItem} onClick={closeNav}>
                {({ isActive }) => (
                  <span className="flex items-center justify-between">
                    <span>Alerts</span>
                    {alertCount > 0 && (
                      <span className="min-w-[1.25rem] px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-danger text-white text-center">
                        {alertCount}
                      </span>
                    )}
                  </span>
                )}
              </NavLink>
            </NavSection>

            <NavSection label="Public">
              <NavLink
                to="/verify"
                className={navItem}
                onClick={closeNav}
                title="Public consumer verification — no login needed"
              >
                Verify a product ↗
              </NavLink>
            </NavSection>
          </nav>

          <div className="px-4 py-4 border-t border-line">
            <div className="text-sm font-medium">{user?.name}</div>
            <div className="text-xs text-ink/50 capitalize">{user?.role} · {user?.organization}</div>
            <button
              onClick={logout}
              className="mt-3 w-full text-left text-xs font-medium text-danger hover:underline"
            >
              Sign out
            </button>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto min-w-0">
          <div className="max-w-6xl mx-auto px-4 md:px-8 py-6 md:py-8">
            <Outlet />

            <footer className="mt-12 pt-4 border-t border-line flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink/40">
              <span>TraceCert v1.0.0 — beverage quality verification &amp; traceability</span>
              <span className="flex items-center gap-4">
                <span className="flex items-center gap-1.5" title={apiUp === null ? 'Checking API…' : apiUp ? 'API responding normally' : 'API unreachable'}>
                  <span
                    className={`w-2 h-2 rounded-full ${
                      apiUp === null ? 'bg-ink/30' : apiUp ? 'bg-teal' : 'bg-danger'
                    }`}
                  />
                  {apiUp === null ? 'Checking API…' : apiUp ? 'API online' : 'API unreachable'}
                </span>
                <a
                  href={`${API_URL}/docs`}
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-teal-dark transition-colors"
                >
                  API docs ↗
                </a>
              </span>
            </footer>
          </div>
        </main>
      </div>
    </div>
  )
}
