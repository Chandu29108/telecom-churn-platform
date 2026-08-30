import { useNavigate } from 'react-router-dom'
import { useState, Fragment } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { useAnalysis } from '../context/AnalysisContext'
import KpiCard from '../components/KpiCard'
import RiskBadge from '../components/RiskBadge'

const TIER_COLORS = { Critical: '#E5484D', High: '#F2994A', Medium: '#F2C94C', Low: '#27AE60' }

export default function Dashboard() {
  const { result } = useAnalysis()
  const navigate = useNavigate()

  if (!result) {
    return (
      <div className="max-w-md">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted mt-2">No analysis yet — upload a dataset to populate this view.</p>
        <button onClick={() => navigate('/upload')} className="mt-4 bg-ink text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-signal">
          Go to Upload
        </button>
      </div>
    )
  }

  const { eda_summary: eda = {}, metrics = {}, feature_importance = [], risk_counts = {}, top_high_risk_customers = [] } = result

  const riskData = Object.entries(risk_counts).map(([tier, count]) => ({ tier, count }))
  const tenureData = Object.entries(eda.churn_by_tenure || {}).map(([bucket, rate]) => ({ bucket, rate: +(rate * 100).toFixed(1) }))
  const rechargeData = Object.entries(eda.churn_by_recharge || {}).map(([bucket, rate]) => ({ bucket, rate: +(rate * 100).toFixed(1) }))
  const featData = [...feature_importance].reverse().slice(-12)

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <span className="text-xs text-muted font-mono">{result.filename} · {result.row_count?.toLocaleString()} rows</span>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
        <KpiCard label="Total Customers" value={eda.total_customers?.toLocaleString() ?? '—'} />
        <KpiCard label="Churn Rate" value={eda.churn_rate ? `${(eda.churn_rate * 100).toFixed(1)}%` : '—'} accent="text-tier-critical" />
        <KpiCard label="Predicted High-Risk" value={((risk_counts.Critical || 0) + (risk_counts.High || 0)).toLocaleString()} sublabel="Critical + High tiers" />
        <KpiCard label="Avg Monthly Charges" value={eda.avg_monthly_charges ? `₹${eda.avg_monthly_charges}` : '—'} />
        <KpiCard label="Active Customers" value={eda.active_customers?.toLocaleString() ?? '—'} accent="text-tier-low" />
        <KpiCard label="Avg Tenure (days)" value={eda.avg_tenure_days ?? '—'} />
        <KpiCard label="Model ROC-AUC" value={metrics.roc_auc ?? '—'} accent="text-signal" />
        <KpiCard label="Model Recall" value={metrics.recall ? `${(metrics.recall * 100).toFixed(1)}%` : '—'} />
      </div>

      <div className="grid md:grid-cols-2 gap-5 mt-8">
        <ChartCard title="Customer Risk Distribution">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={riskData} dataKey="count" nameKey="tier" innerRadius={55} outerRadius={85} paddingAngle={2}>
                {riskData.map((d) => <Cell key={d.tier} fill={TIER_COLORS[d.tier] || '#999'} />)}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Top Feature Importance">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={featData} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="feature" tick={{ fontSize: 10 }} width={110} />
              <Tooltip />
              <Bar dataKey="importance" fill="#12B8A6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {tenureData.length > 0 && (
          <ChartCard title="Churn by Tenure Group">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={tenureData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="%" />
                <Tooltip />
                <Bar dataKey="rate" fill="#E5484D" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {rechargeData.length > 0 && (
          <ChartCard title="Churn by Recharge Bucket">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={rechargeData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} unit="%" />
                <Tooltip />
                <Bar dataKey="rate" fill="#F2994A" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {metrics.roc_curve && (
          <ChartCard title="ROC Curve">
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={metrics.roc_curve.fpr.map((f, i) => ({ fpr: +f.toFixed(3), tpr: +metrics.roc_curve.tpr[i].toFixed(3) }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="fpr" tick={{ fontSize: 11 }} label={{ value: 'FPR', position: 'insideBottom', offset: -3, fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} label={{ value: 'TPR', angle: -90, position: 'insideLeft', fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="tpr" stroke="#12B8A6" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </ChartCard>
        )}

        {metrics.confusion_matrix && (
          <ChartCard title="Confusion Matrix">
            <ConfusionMatrix cm={metrics.confusion_matrix} />
          </ChartCard>
        )}
      </div>

      {top_high_risk_customers.length > 0 && (
        <div className="mt-8">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm font-semibold">High-Risk Customer Table (top 50)</div>
            <div className="text-[11px] text-muted">Click a row to see why (SHAP)</div>
          </div>
          <HighRiskTable customers={top_high_risk_customers} />
        </div>
      )}
    </div>
  )
}

function HighRiskTable({ customers }) {
  const [expanded, setExpanded] = useState(null)

  return (
    <div className="bg-card border border-black/5 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-black/[0.03] text-xs uppercase text-muted">
          <tr>
            <th className="text-left px-4 py-2.5 font-medium">Customer ID</th>
            <th className="text-left px-4 py-2.5 font-medium">Probability</th>
            <th className="text-left px-4 py-2.5 font-medium">Risk Tier</th>
            <th className="text-left px-4 py-2.5 font-medium w-8"></th>
          </tr>
        </thead>
        <tbody>
          {customers.slice(0, 12).map((c, i) => {
            const hasFactors = c.top_factors && c.top_factors.length > 0
            const isOpen = expanded === i
            return (
              <Fragment key={i}>
                <tr
                  className={`border-t border-black/5 ${hasFactors ? 'cursor-pointer hover:bg-black/[0.02]' : ''}`}
                  onClick={() => hasFactors && setExpanded(isOpen ? null : i)}
                >
                  <td className="px-4 py-2.5 font-mono">{c.customer_id}</td>
                  <td className="px-4 py-2.5 font-mono">{(c.churn_probability * 100).toFixed(1)}%</td>
                  <td className="px-4 py-2.5"><RiskBadge tier={c.risk_tier} /></td>
                  <td className="px-4 py-2.5 text-muted">
                    {hasFactors && (isOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />)}
                  </td>
                </tr>
                {isOpen && hasFactors && (
                  <tr className="border-t border-black/5 bg-black/[0.015]">
                    <td colSpan={4} className="px-4 py-3">
                      <div className="text-[11px] font-medium text-muted uppercase mb-2">
                        Why this customer is at risk (SHAP)
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {c.top_factors.map((f, fi) => (
                          <span
                            key={fi}
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
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ChartCard({ title, children }) {
  return (
    <div className="bg-card border border-black/5 rounded-xl p-5">
      <div className="text-sm font-semibold mb-2">{title}</div>
      {children}
    </div>
  )
}

function ConfusionMatrix({ cm }) {
  const [[tn, fp], [fn, tp]] = cm
  const cell = (label, val, tone) => (
    <div className={`rounded-lg p-4 text-center ${tone}`}>
      <div className="text-[11px] uppercase text-muted">{label}</div>
      <div className="font-mono text-xl font-semibold mt-1">{val}</div>
    </div>
  )
  return (
    <div className="grid grid-cols-2 gap-2">
      {cell('True Negative', tn, 'bg-tier-low/10')}
      {cell('False Positive', fp, 'bg-tier-medium/10')}
      {cell('False Negative', fn, 'bg-tier-critical/10')}
      {cell('True Positive', tp, 'bg-signal/10')}
    </div>
  )
}
