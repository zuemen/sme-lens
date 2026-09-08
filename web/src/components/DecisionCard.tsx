import type { Decision, ScreenResult } from '../api/types'
import { Panel } from './Panel'
import { RiskBadge } from './RiskBadge'

const DECISION_COLOR: Record<Decision, string> = {
  block: 'var(--color-risk-high)',
  review: 'var(--color-risk-med)',
  pass: 'var(--color-risk-low)',
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl">{value}</div>
    </div>
  )
}

export function DecisionCard({ result }: { result: ScreenResult }) {
  return (
    <Panel title="審查決策">
      <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
        <div>
          <div className="text-xs text-muted">綜合風險分數</div>
          <div className="mt-1">
            <RiskBadge
              score={result.risk_score}
              label={result.risk_score >= 0.7 ? 'high' : result.risk_score >= 0.4 ? 'medium' : 'low'}
            />
          </div>
        </div>
        <Metric label="自身結構分數" value={result.self_score.toFixed(2)} />
        <Metric label="關聯風險分數" value={result.association_score.toFixed(2)} />
        <div>
          <div className="text-xs text-muted">處置建議</div>
          <div
            className="mt-1 text-lg font-semibold"
            style={{ color: DECISION_COLOR[result.decision] }}
          >
            {result.decision_zh}
          </div>
        </div>
      </div>

      <p
        className="mt-5 rounded border-l-2 pl-4 text-sm leading-relaxed text-ink"
        style={{ borderColor: DECISION_COLOR[result.decision] }}
      >
        {result.narrative_zh}
      </p>
    </Panel>
  )
}
