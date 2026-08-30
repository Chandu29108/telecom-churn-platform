import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'

const stack = [
  ['Frontend', 'React + Vite + Tailwind'],
  ['Backend', 'FastAPI'],
  ['ML', 'Gradient Boosting (scikit-learn)'],
  ['Database', 'PostgreSQL'],
  ['Deployment', 'Render + Vercel + Docker'],
]

export default function Home() {
  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-1 text-signal mb-6">
        <span className="signal-mark"><span></span><span></span><span></span><span></span></span>
        <span className="text-xs font-semibold uppercase tracking-widest ml-2">Live scoring, not a static report</span>
      </div>
      <h1 className="text-4xl font-extrabold tracking-tight leading-tight">
        Give it a usage file.<br />Get a churn model back.
      </h1>
      <p className="mt-4 text-muted text-lg leading-relaxed">
        Upload customer usage data and this app trains a real Gradient Boosting model on it,
        scores every customer into risk tiers, and generates a dashboard, business insights,
        and retention recommendations — the same pipeline used in the source analysis
        (99,999 customers, ROC-AUC 0.946), running fresh on your data.
      </p>
      <Link to="/upload" className="inline-flex items-center gap-2 mt-8 bg-ink text-white px-5 py-3 rounded-lg font-medium hover:bg-signal transition-colors">
        Upload a dataset <ArrowRight size={16} />
      </Link>

      <div className="mt-16">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted mb-3">Stack</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {stack.map(([k, v]) => (
            <div key={k} className="bg-card border border-black/5 rounded-lg p-3">
              <div className="text-[11px] text-muted uppercase">{k}</div>
              <div className="text-sm font-medium font-mono">{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
