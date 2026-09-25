import React, { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api, clearSession } from '../api'

const navItem = ({ isActive }) =>
  `block px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
    isActive ? 'bg-teal text-white' : 'text-ink/70 hover:bg-teal-light hover:text-teal-dark'
  }`

export default function Layout({ session, onLogout }) {
  const navigate = useNavigate()
  const user = session?.user
  const [alertCount, setAlertCount] = useState(0)

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

  function logout() {
    clearSession()
    onLogout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex bg-paper">
      <aside className="w-64 shrink-0 border-r border-line bg-surface flex flex-col">
        <div className="px-6 py-6 border-b border-line">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🧪</span>
            <span className="font-display text-xl font-semibold tracking-tight">TraceCert</span>
          </div>
          <p className="text-xs text-ink/50 mt-1">Beverage QA & Traceability</p>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          <NavLink to="/" end className={navItem}>Overview</NavLink>
          <NavLink to="/batches" className={navItem}>Batches</NavLink>
          {canManageSupply && <NavLink to="/suppliers" className={navItem}>Suppliers</NavLink>}
          <NavLink to="/recalls" className={navItem}>Recalls</NavLink>
          <NavLink to="/alerts" className={navItem}>
            {({ isActive }) => (
              <span className={`flex items-center justify-between ${isActive ? '' : ''}`}>
                <span>Alerts</span>
                {alertCount > 0 && (
                  <span className="min-w-[1.25rem] px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-danger text-white text-center">
                    {alertCount}
                  </span>
                )}
              </span>
            )}
          </NavLink>
          <NavLink to="/verify" className={navItem} title="Public consumer verification — no login needed">
            Verify a product ↗
          </NavLink>
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

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
