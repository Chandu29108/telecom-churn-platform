import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import PasswordInput from '../components/PasswordInput'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Login failed. Check your email and password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm bg-card border border-black/5 rounded-xl p-8 shadow-sm">
        <div className="font-semibold text-lg">Churn Intelligence</div>
        <div className="text-xs text-muted mb-6">Sign in to your organization's workspace</div>

        <form onSubmit={submit} className="space-y-4">
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Email</span>
            <input
              type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal"
            />
          </label>
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Password</span>
            <PasswordInput
              required value={password} onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <div className="text-right -mt-2">
            <Link to="/forgot-password" className="text-xs text-signal font-medium">Forgot password?</Link>
          </div>

          {error && <div className="text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-3 py-2">{error}</div>}

          <button
            type="submit" disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-ink text-white py-2.5 rounded-lg font-medium hover:bg-signal disabled:opacity-40"
          >
            {loading ? <><Loader2 className="animate-spin" size={16} /> Signing in…</> : 'Sign in'}
          </button>
        </form>

        <div className="text-xs text-muted mt-5 text-center">
          No account yet? <Link to="/register" className="text-signal font-medium">Create one</Link>
        </div>
      </div>
    </div>
  )
}
