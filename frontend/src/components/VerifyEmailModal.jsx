// A focused modal, not a toast, on purpose: this blocks an action the
// user just tried to take (running an analysis) and the two things they
// can actually do about it (resend, or go verify) need a deliberate
// click, not something that auto-dismisses after a few seconds.
import { MailWarning } from 'lucide-react'
import { useState } from 'react'
import { resendVerification } from '../api'
import { useAuth } from '../context/AuthContext'

export default function VerifyEmailModal({ onClose }) {
  const { user } = useAuth()
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  const resend = async () => {
    setSending(true)
    try {
      await resendVerification(user?.email)
      setSent(true)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-xl p-6">
        <MailWarning className="text-amber-500" size={28} />
        <div className="font-semibold text-lg mt-3">Verify your email to continue</div>
        <p className="text-sm text-muted mt-1.5">
          You need to verify {user?.email ? <span className="font-medium">{user.email}</span> : 'your email address'} before
          you can run an analysis. Check your inbox for the verification link.
        </p>

        {sent ? (
          <div className="text-sm text-emerald-700 mt-4">Verification email sent — check your inbox.</div>
        ) : (
          <button
            onClick={resend}
            disabled={sending}
            className="mt-4 w-full bg-ink text-white py-2.5 rounded-lg font-medium hover:bg-signal disabled:opacity-40 text-sm"
          >
            {sending ? 'Sending…' : 'Resend verification email'}
          </button>
        )}

        <button
          onClick={onClose}
          className="mt-3 w-full text-xs text-muted hover:text-ink"
        >
          Close
        </button>
      </div>
    </div>
  )
}
