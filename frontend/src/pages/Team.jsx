// Owner-only: mint invite links so teammates can join THIS org. Replaces
// the old "register with the same org name" behaviour, which let anyone
// who knew an org's name join it — see backend routers/auth.py.
import { useEffect, useState } from 'react'
import { Loader2, Copy, Check, ShieldAlert } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { createInvite, listInvites } from '../api'

export default function Team() {
  const { user } = useAuth()
  const [invites, setInvites] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [copiedId, setCopiedId] = useState(null)

  const refresh = () => {
    setLoading(true)
    listInvites()
      .then((res) => setInvites(res.data))
      .catch((err) => setError(err.response?.data?.detail || 'Could not load invites.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (user?.role === 'owner') refresh()
    else setLoading(false)
  }, [user])

  const handleCreate = async () => {
    setCreating(true)
    setError(null)
    try {
      await createInvite()
      refresh()
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create invite.')
    } finally {
      setCreating(false)
    }
  }

  const inviteLink = (token) =>
    `${window.location.origin}/register?invite=${token}&org=${encodeURIComponent(user?.organization_name || '')}`

  const copy = (invite) => {
    navigator.clipboard.writeText(inviteLink(invite.token))
    setCopiedId(invite.id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  if (user && user.role !== 'owner') {
    return (
      <div className="flex items-center gap-2 text-sm text-muted bg-card border border-black/5 rounded-xl p-6">
        <ShieldAlert size={16} /> Only your organization's owner can invite teammates.
      </div>
    )
  }

  if (user && user.account_type === 'personal') {
    return (
      <div className="flex items-center gap-2 text-sm text-muted bg-card border border-black/5 rounded-xl p-6">
        <ShieldAlert size={16} /> Personal accounts are single-seat and don't support team invites.
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      <div className="font-semibold text-lg mb-1">Invite teammates</div>
      <div className="text-xs text-muted mb-6">
        Anyone with a valid, unused invite link can join your organization as a member. Links
        expire after 7 days and can only be used once.
      </div>

      <button
        onClick={handleCreate}
        disabled={creating}
        className="mb-6 flex items-center gap-2 bg-ink text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-signal disabled:opacity-40"
      >
        {creating ? <><Loader2 className="animate-spin" size={16} /> Creating…</> : 'Generate invite link'}
      </button>

      {error && <div className="text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-3 py-2 mb-4">{error}</div>}

      {loading ? (
        <div className="text-sm text-muted">Loading…</div>
      ) : invites.length === 0 ? (
        <div className="text-sm text-muted">No invites yet.</div>
      ) : (
        <div className="space-y-2">
          {invites.map((inv) => (
            <div key={inv.id} className="flex items-center justify-between bg-card border border-black/5 rounded-lg px-4 py-3">
              <div className="min-w-0">
                <div className="text-sm font-mono truncate">{inviteLink(inv.token)}</div>
                <div className="text-xs text-muted mt-0.5">
                  {inv.used ? 'Used' : `Expires ${new Date(inv.expires_at).toLocaleDateString()}`}
                </div>
              </div>
              <button
                onClick={() => copy(inv)}
                disabled={inv.used}
                className="shrink-0 ml-3 text-muted hover:text-ink disabled:opacity-30"
                title="Copy link"
              >
                {copiedId === inv.id ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
