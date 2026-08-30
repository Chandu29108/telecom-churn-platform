import { useNavigate } from 'react-router-dom'
import { Lightbulb } from 'lucide-react'
import { useAnalysis } from '../context/AnalysisContext'

export default function Insights() {
  const { result } = useAnalysis()
  const navigate = useNavigate()

  if (!result) {
    return (
      <div className="max-w-md">
        <h1 className="text-2xl font-bold">Insights</h1>
        <p className="text-muted mt-2">No analysis yet — upload a dataset first.</p>
        <button onClick={() => navigate('/upload')} className="mt-4 bg-ink text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-signal">
          Go to Upload
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold">Business Insights</h1>
      <p className="text-muted mt-1 text-sm">Generated directly from this dataset's EDA and model results — not generic text.</p>

      <div className="mt-6 space-y-4">
        {(result.insights || []).map((ins, i) => (
          <div key={i} className="bg-card border border-black/5 rounded-xl p-5 flex gap-4">
            <div className="w-9 h-9 rounded-lg bg-signal/10 text-signal flex items-center justify-center shrink-0">
              <Lightbulb size={18} />
            </div>
            <div>
              <div className="font-semibold">{ins.title}</div>
              <p className="text-sm text-muted mt-1 leading-relaxed">{ins.body}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
