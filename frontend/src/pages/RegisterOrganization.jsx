import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Building2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import PasswordInput from '../components/PasswordInput'

export default function RegisterOrganization() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  // Owners share invite links as /register?invite=<token>&org=<name>,
  // which redirects here (see RegisterChoice) with the same params. If a
  // valid invite token is present we're joining an existing org, so the
  // org-name field becomes read-only instead of free text — registering
  // with someone else's org NAME is no longer sufficient to join it, and
  // the invite token identifies the target org directly regardless of
  // what's typed here (see backend routers/auth.py).
  const inviteToken = searchParams.get('invite') || ''
  const [form, setForm] = useState({
    full_name: '', email: '', password: '',
    account_type: 'organization',
    organization_name: searchParams.get('org') || '',
    invite_token: inviteToken,
  })
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
        <Building2 className="text-signal" size={22} />
        <div className="font-semibold text-lg mt-2">
          {inviteToken ? 'Join your team' : 'Create your organization'}
        </div>
        <div className="text-xs text-muted mb-6">
          {inviteToken
            ? "You're joining an existing organization via invite link."
            : 'Creating an account with a new organization name makes you its owner. To join an ' +
              "organization that already exists, ask its owner for an invite link — organization " +
              'names alone can no longer be used to join.'}
        </div>

        <form onSubmit={submit} className="space-y-4">
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Full name</span>
            <input required value={form.full_name} onChange={(e) => update('full_name', e.target.value)}
              className="w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal" />
          </label>
          <label className="text-sm block">
            <span className="block text-xs font-medium text-muted mb-1">Organization name</span>
            <input required value={form.organization_name} onChange={(e) => update('organization_name', e.target.value)}
              readOnly={!!inviteToken}
              placeholder="e.g. Acme Telecom"
              className={`w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal ${inviteToken ? 'bg-surface text-muted' : ''}`} />
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
          {!inviteToken && <div><Link to="/register" className="text-signal font-medium">← Back to account type</Link></div>}
          <div>Already have an account? <Link to="/login" className="text-signal font-medium">Sign in</Link></div>
        </div>
      </div>
    </div>
  )
}
