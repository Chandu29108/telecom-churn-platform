const COLORS = {
  Critical: 'bg-tier-critical/10 text-tier-critical',
  High: 'bg-tier-high/10 text-tier-high',
  Medium: 'bg-tier-medium/10 text-yellow-700',
  Low: 'bg-tier-low/10 text-tier-low',
}

export default function RiskBadge({ tier }) {
  return (
    <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${COLORS[tier] || 'bg-gray-100 text-gray-600'}`}>
      {tier}
    </span>
  )
}
