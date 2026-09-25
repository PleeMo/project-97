export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function getToken() {
  return localStorage.getItem('tc_token')
}

async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const errJson = await res.json()
      detail = errJson.detail || detail
    } catch (_) {}
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // auth
  login: (email, password) => request('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  register: (payload) => request('/auth/register', { method: 'POST', body: payload, auth: false }),
  me: () => request('/auth/me'),

  // suppliers
  listSuppliers: () => request('/suppliers'),
  supplierStats: () => request('/suppliers/stats'),
  createSupplier: (payload) => request('/suppliers', { method: 'POST', body: payload }),
  listRawMaterials: () => request('/suppliers/raw-materials'),
  createRawMaterial: (payload) => request('/suppliers/raw-materials', { method: 'POST', body: payload }),

  // batches
  listBatches: () => request('/batches'),
  getBatch: (id) => request(`/batches/${id}`),
  createBatch: (payload) => request('/batches', { method: 'POST', body: payload }),
  batchTimeline: (id) => request(`/batches/${id}/timeline`),

  // quality
  createQualityTest: (payload) => request('/quality-tests', { method: 'POST', body: payload }),
  getTestsForBatch: (batchId) => request(`/quality-tests/batch/${batchId}`),
  predictRisk: (params) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined)
    ).toString()
    return request(`/quality-tests/predict?${q}`, { method: 'POST' })
  },
  modelInfo: () => request('/quality-tests/model-info'),
  retrain: () => request('/quality-tests/retrain', { method: 'POST' }),
  uploadCertificate: async (testId, file) => {
    const form = new FormData()
    form.append('file', file)
    const headers = {}
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${API_URL}/quality-tests/${testId}/certificate`, {
      method: 'POST', headers, body: form,
    })
    if (!res.ok) {
      let detail = res.statusText
      try { detail = (await res.json()).detail || detail } catch (_) {}
      throw new Error(detail)
    }
    return res.json()
  },
  downloadCertificate: async (testId) => {
    const headers = {}
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${API_URL}/quality-tests/${testId}/certificate`, { headers })
    if (!res.ok) throw new Error('No certificate attached')
    const blob = await res.blob()
    const disposition = res.headers.get('content-disposition') || ''
    const match = disposition.match(/filename="?([^";]+)"?/)
    return { blob, filename: match ? match[1] : 'certificate' }
  },

  // supply chain
  createEvent: (payload) => request('/supply-chain/events', { method: 'POST', body: payload }),
  getEventsForBatch: (batchId) => request(`/supply-chain/events/batch/${batchId}`),

  // qr
  getQr: (batchId) => request(`/qr/${batchId}`),

  // cold chain
  getColdChain: (batchId) => request(`/cold-chain/batch/${batchId}`),
  simulateColdChain: (batchId, payload) =>
    request(`/cold-chain/simulate/${batchId}`, { method: 'POST', body: payload }),
  addTemperatureReading: (payload) =>
    request('/cold-chain/readings', { method: 'POST', body: payload }),

  // anti-counterfeit
  scanAnalysis: (batchId) => request(`/scans/batch/${batchId}`),

  // public verify (no auth)
  verify: (batchCode, tz) => {
    const q = tz ? `?tz=${encodeURIComponent(tz)}` : ''
    return request(`/verify/${batchCode}${q}`, { auth: false })
  },

  // recalls
  listRecalls: () => request('/recalls'),
  triggerRecall: (payload) => request('/recalls', { method: 'POST', body: payload }),

  // dashboard + analytics
  summary: () => request('/dashboard/summary'),
  analytics: () => request('/dashboard/analytics'),

  // health (public)
  health: () => request('/health', { auth: false }),

  // alerts
  alerts: () => request('/alerts'),

  // CSV exports (authenticated download → browser Save-As)
  downloadCsv: async (path) => {
    const headers = {}
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${API_URL}${path}`, { headers })
    if (!res.ok) throw new Error(`Export failed (${res.status})`)
    const blob = await res.blob()
    const disposition = res.headers.get('content-disposition') || ''
    const match = disposition.match(/filename="?([^";]+)"?/)
    const filename = match ? match[1] : 'export.csv'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
    return filename
  },
}

export function saveSession(token, user) {
  localStorage.setItem('tc_token', token)
  localStorage.setItem('tc_user', JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem('tc_token')
  localStorage.removeItem('tc_user')
}

export function getSession() {
  const token = getToken()
  const userRaw = localStorage.getItem('tc_user')
  if (!token || !userRaw) return null
  try {
    return { token, user: JSON.parse(userRaw) }
  } catch {
    return null
  }
}
