import { useCallback, useState } from 'react'
import { ApiError, postCredit } from '../api/client'
import { CREDIT_SNAPSHOT } from '../api/snapshot'
import type { AttentionLabel, CreditOpinion } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'
import { RISK_LABEL_ZH, riskColor } from '../components/RiskBadge'
import { GraphView } from '../graph/GraphView'

const TARGETS = [
  { value: '泰昇精密', label: '泰昇精密（授信申請人）' },
  { value: '禾昌五金', label: '禾昌五金（對照組）' },
]

const ATTENTION_COLOR: Record<AttentionLabel, string> = {
  watch: 'var(--color-risk-high)',
  caution: 'var(--color-risk-med)',
  normal: 'var(--color-risk-low)',
}

const CENTRALITY_ZH: Record<string, string> = {
  in_degree: '入度百分位',
  out_degree: '出度百分位',
  pagerank: 'PageRank 百分位',
  kcore: 'K-core 百分位',
  betweenness: '中介中心性百分位',
}

export default function Credit() {
  const [target, setTarget] = useState(TARGETS[0].value)
  const [withGroup, setWithGroup] = useState(false)
  const [result, setResult] = useState<CreditOpinion | null>(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(
        await postCredit(target, withGroup ? 0 : undefined, withGroup ? 50000000 : undefined),
      )
      setOffline(false)
    } catch (err) {
      // 完全無法連線（斷網/DNS/CORS）或後端本身出錯（5xx，含 Vercel 冷啟動逾時）時
      // 退回內建快照，讓現場演示不中斷；畫面會明確標示為離線快照。
      // 4xx（例如 VITE_API_BASE 設錯導致的 404/405）不算——那是設定問題，
      // 假裝查詢成功反而會掩蓋它。
      if (
        err instanceof ApiError &&
        (err.status === 0 || err.status >= 500) &&
        target === '泰昇精密'
      ) {
        setResult(CREDIT_SNAPSHOT)
        setOffline(true)
      } else {
        // 清掉上一次的結果，避免畫面同時顯示錯誤條與舊的（且可能是別家公司的）決策卡。
        setResult(null)
        setOffline(false)
        setError(err instanceof ApiError ? err.detail : '產生授信意見書失敗，請稍後再試。')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleSelect = useCallback((nodeId: string) => {
    // 目前僅供未來擴充（例如點選節點展開個別敘事）；先保留 hook 以符合 GraphView 合約。
    void nodeId
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">授信意見書</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          企業申請週轉金，財務報表看起來健康、無退票紀錄——傳統財報審核會直接放行。
          以下展示企業關係圖如何揭露財報看不到的三件事：封閉資金環、買方集中與空殼過水。
        </p>
      </div>

      <Panel>
        <div className="grid gap-4 md:grid-cols-[2fr_1fr_auto] md:items-end">
          <label className="block">
            <span className="text-xs text-muted">授信申請企業</span>
            <select
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            >
              {TARGETS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={withGroup}
              onChange={(event) => setWithGroup(event.target.checked)}
            />
            帶入集團歸戶脈絡
          </label>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-50"
          >
            {loading ? '產生中…' : '產生授信意見書'}
          </button>
        </div>
      </Panel>

      {error && <ErrorNotice message={error} action={{ label: '重試', onClick: run }} />}

      {offline && (
        <ErrorNotice message="目前顯示的是內建離線快照（案例固定為泰昇精密），非即時查詢結果——已標示為離線快照。" />
      )}

      {result && (
        <>
          <Panel title="授信關注等級">
            <div className="grid grid-cols-2 gap-6 md:grid-cols-3">
              <div>
                <div className="text-xs text-muted">關注等級</div>
                <div
                  className="mt-1 text-2xl font-semibold"
                  style={{ color: ATTENTION_COLOR[result.label] }}
                >
                  {result.label_zh}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted">授信關注分數</div>
                <div
                  className="tabular mt-1 text-xl"
                  style={{ color: ATTENTION_COLOR[result.label] }}
                >
                  {result.attention_score.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted">網絡信用分</div>
                <div className="tabular mt-1 text-xl">{result.network_credit.toFixed(4)}</div>
              </div>
            </div>
          </Panel>

          <Panel title="建議">
            <p
              className="rounded border-l-4 pl-4 text-3xl font-semibold leading-relaxed text-ink"
              style={{ borderColor: ATTENTION_COLOR[result.label] }}
            >
              {result.recommendation_zh}
            </p>
          </Panel>

          <Panel title="敘事">
            <p className="text-sm leading-relaxed text-muted">{result.narrative_zh}</p>
          </Panel>

          <Panel title="命中企金風險圖樣">
            {result.motif_hits.length > 0 ? (
              <ul className="space-y-3 text-sm">
                {result.motif_hits.map((hit) => (
                  <li key={`${hit.motif}-${hit.center}`} className="border-l-2 border-line pl-4">
                    {hit.description_zh}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">
                未命中任何企金風險圖樣——本公司在關係圖上未出現循環交易、空殼中介或買方集中的結構特徵。
              </p>
            )}
          </Panel>

          <Panel title="結構證據">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
              {Object.entries(result.centrality_percentile).map(([key, value]) => (
                <div key={key}>
                  <div className="text-xs text-muted">{CENTRALITY_ZH[key] ?? key}</div>
                  <div className="tabular mt-1 text-lg">{value.toFixed(2)}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs text-muted">交易對手多樣性</div>
                <div className="tabular mt-1 text-lg">
                  {result.counterparty_diversity.toFixed(4)}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted">社群風險比例</div>
                <div className="tabular mt-1 text-lg">{result.community_risk_ratio.toFixed(4)}</div>
              </div>
            </div>
          </Panel>

          <Panel title="企業關係圖譜（外框標示命中圖樣節點；金框＝申請企業）">
            <GraphView
              payload={result.graph}
              focus={result.target}
              layout="cose"
              scheme="role"
              onSelect={handleSelect}
            />
          </Panel>

          <Panel title="節點清單（圖譜之等價替代）">
            <div className="overflow-x-auto">
              <table className="tabular w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-muted">
                    <th className="py-2 pr-4">企業</th>
                    <th className="py-2 pr-4">角色</th>
                    <th className="py-2 pr-4">分數</th>
                    <th className="py-2 pr-4">風險等級</th>
                  </tr>
                </thead>
                <tbody>
                  {result.graph.nodes.map((node) => (
                    <tr key={node.id} className="border-b border-line/50">
                      <td className="py-2 pr-4">{node.id}</td>
                      <td className="py-2 pr-4">{node.role_zh}</td>
                      <td className="py-2 pr-4">{node.score.toFixed(2)}</td>
                      <td className="py-2 pr-4" style={{ color: riskColor(node.label) }}>
                        {RISK_LABEL_ZH[node.label]}
                      </td>
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
