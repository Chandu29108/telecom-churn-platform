// Single place that knows about the backend base URL, so switching from
// local docker-compose to the deployed Render URL is a one-line env change.
//
// Auth model (Phase 1 hardening): the access token is short-lived (15 min)
// and lives ONLY in memory (a module-level variable), never localStorage —
// a future XSS bug can no longer read a long-lived credential straight out
// of storage. A rotating refresh token backs it, delivered as an httpOnly
// cookie the backend sets on login/register/refresh, so no JS on this page
// (ours or an attacker's) can read it at all. `withCredentials: true` is
// what makes the browser attach/receive that cookie on cross-origin
// requests (frontend and backend are different origins in production).
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
// Must match backend/app/config.py::CSRF_HEADER_NAME.
const CSRF_HEADER_NAME = 'X-CSRF-Token'

export const api = axios.create({ baseURL: API_BASE, withCredentials: true })

let accessToken = null
export const getAccessToken = () => accessToken
export const setAccessToken = (token) => { accessToken = token }
export const clearAccessToken = () => { accessToken = null }

// CSRF token for the two cookie-authenticated endpoints (refresh, logout).
// Delivered once in the login/register/refresh JSON response body and
// kept in memory only, same pattern as the access token — never
// localStorage, never read from a cookie (the CSRF cookie lives on the
// backend's domain and is invisible to this page's document.cookie
// anyway, since frontend and backend are different origins).
let csrfToken = null
export const setCsrfToken = (token) => { csrfToken = token }
export const clearCsrfToken = () => { csrfToken = null }

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  if (csrfToken && (config.url?.includes('/api/auth/refresh') || config.url?.includes('/api/auth/logout'))) {
    config.headers[CSRF_HEADER_NAME] = csrfToken
  }
  return config
})

// On a 401, try exactly once to silently refresh the access token using
// the httpOnly refresh cookie, then retry the original request. If the
// refresh itself fails (expired/revoked/logged out elsewhere), give up and
// bounce to login — this mirrors the old localStorage-401 behaviour but
// now goes through the refresh flow first instead of assuming the session
// is dead immediately.
let refreshPromise = null

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    const isAuthEndpoint = original?.url?.includes('/api/auth/login')
      || original?.url?.includes('/api/auth/register')
      || original?.url?.includes('/api/auth/refresh')

    if (err.response?.status === 401 && !original._retried && !isAuthEndpoint) {
      original._retried = true
      try {
        if (!refreshPromise) {
          refreshPromise = api.post('/api/auth/refresh').finally(() => { refreshPromise = null })
        }
        const refreshRes = await refreshPromise
        setAccessToken(refreshRes.data.access_token)
        setCsrfToken(refreshRes.data.csrf_token)
        original.headers.Authorization = `Bearer ${refreshRes.data.access_token}`
        return api(original)
      } catch (refreshErr) {
        clearAccessToken()
        clearCsrfToken()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject(refreshErr)
      }
    }
    return Promise.reject(err)
  }
)

// --- Auth -------------------------------------------------------------- //
export const registerUser = (payload) => api.post('/api/auth/register', payload)

export const loginUser = (email, password) => {
  // The backend's /api/auth/login endpoint is an OAuth2PasswordRequestForm
  // (form-encoded, field name "username") so it stays compatible with
  // FastAPI's built-in /docs "Authorize" button.
  const form = new URLSearchParams()
  form.append('username', email)
  form.append('password', password)
  return api.post('/api/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
}

export const logoutUser = () => api.post('/api/auth/logout')
export const refreshSession = () => api.post('/api/auth/refresh')
export const getMe = () => api.get('/api/auth/me')

export const verifyEmail = (token) => api.post('/api/auth/verify-email', { token })
export const resendVerification = (email) => api.post('/api/auth/resend-verification', { email })
export const forgotPassword = (email) => api.post('/api/auth/forgot-password', { email })
export const resetPassword = (token, new_password) =>
  api.post('/api/auth/reset-password', { token, new_password })

// --- Org invites (owner only) -------------------------------------------- //
export const createInvite = (expiresHours = 168) =>
  api.post('/api/auth/invites', { expires_hours: expiresHours })
export const listInvites = () => api.get('/api/auth/invites')

// --- Billing (owner-only checkout; status readable by any member) --------- //
export const getBillingStatus = () => api.get('/api/billing/status')
export const createCheckout = () => api.post('/api/billing/checkout')

// --- Audit log (owner only) ----------------------------------------------- //
export const listAuditLogs = (params = {}) => api.get('/api/audit', { params })

// --- Analysis ------------------------------------------------------------ //
export const uploadAndAnalyze = (file) => {
  const form = new FormData()
  form.append('file', file)
  // No onUploadProgress-driven percentage anymore — the response now
  // comes back almost immediately (a queued job id), so upload progress
  // isn't the interesting number; job stage/progress (polled below) is.
  return api.post('/api/analysis/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// The backend blocks unverified accounts from starting new analyses
// (see deps.require_verified) with a 403 whose detail string always
// contains this phrase — checked explicitly here so the UI can show a
// dedicated "verify your email" prompt instead of a generic error.
export const isUnverifiedEmailError = (err) =>
  err?.response?.status === 403 &&
  (err?.response?.data?.detail || '').toLowerCase().includes('verify your email')

export const getJob = (jobId) => api.get(`/api/analysis/jobs/${jobId}`)
export const listJobs = () => api.get('/api/analysis/jobs')
export const retryJob = (jobId) => api.post(`/api/analysis/jobs/${jobId}/retry`)
export const cancelJob = (jobId) => api.post(`/api/analysis/jobs/${jobId}/cancel`)

export const listRuns = () => api.get('/api/analysis/runs')
export const getRun = (id) => api.get(`/api/analysis/runs/${id}`)
export const predictSingle = (payload) => api.post('/api/predict', payload)

// --- Copilot ------------------------------------------------------------- //
export const askCopilot = (question, runId) => api.post('/api/copilot', { question, run_id: runId ?? null })
