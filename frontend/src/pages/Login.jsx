import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api, saveSession } from '../api'

const DEMO_ACCOUNTS = [
  { role: 'Admin', email: 'admin@demo.com' },
  { role: 'Producer / QC', email: 'producer@demo.com' },
  { role: 'Distributor', email: 'distributor@demo.com' },
  { role: 'Retailer', email: 'retailer@demo.com' },
]

export default function Login({ onLogin }) {
  const [mode, setMode] = useState('login') // 'login' | 'register'
  const [email, setEmail] = useState('producer@demo.com')
  const [password, setPassword] = useState('password123')
  const [name, setName] = useState('')
  const [role, setRole] = useState('producer')
  const [organization, setOrganization] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = mode === 'login'
        ? await api.login(email, password)
        : await api.register({
            name,
            email,
            password,
            role,
            organization: organization || null,
          })
      saveSession(data.access_token, data.user)
      onLogin({ token: data.access_token, user: data.user })
      navigate('/')
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <span className="text-3xl">🧪</span>
          <h1 className="font-display text-2xl font-semibold mt-2">TraceCert</h1>
          <p className="text-ink/50 text-sm mt-1">
            {mode === 'login' ? 'Sign in to manage batches and quality checks' : 'Create your traceability account'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="bg-surface border border-line rounded-xl p-6 space-y-4">
          {mode === 'register' && (
            <>
              <div>
                <label className="block text-xs font-medium text-ink/60 mb-1">Full name</label>
                <input
                  value={name} onChange={(e) => setName(e.target.value)} required
                  className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink/60 mb-1">Role</label>
                <select
                  value={role} onChange={(e) => setRole(e.target.value)}
                  className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
                >
                  <option value="producer">Producer / QC</option>
                  <option value="distributor">Distributor</option>
                  <option value="retailer">Retailer</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-ink/60 mb-1">Organization</label>
                <input
                  value={organization} onChange={(e) => setOrganization(e.target.value)}
                  className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
                />
              </div>
            </>
          )}
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1">Email</label>
            <input
              type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
              className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-ink/60 mb-1">Password</label>
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
              className="w-full rounded-md border border-line px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal"
            />
          </div>
          {error && <p className="text-danger text-sm">{error}</p>}
          <button
            type="submit" disabled={loading}
            className="w-full bg-teal hover:bg-teal-dark text-white rounded-md py-2.5 text-sm font-medium transition-colors disabled:opacity-60"
          >
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-xs text-ink/50 mt-4">
          {mode === 'login' ? (
            <>New here?{' '}
              <button className="text-teal-dark hover:underline" onClick={() => { setMode('register'); setError('') }}>
                Create an account
              </button>
            </>
          ) : (
            <>Already registered?{' '}
              <button className="text-teal-dark hover:underline" onClick={() => { setMode('login'); setError('') }}>
                Sign in
              </button>
            </>
          )}
        </p>

        <div className="mt-6 bg-teal-light/60 border border-line rounded-lg p-4 text-xs text-ink/70">
          <p className="font-medium mb-2">Demo accounts (password: password123)</p>
          <ul className="space-y-1">
            {DEMO_ACCOUNTS.map((a) => (
              <li key={a.email} className="flex justify-between">
                <span>{a.role}</span>
                <button
                  type="button"
                  className="font-mono text-teal-dark hover:underline"
                  onClick={() => setEmail(a.email)}
                >
                  {a.email}
                </button>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-center text-xs text-ink/40 mt-6">
          Consumer? No login needed —{' '}
          <Link to="/verify" className="text-teal-dark hover:underline">verify a product here</Link>.
        </p>
      </div>
    </div>
  )
}
