import { Link, useSearchParams, Navigate } from 'react-router-dom'
import { User, Building2, ArrowRight } from 'lucide-react'

// Landing point for /register — splits into the two real signup forms
// rather than cramming a type toggle into one form, since the fields
// that matter (organization name vs. none) genuinely differ, and a
// dedicated choice screen reads as more deliberate/professional than a
// small radio toggle buried above the fields.
export default function RegisterChoice() {
  const [searchParams] = useSearchParams()
  // Invite links (/register?invite=<token>&org=<name>) always join an
  // existing organization regardless of account type — skip the choice
  // screen entirely and go straight to the organization form, which
  // already knows how to render the invite state.
  if (searchParams.get('invite')) {
    return <Navigate to={`/register/organization?${searchParams.toString()}`} replace />
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <div className="font-semibold text-2xl">Create your account</div>
          <div className="text-sm text-muted mt-1.5">Choose the kind of workspace you need.</div>
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <Link
            to="/register/personal"
            className="group bg-card border border-black/5 rounded-xl p-6 hover:border-signal hover:shadow-sm transition-all"
          >
            <User className="text-signal" size={26} />
            <div className="font-semibold text-lg mt-3">Personal</div>
            <div className="text-sm text-muted mt-1.5 leading-relaxed">
              A private, single-seat workspace. Best for individual analysts, students, and
              trying the product out on your own data.
            </div>
            <div className="text-xs font-medium text-signal mt-4 flex items-center gap-1">
              Continue <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
            </div>
          </Link>

          <Link
            to="/register/organization"
            className="group bg-card border border-black/5 rounded-xl p-6 hover:border-signal hover:shadow-sm transition-all"
          >
            <Building2 className="text-signal" size={26} />
            <div className="font-semibold text-lg mt-3">Organization</div>
            <div className="text-sm text-muted mt-1.5 leading-relaxed">
              A shared workspace for your team — invite teammates, share analyses, and manage
              access from one account.
            </div>
            <div className="text-xs font-medium text-signal mt-4 flex items-center gap-1">
              Continue <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
            </div>
          </Link>
        </div>

        <div className="text-xs text-muted mt-6 text-center">
          Already have an account? <Link to="/login" className="text-signal font-medium">Sign in</Link>
        </div>
      </div>
    </div>
  )
}
