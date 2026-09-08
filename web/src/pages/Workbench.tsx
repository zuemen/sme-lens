import { useCallback, useEffect, useState } from 'react'
import { ApiError, postGraph } from '../api/client'
import type { GraphNode, WorkbenchPayload } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'
import { GraphView } from '../graph/GraphView'

const TRON_ADDRESS = /^T[1-9A-HJ-NP-Za-km-z]{33}$/

type GraphSource = { kind: 'example' } | { kind: 'tron'; address: string }

function sourceLabel(source: GraphSource | null): string {
  if (!source) return ''
  return source.kind === 'tron' ? `TRON 即時：${source.address}` : '內建範例圖'
}

export default function Workbench() {
  const [address, setAddress] = useState('')
  const [payload, setPayload] = useState<WorkbenchPayload | null>(null)
  // 目前畫面上這張圖的來源；只在成功查詢後更新，失敗時維持不變——
  // 這樣即使查詢失敗、畫面保留上一張圖，標題也如實反映那張圖到底是什麼。
  const [source, setSource] = useState<GraphSource | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function load(mode: 'example' | 'tron') {
    setLoading(true)
    setError(null)
    try {
      const next = await postGraph(mode === 'tron' ? { mode, address } : { mode })
      setPayload(next)
      setSource(mode === 'tron' ? { kind: 'tron', address } : { kind: 'example' })
      setSelected(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : '載入失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load('example')
    // 只在首次掛載時載入內建範例圖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSelect = useCallback(
    (id: string) => setSelected(payload?.nodes.find((node) => node.id === id) ?? null),
    [payload],
  )

  const addressValid = TRON_ADDRESS.test(address)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">金流圖譜工作台</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          內建範例圖含集資扇入、快速分散、剝洋蔥鏈三種圖樣。也可輸入 TRON 主網地址，
          即時抓取 2-hop USDT 金流圖——真實查詢約需 10–30 秒。
        </p>
      </div>

      <Panel>
        <div className="grid gap-4 md:grid-cols-[3fr_auto_auto] md:items-end">
          <label className="block">
            <span className="text-xs text-muted">TRON 地址（TRC-20 USDT）</span>
            <input
              value={address}
              onChange={(event) => setAddress(event.target.value.trim())}
              placeholder="T 開頭主網地址，34 字元"
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            />
            {address && !addressValid && (
              <span className="mt-1 block text-xs" style={{ color: 'var(--color-risk-med)' }}>
                地址格式不正確：需為 T 開頭的 Base58 主網地址（34 字元）。
              </span>
            )}
          </label>

          <button
            type="button"
            onClick={() => load('tron')}
            disabled={!addressValid || loading}
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-40"
          >
            {loading ? '查詢中…' : '抓取真實金流'}
          </button>

          <button
            type="button"
            onClick={() => load('example')}
            disabled={loading}
            className="rounded border border-line px-5 py-2"
          >
            用內建範例圖
          </button>
        </div>
      </Panel>

      {error && (
        <ErrorNotice
          message={error}
          action={{ label: '改用內建範例圖', onClick: () => load('example') }}
        />
      )}

      {payload && (
        <>
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Panel
              title={`金流圖譜 · ${sourceLabel(source)}（${payload.meta.node_count} 節點 / ${payload.meta.edge_count} 邊）`}
            >
              <GraphView payload={payload} layout="cose" scheme="risk" onSelect={handleSelect} />
              {payload.meta.truncated && (
                <p className="mt-3 text-xs" style={{ color: 'var(--color-risk-med)' }}>
                  圖譜顯示風險最高的 {payload.meta.node_count} 個節點（原始共{' '}
                  {payload.meta.total_node_count} 個）。下方鄰接表僅列出這{' '}
                  {payload.meta.node_count} 個節點之間的連線，被截斷節點的連線不會出現在表中。
                </p>
              )}
              <p className="mt-3 text-xs text-muted">點選節點查看該地址的風險證據。</p>
            </Panel>

            <Panel title="風險證據">
              {selected ? (
                <div className="space-y-3">
                  <div className="tabular text-sm">{selected.id}</div>
                  <div className="tabular text-3xl">{selected.score.toFixed(2)}</div>
                  <p className="text-sm leading-relaxed text-muted">{selected.narrative_zh}</p>
                </div>
              ) : (
                <p className="text-sm text-muted">尚未選取節點。</p>
              )}
            </Panel>
          </div>

          <Panel title="資金流向明細（鄰接表）">
            <p className="mb-3 text-xs text-muted">
              圖譜對螢幕閱讀器不可讀，此表為等效的文字替代，列出圖中每一條資金流向。
            </p>
            <div className="max-h-80 overflow-auto">
              <table className="tabular w-full text-left text-xs">
                <caption className="sr-only">
                  金流圖譜的鄰接表，欄位為來源地址、目標地址與轉帳金額
                </caption>
                <thead className="sticky top-0 bg-panel text-muted">
                  <tr>
                    <th scope="col" className="py-2 pr-4 font-normal">來源</th>
                    <th scope="col" className="py-2 pr-4 font-normal">目標</th>
                    <th scope="col" className="py-2 pr-4 font-normal">金額（USDT）</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.edges.map((edge) => (
                    <tr key={`${edge.source}->${edge.target}`} className="border-t border-line">
                      <td className="py-2 pr-4">{edge.source}</td>
                      <td className="py-2 pr-4">{edge.target}</td>
                      <td className="py-2 pr-4">{edge.amount.toLocaleString('zh-TW')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="SNA 指標（依風險分數排序前 15 名）">
            <div className="overflow-x-auto">
              <table className="tabular w-full text-left text-xs">
                <thead className="text-muted">
                  <tr>
                    {['地址', 'in', 'out', 'PageRank', 'k-core', 'betweenness', '分數'].map(
                      (head) => (
                        <th key={head} className="py-2 pr-4 font-normal">
                          {head}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {payload.sna.map((row) => (
                    <tr key={row.node} className="border-t border-line">
                      <td className="py-2 pr-4">{row.node}</td>
                      <td className="py-2 pr-4">{row.in_degree.toFixed(0)}</td>
                      <td className="py-2 pr-4">{row.out_degree.toFixed(0)}</td>
                      <td className="py-2 pr-4">{row.pagerank.toFixed(4)}</td>
                      <td className="py-2 pr-4">{row.kcore.toFixed(0)}</td>
                      <td className="py-2 pr-4">{row.betweenness.toFixed(4)}</td>
                      <td className="py-2 pr-4">{row.score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
