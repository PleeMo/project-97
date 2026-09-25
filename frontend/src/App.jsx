import React, { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { getSession } from './api'

import Login from './pages/Login.jsx'
import Verify from './pages/Verify.jsx'
import DashboardHome from './pages/DashboardHome.jsx'
import Batches from './pages/Batches.jsx'
import BatchDetail from './pages/BatchDetail.jsx'
import Recalls from './pages/Recalls.jsx'
import Suppliers from './pages/Suppliers.jsx'
import Alerts from './pages/Alerts.jsx'
import PrintQr from './pages/PrintQr.jsx'
import Layout from './components/Layout.jsx'

function useSession() {
  const [session, setSession] = useState(getSession())
  useEffect(() => {
    const onStorage = () => setSession(getSession())
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])
  return [session, setSession]
}

function RequireAuth({ session, children }) {
  if (!session) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const [session, setSession] = useSession()

  return (
    <Routes>
      {/* Public — no login needed. This is what a consumer hits after scanning a QR code. */}
      <Route path="/verify/:batchCode?" element={<Verify />} />

      <Route path="/login" element={<Login onLogin={setSession} />} />

      {/* Print-friendly: rendered outside the app chrome so only labels print. */}
      <Route
        path="/print/qr/:id"
        element={
          <RequireAuth session={session}>
            <PrintQr />
          </RequireAuth>
        }
      />

      <Route
        path="/"
        element={
          <RequireAuth session={session}>
            <Layout session={session} onLogout={() => setSession(null)} />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardHome session={session} />} />
        <Route path="batches" element={<Batches session={session} />} />
        <Route path="batches/:id" element={<BatchDetail session={session} />} />
        <Route path="suppliers" element={<Suppliers session={session} />} />
        <Route path="recalls" element={<Recalls session={session} />} />
        <Route path="alerts" element={<Alerts session={session} />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
