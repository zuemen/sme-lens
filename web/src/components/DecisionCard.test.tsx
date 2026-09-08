import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ScreenResult } from '../api/types'
import { DecisionCard } from './DecisionCard'

const blocked: ScreenResult = {
  target: 'TOtcOut01',
  amount_usdt: 500000,
  risk_score: 0.7307,
  self_score: 0.3268,
  association_score: 0.6,
  decision: 'block',
  decision_zh: '暫緩出金並啟動人工審查',
  narrative_zh: '敘事',
  associations: [
    {
      risky_node: 'TAggregator01',
      distance: 2,
      path: ['TAggregator01', 'TMule03', 'TOtcOut01'],
      motifs: ['fan_in', 'fan_out', 'gather_scatter'],
    },
  ],
  evidence: null,
  str_draft_zh: '草稿',
  graph: {
    nodes: [],
    edges: [],
    meta: {
      node_count: 0,
      total_node_count: 0,
      edge_count: 0,
      truncated: false,
      story_zh: null,
      degraded: false,
    },
  },
  highlight_path: ['TAggregator01', 'TMule03', 'TOtcOut01'],
}

describe('DecisionCard', () => {
  it('顯示綜合風險與處置建議', () => {
    render(<DecisionCard result={blocked} />)
    expect(screen.getByText('0.73')).toBeDefined()
    expect(screen.getByText('暫緩出金並啟動人工審查')).toBeDefined()
  })

  it('拆解自身分數與關聯分數——這是 Demo 的論點', () => {
    render(<DecisionCard result={blocked} />)
    expect(screen.getByText('0.33')).toBeDefined()
    expect(screen.getByText('0.60')).toBeDefined()
  })

  it('放行時顯示放行文案', () => {
    render(
      <DecisionCard
        result={{ ...blocked, decision: 'pass', decision_zh: '予以放行', risk_score: 0.0962 }}
      />,
    )
    expect(screen.getByText('予以放行')).toBeDefined()
  })
})
