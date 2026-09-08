import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import type { DagreLayoutOptions } from 'cytoscape-dagre'
import { useEffect, useRef } from 'react'
import type { GraphPayload } from '../api/types'
import { type ColorScheme, toElements } from './elements'

cytoscape.use(dagre)

const STYLE: cytoscape.StylesheetJson = [
  {
    selector: 'node',
    style: {
      'background-color': 'data(color)',
      width: 'data(size)',
      height: 'data(size)',
      label: 'data(label)',
      color: '#e6edf3',
      'font-size': 9,
      'font-family': 'ui-monospace, Menlo, monospace',
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'border-width': 0,
    },
  },
  {
    // 工作台用分數色階時，命中圖樣的節點靠外框而非填色來標示
    selector: 'node[?motifCenter]',
    style: { 'border-width': 2, 'border-color': '#e74c3c' },
  },
  {
    selector: 'node[?focused]',
    style: { 'border-width': 4, 'border-color': '#f1c40f' },
  },
  {
    selector: 'edge',
    style: {
      width: 1,
      'line-color': '#2b3947',
      'target-arrow-color': '#2b3947',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.7,
      'curve-style': 'bezier',
    },
  },
  {
    selector: 'edge[?highlighted]',
    style: { width: 5, 'line-color': '#f39c12', 'target-arrow-color': '#f39c12' },
  },
]

export function GraphView({
  payload,
  highlightPath,
  focus,
  layout,
  scheme,
  onSelect,
}: {
  payload: GraphPayload
  highlightPath?: string[]
  focus?: string
  /** dagre＝劇本圖由左至右說故事；cose＝真實 2-hop 圖沒有敘事順序 */
  layout: 'dagre' | 'cose'
  scheme: ColorScheme
  onSelect?: (nodeId: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    const dagreLayout: DagreLayoutOptions = {
      name: 'dagre',
      rankDir: 'LR',
      nodeSep: 18,
      rankSep: 90,
    }
    const cy = cytoscape({
      container: container.current,
      elements: toElements(payload, { scheme, highlightPath, focus }),
      style: STYLE,
      layout:
        layout === 'dagre' ? dagreLayout : { name: 'cose', randomize: false, animate: false },
      minZoom: 0.2,
      maxZoom: 2.5,
    })
    if (onSelect) {
      cy.on('tap', 'node', (event) => onSelect(event.target.id() as string))
    }
    return () => cy.destroy()
  }, [payload, highlightPath, focus, layout, scheme, onSelect])

  return (
    <div
      ref={container}
      data-testid="graph-view"
      className="h-[520px] w-full rounded border border-line"
      style={{ backgroundColor: 'var(--color-graph-bg)' }}
    />
  )
}
