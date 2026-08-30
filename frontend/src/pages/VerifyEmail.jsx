import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { verifyEmail, resendVerification } from '../api'

export default function VerifyEmail() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [status, setStatus] = useState(token ? 'verifying' : 'missing') // verifying | success | error | missing
  const [message, setMessage] = useState('')
  const [resendEmail, setResendEmail] = useState('')
  const [resendSent, setResendSent] = useState(false)

  useEffect(() => {
    if (!token) return
    verifyEmail(token)
      .then((res) => {
        setStatus('success')
        setMessage(res.data.message)
      })
      .catch((err) => {
        setStatus('error')
        setMessage(err.response?.data?.detail || 'This verification link is invalid or has expired.')
      })
  }, [token])

  const submitResend = async (e) => {
    e.preventDefault()
    await resendVerification(resendEmail)
    setResendSent(true)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-sm bg-card border border-black/5 rounded-xl p-8 shadow-sm text-center">
        {status === 'verifying' && (
          <>
            <Loader2 className="animate-spin mx-auto mb-3" size={28} />
            <div className="text-sm text-muted">Verifying your email…</div>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle2 className="mx-auto mb-3 text-emerald-600" size={32} />
            <div className="font-semibold mb-1">Email verified</div>
            <div className="text-xs text-muted mb-5">{message}</div>
            <Link to="/" className="text-signal font-medium text-sm">Go to dashboard</Link>
          </>
        )}

        {(status === 'error' || status === 'missing') && (
          <>
            <XCircle className="mx-auto mb-3 text-tier-critical" size={32} />
            <div className="font-semibold mb-1">Verification link invalid or expired</div>
            <div className="text-xs text-muted mb-5">
              {status === 'missing' ? 'No verification token was provided.' : message}
            </div>

            {resendSent ? (
              <div className="text-xs text-muted">
                If that email exists and isn't verified yet, a new link is on its way.
              </div>
            ) : (
              <form onSubmit={submitResend} className="space-y-3 text-left">
                <label className="text-sm block">
                  <span className="block text-xs font-medium text-muted mb-1">Resend to</span>
                  <input
                    type="email" required value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    className="w-full border border-black/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-signal"
                  />
                </label>
                <button
                  type="submit"
                  className="w-full bg-ink text-white py-2.5 rounded-lg font-medium hover:bg-signal text-sm"
                >
                  Resend verification email
                </button>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}
