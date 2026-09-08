import { describe, expect, it } from 'vitest'
import type { GraphPayload } from '../api/types'
import { nodeColor, toElements } from './elements'

const payload: GraphPayload = {
  nodes: [
    {
      id: 'TAggregator01',
      role: 'aggregator',
      role_zh: '集資主錢包',
      score: 0.91,
      label: 'high',
      is_motif_center: true,
      pagerank: 0.04,
      narrative_zh: '敘事',
    },
    {
      id: 'TMule03',
      role: 'mule',
      role_zh: '車手地址',
      score: 0.42,
      label: 'medium',
      is_motif_center: false,
      pagerank: 0.02,
      narrative_zh: '敘事',
    },
    {
      id: 'TOtcOut01',
      role: 'otc',
      role_zh: 'OTC 出金地址',
      score: 0.33,
      label: 'low',
      is_motif_center: false,
      pagerank: 0.03,
      narrative_zh: '敘事',
    },
  ],
  edges: [
    { source: 'TAggregator01', target: 'TMule03', amount: 86000, timestamp: 1760000600 },
    { source: 'TMule03', target: 'TOtcOut01', amount: 86000, timestamp: 1760001200 },
  ],
  meta: {
    node_count: 3,
    total_node_count: 3,
    edge_count: 2,
    truncated: false,
    story_zh: null,
    degraded: false,
  },
}

describe('toElements', () => {
  it('每個節點與每條邊各產生一個元素', () => {
    expect(toElements(payload, { scheme: 'role' })).toHaveLength(5)
  })

  it('節點帶入標籤與角色供樣式使用', () => {
    const node = toElements(payload, { scheme: 'role' }).find((el) => el.data.id === 'TMule03')
    expect(node?.data.roleZh).toBe('車手地址')
    expect(node?.data.score).toBe(0.42)
  })

  it('命中圖樣的節點被標記，供工作台加外框', () => {
    const node = toElements(payload, { scheme: 'risk' }).find(
      (el) => el.data.id === 'TAggregator01',
    )
    expect(node?.data.motifCenter).toBe(true)
  })

  it('高亮路徑上的邊被標記', () => {
    const elements = toElements(payload, {
      scheme: 'role',
      highlightPath: ['TAggregator01', 'TMule03', 'TOtcOut01'],
    })
    expect(elements.filter((el) => el.data.highlighted === true)).toHaveLength(2)
  })

  it('不在路徑上的邊不被標記', () => {
    const elements = toElements(payload, {
      scheme: 'role',
      highlightPath: ['TMule03', 'TOtcOut01'],
    })
    expect(elements.filter((el) => el.data.highlighted === true)).toHaveLength(1)
  })

  it('沒有高亮路徑時所有邊都不標記', () => {
    const elements = toElements(payload, { scheme: 'role' })
    expect(elements.some((el) => el.data.highlighted === true)).toBe(false)
  })
})

describe('nodeColor（role 配色：劇本圖）', () => {
  it('focus 節點用金色，優先於其他規則', () => {
    expect(nodeColor(payload.nodes[0], { scheme: 'role', focus: 'TAggregator01' })).toBe('#f1c40f')
  })

  it('命中圖樣的節點用紅色', () => {
    expect(nodeColor(payload.nodes[0], { scheme: 'role' })).toBe('#e74c3c')
  })

  it('高分節點即使沒命中圖樣也用紅色', () => {
    expect(nodeColor({ ...payload.nodes[1], score: 0.8 }, { scheme: 'role' })).toBe('#e74c3c')
  })

  it('其餘節點依角色著色', () => {
    expect(nodeColor(payload.nodes[1], { scheme: 'role' })).toBe('#e67e22')
    expect(nodeColor(payload.nodes[2], { scheme: 'role' })).toBe('#9b59b6')
  })
})

describe('nodeColor（risk 配色：工作台）', () => {
  // 範例圖與真實 TRON 圖沒有 role，全部是 normal；只靠角色著色會整片單色。
  const normal = (score: number): GraphPayload['nodes'][number] => ({
    ...payload.nodes[1],
    role: 'normal',
    role_zh: '正常交易地址',
    is_motif_center: false,
    score,
  })

  it('高分紅、中分琥珀、低分藍——三段都不同', () => {
    expect(nodeColor(normal(0.85), { scheme: 'risk' })).toBe('#e74c3c')
    expect(nodeColor(normal(0.55), { scheme: 'risk' })).toBe('#f5b041')
    expect(nodeColor(normal(0.12), { scheme: 'risk' })).toBe('#5dade2')
  })

  it('風險配色忽略角色，同分數不因角色而異色', () => {
    const asMule = { ...normal(0.12), role: 'mule' }
    expect(nodeColor(asMule, { scheme: 'risk' })).toBe(nodeColor(normal(0.12), { scheme: 'risk' }))
  })

  it('focus 仍然優先', () => {
    expect(nodeColor(normal(0.12), { scheme: 'risk', focus: 'TMule03' })).toBe('#f1c40f')
  })
})
