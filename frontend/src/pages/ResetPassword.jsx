import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { resetPassword } from '../api'
import PasswordInput from '../components/PasswordInput'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await resetPassword(token, password)
      setDone(true)
      setTimeout(() => navigate('/login'), 2000)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not reset your password. The link may have expired.')
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface px-4">
        <div className="w-full max-w-sm bg-card border border-black/5 rounded-xl p-8 shadow-sm text-center">
          <div className="font-semibold mb-1">No reset token provided</div>
          <div className="text-xs text-muted mb-5">Use the link from your password reset email.</div>
          <Link to="/forgot-password" className="text-signal font-medium text-sm">Request a new link</Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm bg-card border border-black/5 rounded-xl p-8 shadow-sm">
        <div className="font-semibold text-lg">Choose a new password</div>
        <div className="text-xs text-muted mb-6">
          This will sign you out everywhere else for security.
        </div>

        {done ? (
          <div className="text-sm text-emerald-700">Password updated. Redirecting to sign in…</div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <label className="text-sm block">
              <span className="block text-xs font-medium text-muted mb-1">New password (min 8 characters)</span>
              <PasswordInput
                required minLength={8} value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>

            {error && <div className="text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-3 py-2">{error}</div>}

            <button
              type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-ink text-white py-2.5 rounded-lg font-medium hover:bg-signal disabled:opacity-40"
            >
              {loading ? <><Loader2 className="animate-spin" size={16} /> Updating…</> : 'Update password'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
