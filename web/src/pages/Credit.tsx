import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, postCredit } from '../api/client'
import { CREDIT_CONTROL_SNAPSHOT, CREDIT_SNAPSHOT, GROUP_SNAPSHOT } from '../api/snapshot'
import type { AttentionLabel, CreditOpinion } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'
import { nodeColor } from '../graph/elements'
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

/** 圖上「high／medium／low」是後端把授信 watch／caution／normal 映射過去給著色用的，
 * 這裡把它映回授信詞彙顯示，避免跟防詐分支的 RISK_LABEL_ZH（「高風險」）混用。
 * 對照關係見 smelens/api 的 _GRAPH_LABEL_ZH／graph_to_json 著色邏輯。 */
const ATTENTION_LEVEL_ZH: Record<string, string> = {
  high: '關注',
  medium: '留意',
  low: '正常',
}

/** 節點表格「關注等級」欄位的顏色，鍵沿用圖上的 high／medium／low（與 ATTENTION_COLOR 同色階）。 */
const ATTENTION_COLOR_BY_GRAPH_LABEL: Record<string, string> = {
  high: 'var(--color-risk-high)',
  medium: 'var(--color-risk-med)',
  low: 'var(--color-risk-low)',
}

function formatTwd(amount: number): string {
  return `${amount.toLocaleString('zh-TW')} 元`
}

/**
 * 集團歸戶頁（Group.tsx）示範名冊歸戶後，泰昇集團落在的集團編號與合計曝險——
 * 單一來源是 GROUP_SNAPSHOT（scripts/make_snapshots.py 產生），不是字面常數，
 * 避免這裡與 /group 頁面各存一份數字而漂移。示範名冊只有一個集團編號，
 * 取曝險最高的那個即為「帶入集團歸戶脈絡」勾選時要帶的集團。
 */
const [DEMO_GROUP_ID, DEMO_GROUP_EXPOSURE] = Object.entries(GROUP_SNAPSHOT.exposures).sort(
  ([, a], [, b]) => b - a,
)[0]

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
  // 供 aria-live 區域播報非視覺回饋：查詢中／結果就緒／失敗，按鈕文字改變本身
  // 螢幕報讀器聽不到。
  const [announcement, setAnnouncement] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setAnnouncement('查詢中，正在產生授信意見書…')
    try {
      setResult(
        await postCredit(
          target,
          withGroup ? Number(DEMO_GROUP_ID) : undefined,
          withGroup ? DEMO_GROUP_EXPOSURE : undefined,
        ),
      )
      setOffline(false)
      setAnnouncement('授信意見書已產生。')
    } catch (err) {
      // 完全無法連線（斷網/DNS/CORS）或後端本身出錯（5xx，含 Vercel 冷啟動逾時）時
      // 退回內建快照，讓現場演示不中斷；畫面會明確標示為離線快照。
      // 4xx（例如 VITE_API_BASE 設錯導致的 404/405）不算——那是設定問題，
      // 假裝查詢成功反而會掩蓋它。兩個示範企業都有各自的離線快照，
      // 現場切到對照組（禾昌五金）也不會只剩一行錯誤訊息。
      if (err instanceof ApiError && (err.status === 0 || err.status >= 500)) {
        setResult(target === '泰昇精密' ? CREDIT_SNAPSHOT : CREDIT_CONTROL_SNAPSHOT)
        setOffline(true)
        setAnnouncement('無法連線即時服務，已改用內建備援資料顯示授信意見書。')
      } else {
        // 清掉上一次的結果，避免畫面同時顯示錯誤條與舊的（且可能是別家公司的）決策卡。
        setResult(null)
        setOffline(false)
        const detail = err instanceof ApiError ? err.detail : '產生授信意見書失敗，請稍後再試。'
        setError(detail)
        setAnnouncement(`查詢失敗：${detail}`)
      }
    } finally {
      setLoading(false)
    }
  }

  // FIX 5：查詢結果出現後，把焦點移到結果區第一個標題（「建議」），螢幕報讀器
  // 使用者按下查詢按鈕後不必自己往下找，報告從那裡開始就能被讀到。
  useEffect(() => {
    if (!result) return
    const heading = rootRef.current?.querySelector<HTMLElement>('h2')
    heading?.focus()
  }, [result])

  const handleSelect = useCallback((nodeId: string) => {
    // 目前僅供未來擴充（例如點選節點展開個別敘事）；先保留 hook 以符合 GraphView 合約。
    void nodeId
  }, [])

  return (
    <div className="space-y-6" ref={rootRef}>
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <div>
        <h1 className="text-2xl font-semibold">授信意見書</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          企業申請週轉金，財務報表看起來健康、無退票紀錄——傳統財報審核會直接放行。
          以下展示企業關係圖如何揭露財報看不到的三個結構問題：申請人自身即命中封閉資金環與買方集中，
          而它所在的資金環上，還有一段由宏益企業（空殼中介）經手的過水——申請人身處其中、
          卻不是三者的直接發動者，這正是關係圖比孤立看單一公司財報多看到的東西。
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

      {result?.graph.meta.truncated && (
        <ErrorNotice
          message={`本次企業關係圖節點數過多，僅保留風險分數最高的 ${result.graph.meta.node_count} 個節點（原始共 ${result.graph.meta.total_node_count} 個）。下方的結構證據、命中圖樣與敘事皆基於這張截斷後的圖計算，可能未涵蓋企業關係圖的全部關聯，請一併參考人工覆核。`}
        />
      )}

      {result?.graph.meta.degraded && (
        <ErrorNotice message="本次企業關係圖來源已降級（即時圖形資料無法完整取得，改用替代資料計算），下方的結構分析與建議僅供參考，並非基於完整即時資料，請提高覆核比重。" />
      )}

      {result && (
        <>
          <Panel title="建議">
            <p
              className="rounded border-l-4 pl-4 text-3xl font-semibold leading-relaxed text-ink"
              style={{ borderColor: ATTENTION_COLOR[result.label] }}
            >
              {result.recommendation_zh}
            </p>
          </Panel>

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
                {result.network_credit === null ? (
                  <div className="mt-1 text-sm leading-relaxed text-muted">
                    未評估——本公司在此關係圖中無被觀察到的收入（入度為 0，僅見付款、
                    未見收款），沒有「買方結構」可供評估，故不給分數，非評估結果為零。
                  </div>
                ) : (
                  <div className="tabular mt-1 text-xl">{result.network_credit.toFixed(4)}</div>
                )}
              </div>
            </div>
          </Panel>

          {result.group_id !== null && result.group_exposure_twd !== null && (
            <Panel title="集團歸戶脈絡（呼叫端提供）">
              <p className="text-sm leading-relaxed text-muted">
                依呼叫端提供之歸戶結果：本企業屬集團編號{' '}
                <span className="font-semibold text-ink">{result.group_id}</span>，
                該集團合計曝險為{' '}
                <span className="font-semibold text-ink">
                  {formatTwd(result.group_exposure_twd)}
                </span>
                。此為呼叫端提供之歸戶結果，非本頁面自行判定。
              </p>
            </Panel>
          )}

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
                    <th className="py-2 pr-4">圖例</th>
                    <th className="py-2 pr-4">分數</th>
                    <th className="py-2 pr-4">關注等級</th>
                  </tr>
                </thead>
                <tbody>
                  {result.graph.nodes.map((node) => (
                    <tr key={node.id} className="border-b border-line/50">
                      <td className="py-2 pr-4">{node.id}</td>
                      <td className="py-2 pr-4">{node.role_zh}</td>
                      <td className="py-2 pr-4">
                        <span
                          aria-hidden="true"
                          className="inline-block h-3 w-3 rounded-full align-middle"
                          style={{
                            backgroundColor: nodeColor(node, { scheme: 'role', focus: result.target }),
                          }}
                        />
                      </td>
                      <td className="py-2 pr-4">{node.score.toFixed(2)}</td>
                      <td className="py-2 pr-4" style={{ color: ATTENTION_COLOR_BY_GRAPH_LABEL[node.label] }}>
                        {ATTENTION_LEVEL_ZH[node.label] ?? node.label}
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
