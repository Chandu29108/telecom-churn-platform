import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { forgotPassword } from '../api'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await forgotPassword(email)
    } finally {
      // Always show the same "sent" state regardless of outcome — the
      // backend already returns a generic response either way (see the
      // audit report's anti-enumeration note), so the UI shouldn't leak
      // more than the API does.
      setSent(true)
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm bg-card border border-black/5 rounded-xl p-8 shadow-sm">
        <div className="font-semibold text-lg">Reset your password</div>
        <div className="text-xs text-muted mb-6">
          Enter your account email and we'll send a reset link if it exists.
        </div>

        {sent ? (
          <div className="text-sm text-muted">
            If an account with that email exists, a password reset link is on its way.
            Check your inbox (and spam folder).
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            <label className="text-sm block">
              <span className="block text-xs font-medium text-muted mb-1">Email</span>
              <input
                type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal"
              />
            </label>
            <button
              type="submit" disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-ink text-white py-2.5 rounded-lg font-medium hover:bg-signal disabled:opacity-40"
            >
              {loading ? <><Loader2 className="animate-spin" size={16} /> Sending…</> : 'Send reset link'}
            </button>
          </form>
        )}

        <div className="text-xs text-muted mt-5 text-center">
          <Link to="/login" className="text-signal font-medium">Back to sign in</Link>
        </div>
      </div>
    </div>
  )
}
