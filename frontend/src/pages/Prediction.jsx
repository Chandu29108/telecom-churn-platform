import { useState } from 'react'
import { predictSingle } from '../api'
import RiskBadge from '../components/RiskBadge'
import { Loader2 } from 'lucide-react'

const FIELDS = [
  ['total_ic_mou_8', 'Incoming minutes — Aug'],
  ['total_ic_mou_7', 'Incoming minutes — Jul'],
  ['total_ic_mou_6', 'Incoming minutes — Jun'],
  ['total_rech_amt_8', 'Recharge amount (₹) — Aug'],
  ['total_rech_amt_7', 'Recharge amount (₹) — Jul'],
  ['total_rech_amt_6', 'Recharge amount (₹) — Jun'],
  ['arpu_8', 'ARPU (₹) — Aug'],
  ['arpu_7', 'ARPU (₹) — Jul'],
  ['arpu_6', 'ARPU (₹) — Jun'],
  ['last_day_rch_amt_8', 'Last recharge amount — Aug'],
  ['roam_og_mou_8', 'Roaming outgoing minutes — Aug'],
  ['aon', 'Age on network (days)'],
]

const DEFAULTS = { total_ic_mou_8: 20, total_ic_mou_7: 120, total_ic_mou_6: 130,
  total_rech_amt_8: 50, total_rech_amt_7: 200, total_rech_amt_6: 220,
  arpu_8: 40, arpu_7: 190, arpu_6: 200, last_day_rch_amt_8: 0, roam_og_mou_8: 0, aon: 300 }

export default function Prediction() {
  const [form, setForm] = useState(DEFAULTS)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const update = (key, val) => setForm((f) => ({ ...f, [key]: Number(val) }))

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await predictSingle(form)
      setResult(res.data)
    } catch (err) {
      setError('Prediction failed. Check the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold">Predict a Customer</h1>
      <p className="text-muted mt-1 text-sm">
        Uses the most recently trained model from an uploaded dataset. If none exists yet,
        falls back to a transparent weighted heuristic (clearly labelled in the result) built
        from the same top features the notebook's model ranked highest.
      </p>

      <form onSubmit={submit} className="grid sm:grid-cols-2 gap-4 mt-6">
        {FIELDS.map(([key, label]) => (
          <label key={key} className="text-sm">
            <span className="block text-xs font-medium text-muted mb-1">{label}</span>
            <input
              type="number"
              value={form[key]}
              onChange={(e) => update(key, e.target.value)}
              className="w-full border border-black/10 rounded-lg px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-signal"
            />
          </label>
        ))}
        <button
          type="submit"
          disabled={loading}
          className="sm:col-span-2 mt-2 flex items-center justify-center gap-2 bg-ink text-white py-3 rounded-lg font-medium hover:bg-signal disabled:opacity-40"
        >
          {loading ? <><Loader2 className="animate-spin" size={16} /> Scoring…</> : 'Predict churn risk'}
        </button>
      </form>

      {error && <div className="mt-4 text-sm text-tier-critical bg-tier-critical/10 rounded-lg px-4 py-3">{error}</div>}

      {result && (
        <div className="mt-6 bg-card border border-black/5 rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-muted uppercase">Churn Probability</div>
              <div className="kpi-value text-3xl mt-1">{(result.churn_probability * 100).toFixed(1)}%</div>
            </div>
            <RiskBadge tier={result.risk_tier} />
          </div>
          <div className="grid grid-cols-2 gap-4 mt-5 text-sm">
            <div><span className="text-muted">Churn flag: </span><span className="font-medium">{result.churn_flag ? 'YES' : 'NO'}</span></div>
            <div><span className="text-muted">Confidence: </span><span className="font-medium">{(result.confidence * 100).toFixed(0)}%</span></div>
          </div>
          <div className="mt-4 text-sm">
            <span className="text-muted">Recommended action: </span>
            <span className="font-medium">{result.recommended_action}</span>
          </div>

          {result.top_factors && result.top_factors.length > 0 && (
            <div className="mt-5 pt-5 border-t border-black/5">
              <div className="text-[11px] font-medium text-muted uppercase mb-2">
                Why ({result.explanation_mode === 'shap' ? 'SHAP explanation' : 'heuristic breakdown'})
              </div>
              <div className="flex flex-wrap gap-2">
                {result.top_factors.map((f, i) => (
                  <span
                    key={i}
                    className={`text-xs px-2.5 py-1 rounded-full font-mono ${
                      f.direction === 'increases_risk'
                        ? 'bg-tier-critical/10 text-tier-critical'
                        : 'bg-tier-low/10 text-tier-low'
                    }`}
                  >
                    {f.feature} ({f.impact > 0 ? '+' : ''}{f.impact})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
