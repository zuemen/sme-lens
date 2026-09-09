import type { ElementDefinition } from 'cytoscape'
import type { GraphNode, GraphPayload } from '../api/types'

/**
 * 角色色碼。前八個沿用 smelens/app/workbench.py 的防詐劇本配色，與既有截圖一致；
 * 後六個是企金劇本的角色。
 *
 * 這裡必須是原始 hex：Cytoscape 畫在 canvas 上，解析不了 CSS 變數。
 * DOM 文字用 var(--color-*)，兩套配色是刻意分開的。
 */
const ROLE_COLOR: Record<string, string> = {
  // 防詐劇本
  victim: '#f5b041',
  support: '#e74c3c',
  aggregator: '#c0392b',
  mule: '#e67e22',
  peel: '#d35400',
  peel_side: '#7f8c8d',
  otc: '#9b59b6',
  normal: '#5dade2',
  // 企金劇本
  applicant: '#f1c40f',
  anchor_buyer: '#16a085',
  buyer: '#5dade2',
  shell: '#c0392b',
  related: '#e67e22',
  supplier: '#7f8c8d',
}

const FOCUS_COLOR = '#f1c40f'
const HIT_COLOR = '#e74c3c'
const MED_COLOR = '#f5b041'
const LOW_COLOR = '#5dade2'
const HIGH_SCORE = 0.7
const MED_SCORE = 0.4

/**
 * role＝劇本圖，沿用 Streamlit 的角色語意配色。
 * risk＝工作台，範例圖與真實 TRON 圖沒有 role 屬性（全是 normal），
 *       只靠角色著色會渲染成整片單色，故改用分數色階。
 */
export type ColorScheme = 'role' | 'risk'

export function nodeColor(
  node: GraphNode,
  options: { scheme: ColorScheme; focus?: string },
): string {
  if (options.focus && node.id === options.focus) return FOCUS_COLOR
  if (options.scheme === 'risk') {
    if (node.score >= HIGH_SCORE) return HIT_COLOR
    if (node.score >= MED_SCORE) return MED_COLOR
    return LOW_COLOR
  }
  if (node.is_motif_center || node.score >= HIGH_SCORE) return HIT_COLOR
  return ROLE_COLOR[node.role] ?? ROLE_COLOR.normal
}

export function toElements(
  payload: GraphPayload,
  options: { scheme: ColorScheme; highlightPath?: string[]; focus?: string },
): ElementDefinition[] {
  const { scheme, highlightPath = [], focus } = options
  const pathEdges = new Set(
    highlightPath.slice(0, -1).map((from, index) => `${from}->${highlightPath[index + 1]}`),
  )

  const nodes: ElementDefinition[] = payload.nodes.map((node) => ({
    data: {
      id: node.id,
      label: node.id.length > 14 ? `${node.id.slice(0, 14)}…` : node.id,
      roleZh: node.role_zh,
      score: node.score,
      narrative: node.narrative_zh,
      color: nodeColor(node, { scheme, focus }),
      size: 16 + node.pagerank * 300,
      focused: focus === node.id,
      motifCenter: node.is_motif_center,
    },
  }))

  const edges: ElementDefinition[] = payload.edges.map((edge, index) => ({
    data: {
      id: `e${index}`,
      source: edge.source,
      target: edge.target,
      amount: edge.amount,
      highlighted: pathEdges.has(`${edge.source}->${edge.target}`),
    },
  }))

  return [...nodes, ...edges]
}
