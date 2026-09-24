// Owner-only: mint invite links so teammates can join THIS org. Replaces
// the old "register with the same org name" behaviour, which let anyone
// who knew an org's name join it — see backend routers/auth.py.
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Loader2, Copy, Check, ShieldAlert, CreditCard, Sparkles } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { createInvite, listInvites, getBillingStatus, createCheckout } from '../api'

export default function Team() {
  const { user } = useAuth()
  const [invites, setInvites] = useState([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState(null)
  const [copiedId, setCopiedId] = useState(null)
  const [searchParams] = useSearchParams()
  const [billing, setBilling] = useState(null)
  const [billingLoading, setBillingLoading] = useState(true)
  const [upgrading, setUpgrading] = useState(false)
  const [billingError, setBillingError] = useState(null)
  const justUpgraded = searchParams.get('upgraded') === 'true'

  const refreshBilling = () => {
    setBillingLoading(true)
    getBillingStatus()
      .then((res) => setBilling(res.data))
      .catch(() => {}) // non-critical — page still works if this fails
      .finally(() => setBillingLoading(false))
  }

  useEffect(() => {
    if (user?.role === 'owner' && user?.account_type !== 'personal') refreshBilling()
  }, [user])

  const handleUpgrade = async () => {
    setUpgrading(true)
    setBillingError(null)
    try {
      const res = await createCheckout()
      window.location.href = res.data.checkout_url
    } catch (err) {
      setBillingError(err.response?.data?.detail || 'Could not start checkout.')
      setUpgrading(false)
    }
  }

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
      <div className="mb-10">
        <div className="font-semibold text-lg mb-1">Billing</div>
        <div className="text-xs text-muted mb-4">
          Pro unlocks higher upload limits, more seats, and priority copilot access.
        </div>

        {justUpgraded && (
          <div className="flex items-center gap-2 text-sm text-signal bg-signal/10 rounded-lg px-3 py-2 mb-4">
            <Sparkles size={16} /> Thanks! It can take a minute for your Pro plan to activate — refresh if it doesn't show below right away.
          </div>
        )}

        {billingError && (
          <div className="text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-3 py-2 mb-4">{billingError}</div>
        )}

        {billingLoading ? (
          <div className="text-sm text-muted">Loading…</div>
        ) : billing?.plan === 'pro' ? (
          <div className="flex items-center gap-2 bg-card border border-black/5 rounded-xl px-4 py-3 text-sm">
            <CreditCard size={16} className="text-signal" />
            <span className="font-medium">You're on the Pro plan.</span>
            {billing.subscription_status && (
              <span className="text-muted">({billing.subscription_status})</span>
            )}
          </div>
        ) : (
          <button
            onClick={handleUpgrade}
            disabled={upgrading}
            className="flex items-center gap-2 bg-ink text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-signal disabled:opacity-40"
          >
            {upgrading ? <><Loader2 className="animate-spin" size={16} /> Starting checkout…</> : 'Upgrade to Pro — $49/mo'}
          </button>
        )}
      </div>

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
