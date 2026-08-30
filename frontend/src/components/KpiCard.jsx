export default function KpiCard({ label, value, sublabel, accent = 'text-ink' }) {
  return (
    <div className="bg-card border border-black/5 rounded-xl p-5 shadow-sm">
      <div className="text-xs font-medium text-muted uppercase tracking-wide">{label}</div>
      <div className={`kpi-value text-2xl mt-2 ${accent}`}>{value}</div>
      {sublabel && <div className="text-xs text-muted mt-1">{sublabel}</div>}
    </div>
  )
}
