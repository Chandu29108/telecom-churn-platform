import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, User } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import PasswordInput from '../components/PasswordInput'

export default function RegisterPersonal() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ full_name: '', email: '', password: '', account_type: 'personal' })
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const update = (key, val) => setForm((f) => ({ ...f, [key]: val }))

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await register(form)
      navigate('/')
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Please check your details.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm bg-card border border-black/5 rounded-xl p-8 shadow-sm">
        <User className="text-signal" size={22} />
        <div className="font-semibold text-lg mt-2">Create your personal workspace</div>
        <div className="text-xs text-muted mb-6">
          A private, single-seat workspace — no organization name needed. You can upgrade to an
          Organization account later if you need to add teammates.
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Full name</span>
            <input required value={form.full_name} onChange={(e) => update('full_name', e.target.value)}
              className="w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal" />
          </label>
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Email</span>
            <input type="email" required value={form.email} onChange={(e) => update('email', e.target.value)}
              className="w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal" />
          </label>
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Password (min 8 characters)</span>
            <PasswordInput required minLength={8} value={form.password} onChange={(e) => update('password', e.target.value)} />
          </label>

          {error && <div className="text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-3 py-2">{error}</div>}

          <button
            type="submit" disabled={loading}
            className="w-full flex items-center justify-center gap-2 bg-ink text-white py-2.5 rounded-lg font-medium hover:bg-signal disabled:opacity-40"
          >
            {loading ? <><Loader2 className="animate-spin" size={16} /> Creating account…</> : 'Create account'}
          </button>
        </form>

        <div className="text-xs text-muted mt-5 text-center space-y-1">
          <div><Link to="/register" className="text-signal font-medium">← Back to account type</Link></div>
          <div>Already have an account? <Link to="/login" className="text-signal font-medium">Sign in</Link></div>
        </div>
      </div>
    </div>
  )
}
