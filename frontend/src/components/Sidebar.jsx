import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Upload, Lightbulb, ListChecks, UserSearch, Home, LogOut, Users } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const baseLinks = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/upload', label: 'Upload & Analyze', icon: Upload },
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/insights', label: 'Insights', icon: Lightbulb },
  { to: '/recommendations', label: 'Recommendations', icon: ListChecks },
  { to: '/prediction', label: 'Predict a Customer', icon: UserSearch },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  // Inviting teammates changes who can see this org's data, so it's
  // restricted to owners — see backend deps.require_owner. Personal
  // accounts are single-seat by definition (server rejects invite
  // creation there — see POST /api/auth/invites), so the link is hidden
  // rather than shown-then-erroring.
  const links = (user?.role === 'owner' && user?.account_type !== 'personal')
    ? [...baseLinks, { to: '/team', label: 'Invite Team', icon: Users }]
    : baseLinks

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <aside className="w-64 shrink-0 bg-ink text-white/90 min-h-screen flex flex-col">
      <div className="px-6 py-6 flex items-center gap-3 border-b border-white/10">
        <span className="signal-mark text-signal">
          <span></span><span></span><span></span><span></span>
        </span>
        <div>
          <div className="font-semibold leading-tight">Churn Intelligence</div>
          <div className="text-xs text-white/50">Telecom Retention Platform</div>
        </div>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive ? 'bg-signal/15 text-signal' : 'text-white/70 hover:bg-white/5 hover:text-white'
              }`
            }
          >
            <Icon size={17} strokeWidth={2} />
            {label}
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="px-3 py-3 border-t border-white/10">
          <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-white/5">
            <div className="min-w-0">
              <div className="text-xs font-medium truncate">{user.full_name}</div>
              <div className="text-[11px] text-white/40 truncate">
                {user.account_type === 'personal' ? 'Personal workspace' : `${user.role} · ${user.organization_name}`}
              </div>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="text-white/50 hover:text-white shrink-0 ml-2"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      )}

      <div className="px-6 py-4 text-[11px] text-white/40 border-t border-white/10">
        Model: Gradient Boosting · ROC-AUC 0.946
      </div>
    </aside>
  )
}
