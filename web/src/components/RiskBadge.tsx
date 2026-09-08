import type { RiskLabel } from '../api/types'

const LABEL_ZH: Record<RiskLabel, string> = {
  high: '高風險',
  medium: '中風險',
  low: '低風險',
}

const LABEL_COLOR: Record<RiskLabel, string> = {
  high: 'var(--color-risk-high)',
  medium: 'var(--color-risk-med)',
  low: 'var(--color-risk-low)',
}

export function riskColor(label: RiskLabel): string {
  return LABEL_COLOR[label]
}

export function RiskBadge({ score, label }: { score: number; label: RiskLabel }) {
  return (
    <span className="inline-flex items-baseline gap-2">
      <span className="tabular text-3xl font-semibold" style={{ color: riskColor(label) }}>
        {score.toFixed(2)}
      </span>
      <span className="text-sm" style={{ color: riskColor(label) }}>
        {LABEL_ZH[label]}
      </span>
    </span>
  )
}
