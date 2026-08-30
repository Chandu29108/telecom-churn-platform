import { useNavigate } from 'react-router-dom'
import { useAnalysis } from '../context/AnalysisContext'

const PRIORITY_STYLE = {
  High: 'bg-tier-critical/10 text-tier-critical',
  Medium: 'bg-tier-high/10 text-tier-high',
  Low: 'bg-black/5 text-muted',
}

export default function Recommendations() {
  const { result } = useAnalysis()
  const navigate = useNavigate()

  if (!result) {
    return (
      <div className="max-w-md">
        <h1 className="text-2xl font-bold">Recommendations</h1>
        <p className="text-muted mt-2">No analysis yet — upload a dataset first.</p>
        <button onClick={() => navigate('/upload')} className="mt-4 bg-ink text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-signal">
          Go to Upload
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold">Actionable Recommendations</h1>
      <p className="text-muted mt-1 text-sm">Ranked by priority, derived from this dataset's risk tier sizes and feature importances.</p>

      <div className="mt-6 space-y-4">
        {(result.recommendations || []).map((rec, i) => (
          <div key={i} className="bg-card border border-black/5 rounded-xl p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="font-semibold">{rec.recommendation}</div>
              <span className={`text-[11px] font-semibold px-2 py-1 rounded-full shrink-0 ${PRIORITY_STYLE[rec.priority]}`}>
                {rec.priority} priority
              </span>
            </div>
            <div className="mt-3 text-sm">
              <span className="text-muted font-medium">Why it works: </span>
              <span className="text-muted">{rec.why_it_works}</span>
            </div>
            <div className="mt-1.5 text-sm">
              <span className="text-muted font-medium">Expected impact: </span>
              <span className="text-muted">{rec.expected_impact}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
